from __future__ import annotations

import shutil
from pathlib import Path

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from sound_analyzer.audio import extract_wav
from sound_analyzer.catalog import Catalog, ClipRow
from sound_analyzer.paths import ORGANIZED_DIRNAME, organized_dir
from sound_analyzer.taxonomy import slugify


def _dest_for_clip(library: Path, clip: ClipRow) -> Path:
    category = slugify(clip.category or "review")
    subcategory = slugify(clip.subcategory or "generic")
    name = clip.suggested_name or f"sfx_{clip.duration_ms}ms_{clip.id:06x}.wav"
    return organized_dir(library) / category / subcategory / name


def _same_filesystem(src: Path, library: Path) -> bool:
    try:
        return src.stat().st_dev == library.stat().st_dev
    except OSError:
        return False


def _needs_extract(clip: ClipRow) -> bool:
    return not clip.is_full_file


def plan_organize(library: Path) -> list[tuple[ClipRow, Path, str]]:
    catalog = Catalog(library)
    planned: list[tuple[ClipRow, Path, str]] = []
    for clip in catalog.iter_clips():
        if not clip.tagged:
            continue
        dest = _dest_for_clip(library, clip)
        src = catalog.abs_path(clip.relpath)
        if _needs_extract(clip):
            method = "extract"
        elif _same_filesystem(src, library):
            method = "hardlink"
        else:
            method = "copy"
        planned.append((clip, dest, method))
    catalog.close()
    return planned


def apply_organize(library: Path, *, force: bool = False) -> dict[str, int]:
    catalog = Catalog(library)
    planned = []
    for clip in catalog.iter_clips():
        if not clip.tagged:
            continue
        dest = _dest_for_clip(library, clip)
        src = catalog.abs_path(clip.relpath)
        if dest.exists() and not force:
            continue
        if _needs_extract(clip):
            method = "extract"
        elif _same_filesystem(src, library):
            method = "hardlink"
        else:
            method = "copy"
        planned.append((clip, src, dest, method))

    copied = linked = extracted = skipped = errors = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Organizando", total=len(planned))
        for clip, src, dest, method in planned:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and force:
                    dest.unlink()
                if method == "extract":
                    extract_wav(src, dest, start=clip.start_sec, duration=clip.end_sec - clip.start_sec)
                    extracted += 1
                elif method == "hardlink":
                    try:
                        dest.hardlink_to(src)
                        linked += 1
                    except OSError:
                        shutil.copy2(src, dest)
                        method = "copy"
                        copied += 1
                else:
                    shutil.copy2(src, dest)
                    copied += 1
                rel = dest.relative_to(library).as_posix()
                catalog.log_organize(clip.id, rel, method)
            except Exception:
                errors += 1
            progress.advance(task)
    catalog.close()
    return {
        "hardlink": linked,
        "copy": copied,
        "extract": extracted,
        "skipped": skipped,
        "errors": errors,
        "planned": len(planned),
    }


def undo_organize(library: Path) -> dict[str, int]:
    catalog = Catalog(library)
    rows = catalog.pending_organize()
    removed = 0
    missing = 0
    for row in rows:
        dest = library / row["dest_relpath"]
        if dest.exists():
            dest.unlink()
            removed += 1
        else:
            missing += 1
        catalog.mark_undone(int(row["id"]))
        _cleanup_empty_parents(dest.parent, library / ORGANIZED_DIRNAME)
    catalog.close()
    return {"removed": removed, "missing": missing}


def _cleanup_empty_parents(start: Path, stop: Path) -> None:
    current = start.resolve()
    stop = stop.resolve()
    while True:
        if current == stop:
            try:
                current.rmdir()
            except OSError:
                pass
            break
        if stop not in current.parents:
            break
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
