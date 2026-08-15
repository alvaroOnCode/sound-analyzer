from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_dir

INDEX_DIRNAME = ".sound-analyzer"
ORGANIZED_DIRNAME = "organized"
APP_NAME = "sound-analyzer"


def resolve_library(path: Path) -> Path:
    library = path.expanduser().resolve()
    if not library.exists():
        raise FileNotFoundError(f"No existe la carpeta: {library}")
    if not library.is_dir():
        raise NotADirectoryError(f"No es una carpeta: {library}")
    return library


def index_dir(library: Path) -> Path:
    folder = library / INDEX_DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def organized_dir(library: Path) -> Path:
    return library / ORGANIZED_DIRNAME


def cache_dir() -> Path:
    folder = Path(user_cache_dir(APP_NAME, appauthor=False))
    folder.mkdir(parents=True, exist_ok=True)
    hf = folder / "hf"
    hf.mkdir(parents=True, exist_ok=True)
    return folder


def hf_home() -> Path:
    return cache_dir() / "hf"
