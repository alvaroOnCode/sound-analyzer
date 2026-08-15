"""AudioSet tagging via AST (same 527-class ontology as PANNs, transformers-native)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from sound_analyzer.audio import load_audio
from sound_analyzer.device import torch_device
from sound_analyzer.paths import hf_home

AST_MODEL_ID = "MIT/ast-finetuned-audioset-10-10-0.4593"
AST_SR = 16000


def _configure_hf_cache() -> None:
    import os

    home = str(hf_home())
    os.environ.setdefault("HF_HOME", home)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", home)


@lru_cache(maxsize=1)
def load_ast():
    _configure_hf_cache()
    import torch
    from transformers import ASTForAudioClassification, AutoFeatureExtractor

    device = torch_device()
    extractor = AutoFeatureExtractor.from_pretrained(AST_MODEL_ID)
    model = ASTForAudioClassification.from_pretrained(AST_MODEL_ID)
    model.to(device)
    model.eval()
    return extractor, model, device


def tag_audio_array(samples: np.ndarray, sample_rate: int = AST_SR, top_k: int = 8) -> list[dict]:
    import torch
    import torch.nn.functional as F

    extractor, model, device = load_ast()
    if samples.size == 0:
        return []
    inputs = extractor(samples, sampling_rate=sample_rate, return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.sigmoid(logits)[0]
    values, indices = torch.topk(probs, k=min(top_k, probs.shape[0]))
    id2label = model.config.id2label
    tags = []
    for score, idx in zip(values.tolist(), indices.tolist()):
        tags.append(
            {
                "label": id2label[int(idx)],
                "score": float(score),
                "source": "audioset",
            }
        )
    return tags


def tag_file(path: Path, *, start: float = 0.0, end: float | None = None, top_k: int = 8) -> list[dict]:
    duration = None if end is None else max(0.0, end - start)
    # AST was trained on ~10s clips; cap decode for long files.
    if duration is None or duration > 10:
        duration = 10.0
    samples, sr = load_audio(path, sr=AST_SR, start=start, duration=duration)
    return tag_audio_array(samples, sr, top_k=top_k)
