from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from sound_analyzer.audio import load_audio
from sound_analyzer.device import torch_device
from sound_analyzer.paths import hf_home

CLAP_MODEL_ID = "laion/clap-htsat-unfused"
CLAP_SR = 48000
CHUNK_SECONDS = 10.0


def _configure_hf_cache() -> None:
    import os

    home = str(hf_home())
    os.environ.setdefault("HF_HOME", home)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", home)


@lru_cache(maxsize=1)
def load_clap():
    _configure_hf_cache()
    import torch
    from transformers import ClapModel, ClapProcessor

    device = torch_device()
    processor = ClapProcessor.from_pretrained(CLAP_MODEL_ID)
    model = ClapModel.from_pretrained(CLAP_MODEL_ID)
    model.to(device)
    model.eval()
    return processor, model, device


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm < 1e-8:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def _as_feature_tensor(features):
    import torch

    if torch.is_tensor(features):
        return features
    pooled = getattr(features, "pooler_output", None)
    if pooled is not None and torch.is_tensor(pooled):
        return pooled
    raise TypeError(f"CLAP devolvió un tipo inesperado: {type(features)}")


def embed_text(texts: list[str]) -> np.ndarray:
    import torch

    processor, model, device = load_clap()
    inputs = processor(text=texts, return_tensors="pt", padding=True)
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        features = _as_feature_tensor(model.get_text_features(**inputs))
    arr = features.detach().cpu().numpy().astype(np.float32)
    return np.vstack([_l2_normalize(row) for row in arr])


def embed_audio_array(samples: np.ndarray, sample_rate: int = CLAP_SR) -> np.ndarray:
    import torch

    processor, model, device = load_clap()
    if samples.size == 0:
        return np.zeros((512,), dtype=np.float32)
    max_len = int(CHUNK_SECONDS * sample_rate)
    chunks = []
    if samples.shape[0] <= max_len:
        chunks.append(samples)
    else:
        hop = max_len
        for start in range(0, samples.shape[0], hop):
            piece = samples[start : start + max_len]
            if piece.shape[0] < int(0.4 * sample_rate):
                break
            chunks.append(piece)
    vectors = []
    for chunk in chunks:
        try:
            inputs = processor(audio=[chunk], sampling_rate=sample_rate, return_tensors="pt")
        except TypeError:
            inputs = processor(audios=[chunk], sampling_rate=sample_rate, return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            features = _as_feature_tensor(model.get_audio_features(**inputs))
        vectors.append(features.detach().cpu().numpy().reshape(-1))
    mean = np.mean(np.vstack(vectors), axis=0)
    return _l2_normalize(mean)


def embed_file(
    path: Path,
    *,
    start: float = 0.0,
    end: float | None = None,
) -> np.ndarray:
    duration = None if end is None else max(0.0, end - start)
    samples, sr = load_audio(path, sr=CLAP_SR, start=start, duration=duration)
    return embed_audio_array(samples, sr)
