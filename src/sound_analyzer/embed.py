from __future__ import annotations

from pathlib import Path

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from sound_analyzer.catalog import Catalog
from sound_analyzer.models.clap import embed_file


def embed_library(library: Path, *, force: bool = False, limit: int | None = None) -> dict[str, int]:
    catalog = Catalog(library)
    if force:
        catalog.conn.execute("UPDATE clips SET embedded = 0")
        catalog.conn.commit()
    clips = list(catalog.iter_clips(missing_embed=True))
    if limit is not None:
        clips = clips[: max(0, limit)]
    done = 0
    errors = 0
    first_error: str | None = None
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Embeddings CLAP", total=len(clips))
        for clip in clips:
            path = catalog.abs_path(clip.relpath)
            try:
                vector = embed_file(path, start=clip.start_sec, end=clip.end_sec)
                catalog.save_embedding(clip.id, vector)
                done += 1
            except Exception as exc:
                errors += 1
                if first_error is None:
                    first_error = f"{path}: {exc}"
            progress.advance(task)
    catalog.close()
    return {
        "embedded": done,
        "errors": errors,
        "pending": max(0, len(clips) - done),
        "first_error": first_error,
    }
