from __future__ import annotations

import re

from sound_analyzer.audio import detect_silences
from sound_analyzer.catalog import Catalog, FileRow

SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")


def parse_silence_log(stderr: str) -> list[tuple[float, float]]:
    """Parse ffmpeg silencedetect output into (start, end) silence intervals."""
    silences: list[tuple[float, float]] = []
    pending_start: float | None = None
    for line in stderr.splitlines():
        start_match = SILENCE_START.search(line)
        if start_match:
            pending_start = float(start_match.group(1))
            continue
        end_match = SILENCE_END.search(line)
        if end_match and pending_start is not None:
            silences.append((pending_start, float(end_match.group(1))))
            pending_start = None
    return silences


def invert_silences(
    silences: list[tuple[float, float]],
    duration: float,
    *,
    min_clip: float = 0.15,
    merge_gap: float = 0.12,
    pad: float = 0.04,
) -> list[tuple[float, float]]:
    """Turn silence intervals into non-silent sound regions."""
    if duration <= 0:
        return []
    regions: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in sorted(silences):
        start = max(0.0, min(start, duration))
        end = max(0.0, min(end, duration))
        if start > cursor + 1e-4:
            regions.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration - 1e-4:
        regions.append((cursor, duration))
    if not regions:
        return [(0.0, duration)]

    padded: list[tuple[float, float]] = []
    for start, end in regions:
        padded.append((max(0.0, start - pad), min(duration, end + pad)))

    merged: list[tuple[float, float]] = []
    for start, end in padded:
        if merged and start - merged[-1][1] <= merge_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    filtered = [(s, e) for s, e in merged if (e - s) >= min_clip]
    return filtered or [(0.0, duration)]


def intervals_for_file(
    file: FileRow,
    library,
    *,
    long_threshold: float = 12.0,
    noise_db: float = -35.0,
    min_silence: float = 0.35,
) -> list[tuple[float, float]]:
    duration = float(file.duration or 0.0)
    if duration <= 0:
        return [(0.0, 0.0)]
    if duration <= long_threshold:
        return [(0.0, duration)]
    path = library / file.relpath
    log = detect_silences(path, noise_db=noise_db, min_silence=min_silence)
    silences = parse_silence_log(log)
    if not silences:
        return [(0.0, duration)]
    regions = invert_silences(silences, duration)
    # A single near-full-file region means ambience/bed: keep as one clip.
    if len(regions) == 1:
        span = regions[0][1] - regions[0][0]
        if span >= duration * 0.85:
            return [(0.0, duration)]
    return regions


def segment_library(
    library,
    *,
    force: bool = False,
    long_threshold: float = 12.0,
) -> dict[str, int]:
    from pathlib import Path

    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    catalog = Catalog(Path(library))
    files = list(catalog.iter_files())
    segmented = 0
    kept = 0
    skipped = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Segmentando", total=len(files))
        for file in files:
            existing = catalog.clips_for_file(file.id)
            if existing and not force:
                skipped += 1
                progress.advance(task)
                continue
            intervals = intervals_for_file(
                file, catalog.library, long_threshold=long_threshold
            )
            catalog.replace_clips(file.id, intervals)
            if len(intervals) > 1:
                segmented += 1
            else:
                kept += 1
            progress.advance(task)
    stats = {
        "files": len(files),
        "segmented": segmented,
        "single": kept,
        "skipped": skipped,
        "clips": catalog.clip_count(),
    }
    catalog.close()
    return stats
