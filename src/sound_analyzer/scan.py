from __future__ import annotations

from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from sound_analyzer.audio import AUDIO_EXTENSIONS, probe
from sound_analyzer.catalog import Catalog
from sound_analyzer.paths import INDEX_DIRNAME, ORGANIZED_DIRNAME


def iter_audio_files(library: Path) -> list[Path]:
    files: list[Path] = []
    skip = {INDEX_DIRNAME, ORGANIZED_DIRNAME, ".git", ".venv", "__pycache__"}
    for path in library.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        rel_parts = path.relative_to(library).parts
        if any(part in skip or part.startswith(".") for part in rel_parts[:-1]):
            continue
        if path.name.startswith("."):
            continue
        files.append(path)
    files.sort()
    return files


def scan_library(library: Path, *, force: bool = False) -> dict[str, int]:
    catalog = Catalog(library)
    files = iter_audio_files(library)
    added = 0
    updated = 0
    skipped = 0
    errors = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Escaneando", total=len(files))
        for path in files:
            relpath = path.relative_to(library).as_posix()
            stat = path.stat()
            existing = catalog.get_file_by_path(relpath)
            if (
                existing is not None
                and not force
                and existing.size == stat.st_size
                and abs(existing.mtime - stat.st_mtime) < 0.001
            ):
                skipped += 1
                progress.advance(task)
                continue
            try:
                info = probe(path)
            except Exception:
                errors += 1
                progress.advance(task)
                continue
            _file_id, changed = catalog.upsert_file(
                relpath,
                size=stat.st_size,
                mtime=stat.st_mtime,
                duration=info.duration,
                sample_rate=info.sample_rate,
                channels=info.channels,
                codec=info.codec,
            )
            if existing is None:
                added += 1
            elif changed:
                updated += 1
            else:
                skipped += 1
            progress.advance(task)
    catalog.close()
    return {
        "found": len(files),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }
