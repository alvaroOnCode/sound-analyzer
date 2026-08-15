# sound-analyzer

Indexa, busca y organiza librerías de SFX **en local**, con modelos gratuitos. Multiplataforma: macOS, Windows y Linux.

Se instala **una vez por máquina**. Cada banco de sonidos tiene su propio índice en `.sound-analyzer/` y una vista por categorías en `organized/`. Los archivos originales no se mueven.

## Requisitos

- Python **3.11+** (probado con 3.14 y PyTorch 2.13; 3.12 es la opción más segura)
- [ffmpeg](https://ffmpeg.org/) (`ffmpeg`, `ffprobe` y `ffplay` en el PATH)

```bash
# macOS
brew install ffmpeg python@3.12

# Windows
winget install Gyan.FFmpeg
# o: choco install ffmpeg

# Debian/Ubuntu
sudo apt install ffmpeg
```

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

O con pipx / uv, para un comando global:

```bash
pipx install .
# uv tool install .
```

La primera ejecución descarga CLAP y AST (~1 GB) a la cache del usuario (`~/.cache/sound-analyzer` o `%LOCALAPPDATA%\sound-analyzer`).

## Uso

Apunta a **cualquier carpeta**. Bancos distintos no se mezclan.

```bash
sound-analyzer index "/ruta/Hollywood Edge"
sound-analyzer search "puerta de metal" -l "/ruta/Hollywood Edge"
sound-analyzer ui -l "/ruta/Hollywood Edge"
sound-analyzer organize "/ruta/Hollywood Edge"          # dry-run
sound-analyzer organize "/ruta/Hollywood Edge" --apply  # escribe organized/
```

Comandos sueltos:

| Comando | Qué hace |
| --- | --- |
| `scan` | Inventario recursivo (salta `.sound-analyzer/` y `organized/`) |
| `segment` | Parte pistas largas por silencio (clips virtuales) |
| `embed` | Embeddings CLAP |
| `tag` | Categoría + tags AudioSet/CLAP + nombre sugerido |
| `index` | scan + segment + embed + tag |
| `search` | Búsqueda semántica en todo el banco (`--folder` para acotar, `--ref` por audio) |
| `ui` | Buscador local en el navegador |
| `organize` | Copia/hardlink a `organized/{categoria}/{subcategoria}/` |
| `undo` | Borra lo generado en `organized/` |
| `status` | Resumen del índice |

Sin instalar:

```bash
python -m sound_analyzer index ./assets
```

## Qué se escribe en el banco

```text
Banco/
  1001/                 originales (intactos)
  1002/
  .sound-analyzer/      índice SQLite + embeddings
  organized/
    animals/dogs/
    impacts/metal/
    review/             confianza baja
```

`organize` usa hardlink si el disco lo permite (no duplica GB) y extrae WAV nuevos solo cuando un CD track se partió en varios sonidos.

## Dispositivo

Se elige solo: Apple Silicon → MPS, NVIDIA → CUDA, si no → CPU. Forzar:

```bash
SOUND_ANALYZER_DEVICE=cpu sound-analyzer index ./assets
```
