from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from sound_analyzer import __version__
from sound_analyzer.audio import FFmpegError, play, require_ffmpeg
from sound_analyzer.catalog import Catalog
from sound_analyzer.device import torch_device
from sound_analyzer.paths import resolve_library

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Indexa, busca y organiza librerías de SFX en local.",
)
console = Console()


def _library_arg(library: Optional[Path]) -> Path:
    return resolve_library(library or Path("."))


@app.callback()
def _root() -> None:
    """sound-analyzer."""


@app.command()
def version() -> None:
    """Muestra la versión."""
    console.print(f"sound-analyzer {__version__}")


@app.command()
def scan(
    library: Path = typer.Argument(Path("."), help="Carpeta del banco de sonidos."),
    force: bool = typer.Option(False, "--force", help="Releer archivos aunque no hayan cambiado."),
) -> None:
    """Inventario recursivo de audio (ignora .sound-analyzer/ y organized/)."""
    from sound_analyzer.scan import scan_library

    path = _library_arg(library)
    require_ffmpeg()
    stats = scan_library(path, force=force)
    console.print(
        f"[green]Scan[/green] {path}\n"
        f"  encontrados={stats['found']} añadidos={stats['added']} "
        f"actualizados={stats['updated']} omitidos={stats['skipped']} errores={stats['errors']}"
    )


@app.command()
def segment(
    library: Path = typer.Argument(Path("."), help="Carpeta del banco de sonidos."),
    force: bool = typer.Option(False, "--force", help="Volver a segmentar."),
    long_threshold: float = typer.Option(12.0, "--long", help="Segundos a partir de los que se parte por silencio."),
) -> None:
    """Parte pistas largas por silencio. Los clips son virtuales hasta organize."""
    from sound_analyzer.segment import segment_library

    path = _library_arg(library)
    require_ffmpeg()
    stats = segment_library(path, force=force, long_threshold=long_threshold)
    console.print(
        f"[green]Segment[/green] {path}\n"
        f"  archivos={stats['files']} partidos={stats['segmented']} "
        f"enteros={stats['single']} omitidos={stats['skipped']} clips={stats['clips']}"
    )


@app.command()
def embed(
    library: Path = typer.Argument(Path("."), help="Carpeta del banco de sonidos."),
    force: bool = typer.Option(False, "--force", help="Recalcular embeddings."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Procesar solo N clips (pruebas)."),
) -> None:
    """Genera embeddings CLAP locales."""
    from sound_analyzer.embed import embed_library

    path = _library_arg(library)
    require_ffmpeg()
    console.print(f"Dispositivo: [bold]{torch_device()}[/bold]")
    stats = embed_library(path, force=force, limit=limit)
    console.print(
        f"[green]Embed[/green] {path}\n"
        f"  embeddings={stats['embedded']} errores={stats['errors']} pendientes={stats['pending']}"
    )
    if stats.get("first_error"):
        console.print(f"[red]primer error:[/red] {stats['first_error']}")


@app.command()
def tag(
    library: Path = typer.Argument(Path("."), help="Carpeta del banco de sonidos."),
    force: bool = typer.Option(False, "--force", help="Recalcular tags."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Procesar solo N clips (pruebas)."),
) -> None:
    """Etiqueta clips con CLAP + AudioSet y propone categoría/nombre."""
    from sound_analyzer.tag import tag_library

    path = _library_arg(library)
    require_ffmpeg()
    console.print(f"Dispositivo: [bold]{torch_device()}[/bold]")
    stats = tag_library(path, force=force, limit=limit)
    console.print(
        f"[green]Tag[/green] {path}\n"
        f"  etiquetados={stats['tagged']} errores={stats['errors']} pendientes={stats['pending']}"
    )
    if stats.get("first_error"):
        console.print(f"[red]primer error:[/red] {stats['first_error']}")


@app.command("index")
def index_cmd(
    library: Path = typer.Argument(Path("."), help="Carpeta del banco de sonidos."),
    force: bool = typer.Option(False, "--force", help="Forzar rescan/resegment/reembed/retag."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Limitar embed/tag a N clips."),
) -> None:
    """Pipeline completo: scan + segment + embed + tag."""
    from sound_analyzer.embed import embed_library
    from sound_analyzer.scan import scan_library
    from sound_analyzer.segment import segment_library
    from sound_analyzer.tag import tag_library

    path = _library_arg(library)
    require_ffmpeg()
    console.print(f"Dispositivo: [bold]{torch_device()}[/bold]")
    scan_stats = scan_library(path, force=force)
    console.print(f"scan: {scan_stats}")
    seg_stats = segment_library(path, force=force)
    console.print(f"segment: {seg_stats}")
    embed_stats = embed_library(path, force=force, limit=limit)
    console.print(f"embed: {embed_stats}")
    if embed_stats.get("first_error"):
        console.print(f"[red]primer error embed:[/red] {embed_stats['first_error']}")
    tag_stats = tag_library(path, force=force, limit=limit)
    console.print(f"tag: {tag_stats}")
    if tag_stats.get("first_error"):
        console.print(f"[red]primer error tag:[/red] {tag_stats['first_error']}")
    status(path)


@app.command()
def search(
    query: Optional[str] = typer.Argument(None, help="Descripción del sonido (es o en)."),
    library: Path = typer.Option(Path("."), "--library", "-l", help="Carpeta del banco."),
    top: int = typer.Option(10, "--top", "-n", help="Número de resultados."),
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Acotar a una subcarpeta."),
    ref: Optional[Path] = typer.Option(None, "--ref", help="Audio de referencia."),
    preview: bool = typer.Option(False, "--preview", "-p", help="Reproducir el primer resultado."),
) -> None:
    """Busca en todo el banco, da igual la subcarpeta de origen."""
    from sound_analyzer.search import search_audio, search_text

    path = _library_arg(library)
    if ref is not None:
        hits = search_audio(path, ref.expanduser().resolve(), top=top, folder=folder)
    elif query:
        hits = search_text(path, query, top=top, folder=folder)
    else:
        raise typer.BadParameter("Pasa una consulta o --ref archivo.wav")

    if not hits:
        console.print("[yellow]Sin resultados. ¿Has ejecutado `sound-analyzer index`?[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title=f"Búsqueda en {path}")
    table.add_column("score", justify="right")
    table.add_column("categoría")
    table.add_column("nombre")
    table.add_column("origen")
    table.add_column("tiempo")
    for hit in hits:
        clip = hit.clip
        table.add_row(
            f"{hit.score:.3f}",
            f"{clip.category or '—'}/{clip.subcategory or '—'}",
            clip.suggested_name or "—",
            clip.relpath,
            f"{clip.start_sec:.2f}–{clip.end_sec:.2f}s",
        )
    console.print(table)
    if preview:
        first = hits[0].clip
        catalog = Catalog(path)
        play(catalog.abs_path(first.relpath), start=first.start_sec, duration=first.end_sec - first.start_sec)
        catalog.close()


@app.command()
def ui(
    library: Path = typer.Option(Path("."), "--library", "-l", help="Carpeta del banco."),
    port: int = typer.Option(7860, "--port", help="Puerto local del servidor."),
    no_browser: bool = typer.Option(False, "--no-browser", help="No abrir el navegador al arrancar."),
) -> None:
    """Abre el buscador local en el navegador."""
    from sound_analyzer.ui import launch_ui

    path = _library_arg(library)
    launch_ui(path, port=port, open_browser=not no_browser)


@app.command()
def organize(
    library: Path = typer.Argument(Path("."), help="Carpeta del banco de sonidos."),
    apply: bool = typer.Option(False, "--apply", help="Escribir organized/. Sin esto es dry-run."),
    force: bool = typer.Option(False, "--force", help="Sobrescribir destinos existentes."),
) -> None:
    """Copia/hardlink a organized/{categoria}/{subcategoria}/. No toca originales."""
    from sound_analyzer.organize import apply_organize, plan_organize

    path = _library_arg(library)
    planned = plan_organize(path)
    if not planned:
        console.print("[yellow]Nada que organizar. Ejecuta `index` o `tag` primero.[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title="organized/ (dry-run)" if not apply else "organized/")
    table.add_column("método")
    table.add_column("destino")
    table.add_column("origen")
    for clip, dest, method in planned[:40]:
        table.add_row(method, dest.relative_to(path).as_posix(), clip.relpath)
    console.print(table)
    if len(planned) > 40:
        console.print(f"… y {len(planned) - 40} más")
    console.print(f"Total: {len(planned)} clips")
    if not apply:
        console.print("[cyan]Dry-run. Añade --apply para escribir archivos.[/cyan]")
        return
    require_ffmpeg()
    stats = apply_organize(path, force=force)
    console.print(
        f"[green]Organize[/green] hardlink={stats['hardlink']} copy={stats['copy']} "
        f"extract={stats['extract']} errores={stats['errors']}"
    )


@app.command()
def undo(
    library: Path = typer.Argument(Path("."), help="Carpeta del banco de sonidos."),
) -> None:
    """Elimina lo copiado a organized/. Los originales no se tocan."""
    from sound_analyzer.organize import undo_organize

    path = _library_arg(library)
    stats = undo_organize(path)
    console.print(f"[green]Undo[/green] eliminados={stats['removed']} ya no estaban={stats['missing']}")


@app.command()
def status(
    library: Path = typer.Argument(Path("."), help="Carpeta del banco de sonidos."),
) -> None:
    """Resumen del índice de este banco."""
    path = _library_arg(library)
    catalog = Catalog(path)
    stats = catalog.stats()
    catalog.close()
    console.print(f"[bold]{path}[/bold]")
    console.print(
        f"  archivos={stats['files']} clips={stats['clips']} "
        f"embeddings={stats['embedded']} tags={stats['tagged']} organized={stats['organized']}"
    )
    console.print(f"  dispositivo={torch_device()}")


def main() -> None:
    try:
        app()
    except (FileNotFoundError, NotADirectoryError, FFmpegError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    main()
