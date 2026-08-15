from __future__ import annotations

from pathlib import Path

from sound_analyzer.catalog import Catalog
from sound_analyzer.paths import resolve_library
from sound_analyzer.search import search_audio, search_text


def launch_ui(library: Path, *, port: int = 7860) -> None:
    import gradio as gr

    library = resolve_library(library)

    def do_search(query: str, reference, top: int, folder: str):
        folder_arg = folder.strip() or None
        if reference is not None:
            hits = search_audio(library, Path(reference), top=int(top), folder=folder_arg)
        elif query and query.strip():
            hits = search_text(library, query.strip(), top=int(top), folder=folder_arg)
        else:
            return [], "Escribe una descripción o sube un audio de referencia."
        rows = []
        for hit in hits:
            clip = hit.clip
            tags = ", ".join(tag["label"] for tag in clip.tags[:4]) or "—"
            rows.append(
                [
                    f"{hit.score:.3f}",
                    clip.category or "—",
                    clip.subcategory or "—",
                    tags,
                    f"{clip.start_sec:.2f}–{clip.end_sec:.2f}s",
                    clip.relpath,
                    clip.suggested_name or "—",
                    clip.id,
                ]
            )
        return rows, f"{len(hits)} resultados en {library}"

    def preview(evt: gr.SelectData, table):
        if table is None or evt.index is None:
            return None
        row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        try:
            clip_id = int(table[row_idx][-1])
        except (IndexError, TypeError, ValueError):
            return None
        catalog = Catalog(library)
        clip = catalog.get_clip(clip_id)
        if clip is None:
            catalog.close()
            return None
        src = catalog.abs_path(clip.relpath)
        if clip.is_full_file:
            catalog.close()
            return str(src)
        from sound_analyzer.audio import extract_wav
        from sound_analyzer.paths import index_dir

        dest = index_dir(library) / "preview" / f"clip_{clip.id}.wav"
        extract_wav(src, dest, start=clip.start_sec, duration=clip.end_sec - clip.start_sec)
        catalog.close()
        return str(dest)

    with gr.Blocks(title="sound-analyzer") as demo:
        gr.Markdown(
            f"## sound-analyzer\nLibrería: `{library}`\n\n"
            "Busca por descripción (español o inglés) o por un audio de referencia. "
            "Los originales no se mueven; `organize` crea `organized/`."
        )
        with gr.Row():
            query = gr.Textbox(label="Descripción", placeholder="puerta de metal, perro ladrando, whoosh…")
            reference = gr.Audio(label="Audio de referencia", type="filepath")
        with gr.Row():
            top = gr.Slider(3, 30, value=10, step=1, label="Resultados")
            folder = gr.Textbox(label="Filtrar subcarpeta (opcional)", placeholder="1002")
            search_btn = gr.Button("Buscar", variant="primary")
        status = gr.Markdown()
        table = gr.Dataframe(
            headers=["score", "categoría", "subcategoría", "tags", "tiempo", "origen", "nombre sugerido", "id"],
            interactive=False,
            wrap=True,
        )
        player = gr.Audio(label="Preview (clic en una fila)", type="filepath")
        search_btn.click(do_search, [query, reference, top, folder], [table, status])
        query.submit(do_search, [query, reference, top, folder], [table, status])
        table.select(preview, [table], [player])

    demo.launch(server_name="127.0.0.1", server_port=port, inbrowser=True)
