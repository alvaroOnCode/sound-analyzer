from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sound_analyzer.catalog import SORTS, Catalog, ClipRow, ClipView
from sound_analyzer.paths import index_dir, resolve_library

STATIC_DIR = Path(__file__).parent / "static"
PEAK_BUCKETS = 480
PEAK_SAMPLE_RATE = 8000
MAX_PEAK_SECONDS = 600.0

# suggested_name looks like `dogs_bark_1000ms_00000a.wav`; the tail is bookkeeping, not a title.
_NAME_SUFFIX = re.compile(r"_\d+ms_[0-9a-f]{4,}$")

_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".wave": "audio/wav",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".mp2": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
    ".caf": "audio/x-caf",
    ".au": "audio/basic",
}


def display_name(clip: ClipRow) -> str:
    stem = (clip.suggested_name or "").rsplit(".", 1)[0]
    stem = _NAME_SUFFIX.sub("", stem)
    if not stem:
        stem = clip.relpath.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return stem.replace("_", " ").strip() or clip.relpath


def clip_payload(view: ClipView, *, score: float | None = None) -> dict[str, Any]:
    clip, file = view.clip, view.file
    relpath = clip.relpath
    folder, _, filename = relpath.rpartition("/")
    payload: dict[str, Any] = {
        "id": clip.id,
        "name": display_name(clip),
        "filename": filename or relpath,
        "relpath": relpath,
        "folder": folder,
        "category": clip.category,
        "subcategory": clip.subcategory,
        "tags": clip.tags,
        "confidence": clip.confidence,
        "start": round(clip.start_sec, 3),
        "end": round(clip.end_sec, 3),
        "duration": round(clip.duration_ms / 1000.0, 3),
        "is_full_file": clip.is_full_file,
        "suggested_name": clip.suggested_name,
        "sample_rate": file.sample_rate,
        "channels": file.channels,
        "codec": file.codec,
        "size": file.size,
        "file_duration": file.duration,
    }
    if score is not None:
        payload["score"] = round(score, 4)
    return payload


def create_app(library: Path) -> FastAPI:
    library = resolve_library(library)
    app = FastAPI(title="sound-analyzer", docs_url=None, redoc_url=None)
    app.state.library = library

    @contextmanager
    def catalog() -> Iterator[Catalog]:
        # A connection per request: sync endpoints run in a threadpool and
        # sqlite3 connections are not shareable across threads.
        cat = Catalog(library)
        try:
            yield cat
        finally:
            cat.close()

    def load_view(clip_id: int) -> ClipView:
        with catalog() as cat:
            view = cat.get_clip_view(clip_id)
        if view is None:
            raise HTTPException(status_code=404, detail=f"No existe el clip {clip_id}")
        return view

    def source_path(view: ClipView) -> Path:
        path = library / view.clip.relpath
        if not path.exists():
            raise HTTPException(status_code=410, detail=f"El archivo ya no está: {view.clip.relpath}")
        return path

    def preview_path(view: ClipView) -> Path:
        """Original file for whole-file clips, extracted wav for segments."""
        src = source_path(view)
        if view.clip.is_full_file:
            return src
        from sound_analyzer.audio import extract_wav

        dest = index_dir(library) / "preview" / f"clip_{view.clip.id}.wav"
        if not dest.exists() or dest.stat().st_size == 0:
            extract_wav(
                src,
                dest,
                start=view.clip.start_sec,
                duration=view.clip.end_sec - view.clip.start_sec,
            )
        return dest

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/library")
    def api_library() -> dict[str, Any]:
        with catalog() as cat:
            return {
                "path": str(library),
                "name": library.name,
                "stats": cat.stats(),
                "categories": cat.category_tree(),
                "folders": cat.folders(),
                "sorts": list(SORTS),
            }

    @app.get("/api/browse")
    def api_browse(
        category: str | None = None,
        subcategory: str | None = None,
        folder: str | None = None,
        q: str | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
        sort: str = "name",
        limit: int = Query(60, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        filters = {
            "category": category,
            "subcategory": subcategory,
            "folder": folder,
            "text": q,
            "min_duration": min_duration,
            "max_duration": max_duration,
        }
        with catalog() as cat:
            total = cat.count_clips(**filters)
            views = cat.query_clips(**filters, sort=sort, limit=limit, offset=offset)
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": [clip_payload(view) for view in views],
        }

    def _hits_payload(hits: list[Any]) -> list[dict[str, Any]]:
        with catalog() as cat:
            out = []
            for hit in hits:
                view = cat.get_clip_view(hit.clip.id)
                if view is not None:
                    out.append(clip_payload(view, score=hit.score))
        return out

    @app.get("/api/search")
    def api_search(
        q: str,
        top: int = Query(25, ge=1, le=200),
        folder: str | None = None,
    ) -> dict[str, Any]:
        from sound_analyzer.search import search_text

        query = q.strip()
        if not query:
            raise HTTPException(status_code=422, detail="La consulta está vacía.")
        hits = search_text(library, query, top=top, folder=folder or None)
        return {"query": query, "kind": "text", "results": _hits_payload(hits)}

    @app.post("/api/search/audio")
    def api_search_audio(
        file: UploadFile = File(...),
        top: int = Query(25, ge=1, le=200),
        folder: str | None = None,
    ) -> dict[str, Any]:
        from sound_analyzer.search import search_audio

        suffix = Path(file.filename or "ref.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file.file.read())
            reference = Path(tmp.name)
        try:
            hits = search_audio(library, reference, top=top, folder=folder or None)
        finally:
            reference.unlink(missing_ok=True)
        return {"query": file.filename, "kind": "audio", "results": _hits_payload(hits)}

    @app.get("/api/clip/{clip_id}")
    def api_clip(clip_id: int) -> dict[str, Any]:
        return clip_payload(load_view(clip_id))

    @app.get("/api/clip/{clip_id}/audio")
    def api_clip_audio(clip_id: int) -> FileResponse:
        view = load_view(clip_id)
        path = preview_path(view)
        media_type = _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=media_type)

    @app.get("/api/clip/{clip_id}/download")
    def api_clip_download(clip_id: int) -> FileResponse:
        view = load_view(clip_id)
        path = preview_path(view)
        name = view.clip.suggested_name or path.name
        if Path(name).suffix.lower() != path.suffix.lower():
            name = f"{Path(name).stem}{path.suffix}"
        return FileResponse(path, filename=name)

    @app.get("/api/clip/{clip_id}/peaks")
    def api_clip_peaks(clip_id: int, buckets: int = Query(PEAK_BUCKETS, ge=16, le=2000)) -> dict[str, Any]:
        view = load_view(clip_id)
        cache = index_dir(library) / "preview" / f"peaks_{clip_id}_{buckets}.json"
        if cache.exists():
            try:
                return json.loads(cache.read_text())
            except (json.JSONDecodeError, OSError):
                cache.unlink(missing_ok=True)
        peaks = _compute_peaks(source_path(view), view.clip, buckets)
        payload = {"id": clip_id, "buckets": buckets, "peaks": peaks}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload))
        return payload

    @app.post("/api/reveal")
    def api_reveal(payload: dict[str, int]) -> JSONResponse:
        """Show the original file in Finder/Explorer. Local-only tool, local-only feature."""
        view = load_view(int(payload.get("clip_id", 0)))
        path = source_path(view)
        if sys.platform == "darwin":
            cmd = ["open", "-R", str(path)]
        elif sys.platform.startswith("win"):
            cmd = ["explorer", f"/select,{path}"]
        else:
            cmd = ["xdg-open", str(path.parent)]
        try:
            subprocess.Popen(cmd)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse({"ok": True, "path": str(path)})

    app.mount("/static", _RevalidatingStatic(directory=STATIC_DIR), name="static")
    return app


class _RevalidatingStatic(StaticFiles):
    """Serving from disk on localhost: revalidate always so edits show up."""

    def file_response(self, *args: Any, **kwargs: Any) -> Any:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _compute_peaks(path: Path, clip: ClipRow, buckets: int) -> list[float]:
    import numpy as np

    from sound_analyzer.audio import load_audio

    duration = min(max(clip.end_sec - clip.start_sec, 0.0), MAX_PEAK_SECONDS)
    try:
        samples, _sr = load_audio(
            path,
            sr=PEAK_SAMPLE_RATE,
            start=clip.start_sec,
            duration=duration or None,
            mono=True,
        )
    except Exception:
        return [0.0] * buckets
    if samples.size == 0:
        return [0.0] * buckets
    chunks = np.array_split(np.abs(samples), buckets)
    peaks = np.array([float(chunk.max()) if chunk.size else 0.0 for chunk in chunks])
    ceiling = float(peaks.max())
    if ceiling > 1e-6:
        peaks = peaks / ceiling
    return [round(float(value), 3) for value in peaks]
