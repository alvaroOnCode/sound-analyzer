from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sound_analyzer.catalog import Catalog, ClipRow
from sound_analyzer.models.clap import embed_file, embed_text
from sound_analyzer.taxonomy import expand_query


@dataclass(frozen=True)
class Hit:
    clip: ClipRow
    score: float


def search_text(library: Path, query: str, *, top: int = 10, folder: str | None = None) -> list[Hit]:
    expanded = expand_query(query)
    query_vec = embed_text([expanded])[0]
    return _search_vector(library, query_vec, top=top, folder=folder)


def search_audio(library: Path, reference: Path, *, top: int = 10, folder: str | None = None) -> list[Hit]:
    vector = embed_file(reference)
    return _search_vector(library, vector, top=top, folder=folder)


def _search_vector(
    library: Path, query_vec: np.ndarray, *, top: int, folder: str | None
) -> list[Hit]:
    catalog = Catalog(library)
    ids, matrix = catalog.load_embeddings()
    if matrix.shape[0] == 0:
        catalog.close()
        return []
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms < 1e-8] = 1.0
    matrix = matrix / norms
    scores = matrix @ query_vec
    order = np.argsort(-scores)
    hits: list[Hit] = []
    folder_norm = folder.replace("\\", "/").strip("/") if folder else None
    for idx in order:
        clip = catalog.get_clip(int(ids[idx]))
        if clip is None:
            continue
        if folder_norm and not clip.relpath.replace("\\", "/").startswith(folder_norm):
            continue
        hits.append(Hit(clip=clip, score=float(scores[idx])))
        if len(hits) >= top:
            break
    catalog.close()
    return hits
