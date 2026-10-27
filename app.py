"""
Interfaz web local del sistema RPA CUFE DIAN.

Permite registrar los CUFEs y el NIT, ejecutar el RPA y ver el progreso y los
resultados desde el navegador. Solo escucha en 127.0.0.1.

Uso:
    python app.py
    # abrir http://127.0.0.1:8000
"""

import json
import logging
import re
import sys
import threading
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

from src.config import CHROME_DEBUG_URL
from src.logging_config import setup_logging
from src.rpa_orchestrator import RPAOrchestrator


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

REGISTRO_FILE = DATA_DIR / "registro.json"
CUFES_RUN_FILE = DATA_DIR / "cufes_run.txt"

HOST = "127.0.0.1"
PORT = 8000
MAX_PREVIEW_ROWS = 200

logger = logging.getLogger(__name__)
app = Flask(__name__)

_lock = threading.Lock()
_state = {
    "status": "idle",   # idle | running | done | error
    "total": 0,
    "current": 0,
    "items": [],        # [{cufe, status: pending|running|ok|failed, phase, error}]
    "metrics": None,
    "csv_name": None,
    "rows": [],
    "error": None,
}


def parse_cufes(raw: str) -> list:
    """Separa por líneas, comas o espacios y elimina duplicados conservando el orden."""
    seen = {}
    for token in re.split(r"[\s,;]+", raw or ""):
        token = token.strip()
        if token:
            seen.setdefault(token, None)
    return list(seen)


def load_registro() -> dict:
    try:
        return json.loads(REGISTRO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"nit": "", "cufes": "", "headless": False, "connect_chrome": False}


def save_registro(nit: str, cufes_raw: str, headless: bool, connect_chrome: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRO_FILE.write_text(
        json.dumps({"nit": nit, "cufes": cufes_raw, "headless": headless,
                    "connect_chrome": connect_chrome},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _run_job(cufes: list, nit: str, headless: bool, connect_chrome: bool) -> None:
    """Ejecuta el RPA en un hilo aparte y va actualizando el estado compartido."""

    def on_progress(index, total, cufe, result):
        with _lock:
            item = _state["items"][index - 1]
            if result is None:
                item["status"] = "running"
                _state["current"] = index
            else:
                item["status"] = "ok" if result.success else "failed"
                item["phase"] = result.phase
                item["error"] = result.error

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CUFES_RUN_FILE.write_text("\n".join(cufes) + "\n", encoding="utf-8")

        orchestrator = RPAOrchestrator({
            "input_file": str(CUFES_RUN_FILE),
            "output_dir": str(OUTPUT_DIR),
            "nit_prueba": nit,
            "headless": headless,
            "cdp_url": CHROME_DEBUG_URL if connect_chrome else None,
            "progress_callback": on_progress,
        })
        metrics = orchestrator.run()

        csv_path = Path(metrics["csv_output_path"])
        rows = (
            pd.read_csv(csv_path, dtype=str).fillna("")
            .head(MAX_PREVIEW_ROWS).to_dict("records")
        )

        with _lock:
            _state.update(status="done", metrics=metrics, csv_name=csv_path.name, rows=rows)
    except Exception as e:
        logger.error(f"Fallo la ejecución desde la interfaz web: {e}", exc_info=True)
        with _lock:
            _state.update(status="error", error=str(e))


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/registro")
def get_registro():
    return jsonify(load_registro())


@app.post("/api/registro")
def post_registro():
    body = request.get_json(silent=True) or {}
    save_registro(
        str(body.get("nit", "")).strip(),
        str(body.get("cufes", "")),
        bool(body.get("headless", False)),
        bool(body.get("connect_chrome", False)),
    )
    return jsonify(ok=True)


@app.post("/api/run")
def run():
    body = request.get_json(silent=True) or {}
    nit = str(body.get("nit", "")).strip()
    cufes_raw = str(body.get("cufes", ""))
    headless = bool(body.get("headless", False))
    connect_chrome = bool(body.get("connect_chrome", False))
    cufes = parse_cufes(cufes_raw)

    if not nit:
        return jsonify(error="Falta el NIT"), 400
    if not cufes:
        return jsonify(error="Registra al menos un CUFE"), 400

    with _lock:
        if _state["status"] == "running":
            return jsonify(error="Ya hay una ejecución en curso"), 409
        _state.update(
            status="running", total=len(cufes), current=0, metrics=None,
            csv_name=None, rows=[], error=None,
            items=[{"cufe": c, "status": "pending", "phase": None, "error": None}
                   for c in cufes],
        )

    save_registro(nit, cufes_raw, headless, connect_chrome)
    threading.Thread(
        target=_run_job, args=(cufes, nit, headless, connect_chrome), daemon=True
    ).start()
    return jsonify(ok=True, total=len(cufes))


@app.get("/api/status")
def status():
    with _lock:
        return jsonify(_state)


@app.get("/api/csv/<name>")
def download_csv(name: str):
    if not name.lower().endswith(".csv"):
        return jsonify(error="Archivo no permitido"), 404
    return send_from_directory(OUTPUT_DIR, name, as_attachment=True)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)
    setup_logging()

    print(f"Interfaz disponible en http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, threaded=True, debug=False)


if __name__ == "__main__":
    main()
