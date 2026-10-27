# Implementation Plan: Sistema RPA CUFE DIAN (MVP)

## Overview

Este plan de implementación construye un MVP funcional del sistema RPA CUFE DIAN para demostración en prueba técnica. Se enfoca en funcionalidad core sin testing exhaustivo, priorizando código que funcione sobre código robusto. La implementación es directa y pragmática.

## Tasks

- [x] 1. Setup Completo del Proyecto
  - Crear estructura de directorios: src/, output/, logs/
  - Configurar entorno virtual Python 3.10+
  - Crear requirements.txt con dependencias: playwright, playwright-stealth, PyMuPDF, pypdf, pytesseract, pandas, tenacity
  - Instalar dependencias: `pip install -r requirements.txt`
  - Ejecutar `playwright install chromium`
  - Crear .gitignore para excluir: venv/, output/, logs/, *.pdf, *.pyc, __pycache__/
  - _Requirements: 1.2, 2.1, 3.1, 4.1, 5.1, 6.1_

- [x] 2. Excepciones y Configuración Básica
  - Crear src/exceptions.py con jerarquía de excepciones: RPAError, TurnstileSolveError, DownloadError, InvalidCUFEError, NetworkError, ExtractionError, ParsingError
  - Crear src/config.py con diccionario de configuración y timeouts: TIMEOUTS (page_load: 30s, turnstile_solve: 60s, pdf_download: 60s, ocr_processing: 45s)
  - Configurar logging básico con módulo estándar de Python (archivo + consola)
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 5.7_

- [x] 3. TurnstileSolver y PDFDownloader
  - Crear src/turnstile_solver.py con clase TurnstileSolver
    - Método solve_turnstile() que detecta iframe Turnstile y espera resolución automática
    - Método _simulate_human_behavior() con movimientos aleatorios de mouse
    - Usar playwright-stealth para evasión de detección
    - Rastrear intentos exitosos/fallidos
  - Crear src/pdf_downloader.py con clase PDFDownloader
    - Método _init_browser() con configuración anti-detección (User-Agent, viewport, locale es-CO)
    - Método download_pdf() con decorador @retry (3 intentos, backoff exponencial)
    - Aplicar stealth_sync a cada página
    - Navegar a portal DIAN, resolver primer Turnstile en página inicial
    - Llenar formulario con CUFE y NIT, hacer clic en botón de búsqueda
    - Detectar y resolver segundo Turnstile en página de detalle de factura si está presente
    - Descargar PDF después de resolver segundo Turnstile
    - Detectar CUFEs inválidos con búsqueda de texto "No se encontró"
    - Método close() para liberar recursos
  - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 6.2, 6.4_

- [x] 4. OCRExtractor y DataParser
  - Crear src/ocr_extractor.py con clase OCRExtractor
    - Método extract_text() con decorador @retry (2 intentos)
    - Método _unlock_pdf() usando pypdf para desbloquear PDFs protegidos con contraseña NIT
    - Detectar si PDF está protegido antes de extraer texto
    - Método _extract_native() usando PyMuPDF (fitz)
    - Método _extract_ocr() usando pytesseract con idioma español
    - Estrategia: verificar protección → desbloquear si necesario → intentar nativo → OCR fallback si texto < 50 chars
  - Crear src/data_parser.py con clase DataParser
    - Definir patrones regex en __init__: numero_factura, fecha_emision, nit_emisor, productos_tabla
    - Método parse_invoice() que extrae todos los campos y retorna DataFrame de pandas
    - Métodos auxiliares: _extract_invoice_number(), _extract_emission_date(), _extract_nit(), _extract_products()
    - Normalizar fechas a formato YYYY-MM-DD
    - Crear una fila por producto en el DataFrame
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 6.4_

- [x] 5. CSVGenerator y Métricas Básicas
  - Crear src/csv_generator.py con clase CSVGenerator
    - Método add_invoice_data() para acumular DataFrames en lista
    - Método generate_csv() que usa pd.concat() para consolidar
    - Nombre de archivo con timestamp: facturas_YYYYMMDD_HHMMSS.csv
    - Encoding UTF-8, delimitador coma, incluir headers
    - Manejar caso de CSV vacío (solo headers)
  - Crear src/metrics.py con clase simple MetricsCollector
    - Contadores básicos: downloads_success, downloads_failed, extractions_success, extractions_failed, turnstile_success, turnstile_failed
    - Lista de CUFEs fallidos con fase y error
    - Método get_summary() que retorna diccionario con métricas y tiempo total
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.3, 5.4, 5.5, 5.10, 5.11, 5.12_

- [x] 6. Orquestador y Punto de Entrada
  - Crear src/rpa_orchestrator.py con clase RPAOrchestrator
    - Método __init__() que acepta diccionario de config e inicializa todos los componentes
    - Método run() que lee archivo de CUFEs (un CUFE por línea) y procesa cada uno
    - Método _process_single_cufe() con pipeline completo en try-except
    - Mostrar progreso con print(): "Procesando X/Y: {CUFE}"
    - Registrar métricas en cada fase
    - Al final generar CSV y retornar métricas
    - Cerrar navegador en finally
  - Crear main.py con CLI usando argparse
    - Argumentos: --input-file (requerido), --nit (requerido), --output-dir (default: ./output), --headless (flag)
    - Validar que input-file existe
    - Crear directorios output/ y logs/ si no existen
    - Crear diccionario de config y pasarlo a RPAOrchestrator
    - Mostrar resumen de métricas al finalizar: tiempo total, descargas, extracciones, CUFEs fallidos
    - Guardar métricas en logs/metrics_TIMESTAMP.json
  - Crear example_cufes.txt con 2-3 CUFEs de ejemplo
  - _Requirements: 1.1, 1.2, 1.8, 1.9, 1.10, 1.11, 2.5, 3.7, 5.6, 5.7, 5.9, 5.10, 5.11, 5.12, 6.3, 6.6, 6.7_

- [x] 7. Documentación Básica
  - Actualizar README.md con:
    - Descripción del proyecto y objetivo (MVP para prueba técnica)
    - Requisitos: Python 3.10+, Tesseract OCR instalado
    - Instalación: crear venv, pip install -r requirements.txt, playwright install chromium
    - Uso: comando python main.py con ejemplos
    - Notas sobre Turnstile: playwright-stealth (sin costo), headless=False recomendado, timeout 60s
    - Estructura del proyecto (src/, output/, logs/)
    - Limitaciones conocidas: tasa de éxito Turnstile 70-85%, patrones regex pueden necesitar ajustes
  - Incluir instrucciones para instalar Tesseract en Windows/Linux/Mac
  - _Requirements: 1.1, 1.2, 2.3, 3.1, 4.4, 4.5, 5.6, 6.4_

- [ ] 8. Prueba Manual y Ajustes
  - Ejecutar sistema con example_cufes.txt
  - Verificar que PDFs se descargan en output/
  - Revisar CSV generado: columnas correctas, datos extraídos
  - Revisar logs/metrics_*.json
  - Ajustar patrones regex si es necesario basado en PDFs reales
  - Documentar cualquier problema encontrado y solución aplicada
  - _Requirements: 1.7, 1.10, 3.7, 3.10, 5.3, 5.4, 5.5, 6.7_

## Notes

- **Este es un MVP para demostración técnica**, no código de producción
- **Sin testing automatizado**: El objetivo es funcionalidad básica, no robustez
- **Prioridad: que funcione > que sea perfecto**
- Se usa playwright-stealth (solución gratuita) para resolver Cloudflare Turnstile
- Modo headless=False recomendado para mejor tasa de éxito (80-85% vs 70-75%)
- Timeout de Turnstile es 60s (mayor que servicios de pago)
- Los patrones regex probablemente necesitarán ajustes con PDFs reales de DIAN
- La validación se hace manualmente ejecutando el sistema con CUFEs de ejemplo

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2"] },
    { "id": 2, "tasks": ["3", "5"] },
    { "id": 3, "tasks": ["4"] },
    { "id": 4, "tasks": ["6"] },
    { "id": 5, "tasks": ["7", "8"] }
  ]
}
```
