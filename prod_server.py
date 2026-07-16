"""Production entry point — uses waitress (Windows) or gunicorn (Linux/Mac).

Usage:
    python prod_server.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from web_ui.app import app

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
WORKERS = int(os.environ.get("WORKERS", "4"))

if __name__ == "__main__":
    if sys.platform == "win32":
        from waitress import serve
        print(f"Starting production server on http://{HOST}:{PORT} (waitress)")
        serve(app, host=HOST, port=PORT, threads=WORKERS)
    else:
        from gunicorn.app.base import BaseApplication

        class GunicornApp(BaseApplication):
            def __init__(self):
                self.options = {
                    "bind": f"{HOST}:{PORT}",
                    "workers": WORKERS,
                    "timeout": 300,
                }
                super().__init__()

            def load_config(self):
                for k, v in self.options.items():
                    self.cfg.set(k, v)

            def load(self):
                return app

        print(f"Starting production server on http://{HOST}:{PORT} (gunicorn, {WORKERS} workers)")
        GunicornApp().run()
