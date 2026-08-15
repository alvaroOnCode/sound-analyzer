from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from sound_analyzer.paths import resolve_library


def launch_ui(library: Path, *, port: int = 7860, open_browser: bool = True) -> None:
    import uvicorn

    from sound_analyzer.web.server import create_app

    library = resolve_library(library)
    app = create_app(library)
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    print(f"sound-analyzer · {library}\n{url}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
