from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def torch_device() -> str:
    """Return the best available torch device name."""
    try:
        import torch
    except ImportError:
        return "cpu"
    forced = os.environ.get("SOUND_ANALYZER_DEVICE", "").strip().lower()
    if forced in {"cpu", "cuda", "mps"}:
        return forced
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
