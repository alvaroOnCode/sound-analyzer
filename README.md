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

La primera ejecución descarga los modelos de IA a la cache del usuario (unos **3 GB**, una sola vez, para todos los bancos). En macOS: `~/Library/Caches/sound-analyzer/`. En Linux: `~/.cache/sound-analyzer/`. En Windows: `%LOCALAPPDATA%\sound-analyzer\`.

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

## Dónde se guarda (y qué borrar para liberar espacio)

Hay tres sitios distintos. `index` no llena el disco igual que `organize`. Los mp3/wav originales no se mueven ni se duplican al indexar.

```text
Banco/
  1001/                 originales (intactos)
  1002/
  .sound-analyzer/      índice de ESTE banco (SQLite + embeddings)
  organized/            solo si corriste organize --apply
    animals/dogs/
    ambience/city/
    review/             confianza baja
```

### 1. Índice de cada banco (pequeño)

Dentro de **esa** carpeta de sonidos: `Banco/.sound-analyzer/catalog.sqlite`.

Ahí está el inventario, clips, tags y embeddings. Si copias el banco a un USB, esta carpeta viaja con él. Suele ser unos MB, no GB.

Borrar `.sound-analyzer/` **no borra los sonidos**. Solo olvida el análisis. La próxima vez hay que volver a `index`.

### 2. Modelos de IA (lo gordo, una vez por máquina)

No están dentro del banco. Cache del usuario:

| SO | Ruta |
| --- | --- |
| macOS | `~/Library/Caches/sound-analyzer/` |
| Linux | `~/.cache/sound-analyzer/` |
| Windows | `%LOCALAPPDATA%\sound-analyzer\` |

Unos **3 GB** (CLAP + AudioSet). Se descargan la primera vez y se reutilizan para todos los bancos.

Si los borras, `index` los vuelve a bajar. No toca tus sonidos.

### 3. `organized/` (opcional, puede ser grande)

Solo existe si hiciste `organize --apply`. Es la vista por categorías. Los originales siguen donde estaban.

`organize` usa hardlink si el disco lo permite (casi no duplica GB) y extrae WAV nuevos solo cuando un CD track se partió en varios sonidos.

`sound-analyzer undo /ruta/banco` borra lo de `organized/`. Los CDs originales no se tocan.

Un archivo va a **una sola carpeta**: la categoría con más puntuación. El segundo tag (por ejemplo city dentro de ambience) es subcarpeta: `organized/ambience/city/`. El buscador lo encuentra igual aunque no esté en esa carpeta.

### Qué borrar para liberar espacio

| Quieres… | Borra |
| --- | --- |
| Quitar el análisis de un banco y repetirlo luego | `/tu/banco/.sound-analyzer/` |
| Quitar las carpetas organizadas | `/tu/banco/organized/` o `sound-analyzer undo /tu/banco` |
| Recuperar ~3 GB de modelos (se redescargan) | cache de la tabla de arriba |
| Desinstalar la tool de este repo | la carpeta `.venv` del proyecto |

**No borres** los mp3/wav originales. Eso es la librería, no el índice. El código (`src/`) es pequeño.

## Dispositivo

Se elige solo: Apple Silicon → MPS, NVIDIA → CUDA, si no → CPU. Forzar:

```bash
SOUND_ANALYZER_DEVICE=cpu sound-analyzer index ./assets
```
