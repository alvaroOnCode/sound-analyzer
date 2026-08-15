from __future__ import annotations

from pathlib import Path

import numpy as np
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from sound_analyzer.catalog import Catalog
from sound_analyzer.models.clap import embed_file
from sound_analyzer.models.panns import tag_file
from sound_analyzer.taxonomy import LABELS, label_by_prompt, prompts, suggested_filename

LOW_CONFIDENCE = 0.22


def _clap_taxonomy_scores(audio_vec: np.ndarray, text_matrix: np.ndarray) -> list[tuple[str, float]]:
    scores = text_matrix @ audio_vec
    ranked = sorted(zip(prompts(), scores.tolist()), key=lambda item: item[1], reverse=True)
    return ranked


def tag_clip(catalog: Catalog, clip, text_matrix: np.ndarray) -> None:
    path = catalog.abs_path(clip.relpath)
    audio_vec = None
    stored = catalog.conn.execute(
        "SELECT vector, dim FROM embeddings WHERE clip_id = ?", (clip.id,)
    ).fetchone()
    if stored is not None:
        audio_vec = np.frombuffer(stored["vector"], dtype=np.float32, count=int(stored["dim"]))
        norm = np.linalg.norm(audio_vec)
        if norm > 1e-8:
            audio_vec = audio_vec / norm
    if audio_vec is None:
        audio_vec = embed_file(path, start=clip.start_sec, end=clip.end_sec)
        catalog.save_embedding(clip.id, audio_vec)

    clap_ranked = _clap_taxonomy_scores(audio_vec, text_matrix)
    best_prompt, best_score = clap_ranked[0]
    label = label_by_prompt(best_prompt) or LABELS[0]
    category = label.category
    subcategory = label.subcategory
    confidence = float(best_score)

    audioset_tags: list[dict] = []
    try:
        audioset_tags = tag_file(path, start=clip.start_sec, end=clip.end_sec, top_k=6)
    except Exception:
        audioset_tags = []

    tags = [
        {"label": prompt, "score": float(score), "source": "clap"}
        for prompt, score in clap_ranked[:5]
    ] + audioset_tags[:5]

    if confidence < LOW_CONFIDENCE:
        category = "review"
        subcategory = subcategory or "uncertain"

    extra = None
    if audioset_tags:
        extra = audioset_tags[0]["label"]
    elif len(clap_ranked) > 1:
        extra = clap_ranked[1][0]

    ext = Path(clip.relpath).suffix.lower() or ".wav"
    if clip.start_sec > 0.05 or not clip.is_full_file:
        ext = ".wav"
    name = suggested_filename(
        subcategory=subcategory,
        extra_tag=extra,
        duration_ms=clip.duration_ms,
        clip_id=clip.id,
        ext=ext,
    )
    catalog.save_tags(
        clip.id,
        category=category,
        subcategory=subcategory,
        tags=tags,
        suggested_name=name,
        confidence=confidence,
    )


def tag_library(library: Path, *, force: bool = False, limit: int | None = None) -> dict[str, int]:
    from sound_analyzer.models.clap import embed_text

    catalog = Catalog(library)
    if force:
        catalog.conn.execute("UPDATE clips SET tagged = 0")
        catalog.conn.commit()
    clips = list(catalog.iter_clips(missing_tags=True))
    if limit is not None:
        clips = clips[: max(0, limit)]
    text_matrix = embed_text(prompts())
    done = 0
    errors = 0
    first_error: str | None = None
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Etiquetando", total=len(clips))
        for clip in clips:
            try:
                tag_clip(catalog, clip, text_matrix)
                done += 1
            except Exception as exc:
                errors += 1
                if first_error is None:
                    first_error = f"{clip.relpath}: {exc}"
            progress.advance(task)
    catalog.close()
    return {
        "tagged": done,
        "errors": errors,
        "pending": max(0, len(clips) - done),
        "first_error": first_error,
    }
