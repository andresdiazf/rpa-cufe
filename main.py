"""
Punto de entrada CLI del sistema RPA CUFE DIAN.

Uso:
    python main.py --input-file example_cufes.txt --nit 900123456
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.config import CHROME_DEBUG_URL
from src.logging_config import setup_logging
from src.rpa_orchestrator import RPAOrchestrator


LOGS_DIR = Path("logs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RPA CUFE DIAN: descarga facturas por CUFE, extrae sus datos y genera un CSV."
    )
    parser.add_argument(
        "--input-file", required=True,
        help="Archivo de texto con un CUFE por línea"
    )
    parser.add_argument(
        "--nit", required=True,
        help="NIT usado en la consulta al portal DIAN y para desbloquear los PDFs"
    )
    parser.add_argument(
        "--output-dir", default="./output",
        help="Directorio de salida para PDFs y CSV (default: ./output)"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Ejecutar el navegador sin interfaz (el portal DIAN lo bloquea; no recomendado)"
    )
    parser.add_argument(
        "--connect-chrome", action="store_true",
        help="Conectarse a un Chrome abierto con iniciar_chrome.bat en vez de "
             "lanzar uno (necesario si Cloudflare rechaza el navegador del RPA)"
    )
    parser.add_argument(
        "--tesseract-path", default=None,
        help="Ruta al ejecutable de Tesseract si no está en el PATH"
    )
    return parser.parse_args()


def print_summary(metrics: dict) -> None:
    print("=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    print(f"Tiempo total:  {metrics['total_time_seconds']:.2f}s")
    print(f"CUFEs:         {metrics['total_cufes']}")

    for label, key in (("Descargas", "downloads"), ("Extracciones", "extractions")):
        data = metrics[key]
        print(f"{label + ':':<14} {data['success']} exitosas, {data['failed']} fallidas "
              f"({data['success_rate']:.0%})")

    print(f"CSV:           {metrics['csv_output_path']}")

    failed = metrics["failed_cufes"]
    if failed:
        print(f"\nCUFEs fallidos ({len(failed)}):")
        for item in failed:
            print(f"  - {item['cufe']} [{item['phase']}]: {item['error']}")
    else:
        print("\nNo hubo CUFEs fallidos")
    print("=" * 60)


def save_metrics(metrics: dict) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOGS_DIR / f"metrics_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    return path


def main() -> int:
    # La consola de Windows puede no soportar los símbolos del progreso
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()

    input_file = Path(args.input_file)
    if not input_file.is_file():
        print(f"Error: el archivo de entrada no existe: {input_file}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    setup_logging()
    logger = logging.getLogger(__name__)

    config = {
        "input_file": str(input_file),
        "output_dir": str(output_dir),
        "nit_prueba": args.nit,
        "headless": args.headless,
        "tesseract_path": args.tesseract_path,
        "cdp_url": CHROME_DEBUG_URL if args.connect_chrome else None,
    }

    try:
        metrics = RPAOrchestrator(config).run()
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nProceso interrumpido por el usuario", file=sys.stderr)
        return 130

    print_summary(metrics)
    metrics_path = save_metrics(metrics)
    print(f"Métricas guardadas en: {metrics_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
