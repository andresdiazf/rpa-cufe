"""
Módulo orquestador del sistema RPA CUFE DIAN.

Este módulo coordina todos los componentes del sistema para procesar
una lista de CUFEs a través del pipeline completo: resolución de Turnstile,
descarga de PDF, extracción de texto, parsing de datos y generación de CSV.
"""

import logging
from typing import Dict, Any, List
from pathlib import Path
from dataclasses import dataclass

from src.turnstile_solver import TurnstileSolver
from src.pdf_downloader import PDFDownloader
from src.ocr_extractor import OCRExtractor
from src.data_parser import DataParser
from src.csv_generator import CSVGenerator
from src.metrics import MetricsCollector
from src.exceptions import (
    InvalidCUFEError,
    TurnstileSolveError,
    DownloadError,
    NetworkError,
    ExtractionError,
    ParsingError
)


logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """
    Resultado del procesamiento de un CUFE individual.

    Attributes:
        cufe: Código CUFE procesado
        success: True si el procesamiento fue exitoso
        phase: Fase donde ocurrió (download, extraction, parsing, complete)
        error: Descripción del error si falló
    """
    cufe: str
    success: bool
    phase: str
    error: str = None


class RPAOrchestrator:
    """
    Orquestador principal del sistema RPA CUFE DIAN.

    Coordina el flujo completo de procesamiento:
    1. Lee lista de CUFEs desde archivo
    2. Para cada CUFE:
       - Resuelve Cloudflare Turnstile
       - Descarga PDF
       - Extrae texto
       - Parsea datos
       - Acumula en CSV
    3. Genera CSV consolidado
    4. Retorna métricas

    Attributes:
        config: Diccionario de configuración del sistema
        turnstile_solver: Componente de resolución de Turnstile
        pdf_downloader: Componente de descarga de PDFs
        ocr_extractor: Componente de extracción de texto
        data_parser: Componente de parsing de datos
        csv_generator: Componente de generación de CSV
        metrics: Recopilador de métricas
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa el orquestador y todos sus componentes.

        Args:
            config: Diccionario con configuración:
                - input_file: ruta al archivo con lista de CUFEs
                - output_dir: directorio para PDFs y CSV
                - nit_prueba: NIT para consultas y desbloqueo de PDFs
                - headless: modo headless del navegador (default: False)
                - tesseract_path: ruta opcional al ejecutable de Tesseract
                - cdp_url: opcional, conectar a un Chrome abierto con
                  --remote-debugging-port en lugar de lanzar uno
                - progress_callback: callable(index, total, cufe, result) opcional
        """
        self.config = config

        # Extraer configuración
        self.input_file = config['input_file']
        self.output_dir = config['output_dir']
        self.nit_prueba = config['nit_prueba']
        self.headless = config.get('headless', False)
        # Opcional: callable(index, total, cufe, result) invocado antes de cada
        # CUFE (result=None) y después de procesarlo (result=ProcessResult)
        self.progress_callback = config.get('progress_callback')

        logger.info("Inicializando RPAOrchestrator")
        logger.info(f"  Input file: {self.input_file}")
        logger.info(f"  Output dir: {self.output_dir}")
        logger.info(f"  NIT: {self.nit_prueba}")
        logger.info(f"  Headless: {self.headless}")

        # Inicializar componentes
        self.cdp_url = config.get('cdp_url')
        # En un Chrome real conectado el Turnstile suele resolverse solo
        self.turnstile_solver = TurnstileSolver(
            first_click_delay=10 if self.cdp_url else 3
        )
        self.pdf_downloader = PDFDownloader(
            turnstile_solver=self.turnstile_solver,
            download_dir=self.output_dir,
            headless=self.headless,
            cdp_url=self.cdp_url
        )
        self.ocr_extractor = OCRExtractor(
            tesseract_path=config.get('tesseract_path')
        )
        self.data_parser = DataParser()
        self.csv_generator = CSVGenerator(output_dir=self.output_dir)
        self.metrics = MetricsCollector()

        logger.info("Todos los componentes inicializados correctamente")

    def run(self) -> Dict[str, Any]:
        """
        Ejecuta el pipeline completo de procesamiento.

        Lee el archivo de CUFEs y procesa cada uno secuencialmente,
        mostrando progreso en consola. Al finalizar genera el CSV
        consolidado y retorna métricas completas.

        Returns:
            Diccionario con métricas finales:
            {
                'total_cufes': int,
                'successful_downloads': int,
                'failed_downloads': int,
                'successful_extractions': int,
                'failed_extractions': int,
                'total_time_seconds': float,
                'csv_output_path': str,
                'failed_cufes': List[Dict]
            }
        """
        logger.info("="*60)
        logger.info("INICIANDO PROCESO RPA CUFE DIAN")
        logger.info("="*60)

        try:
            # Leer lista de CUFEs
            cufes = self._read_cufes()
            total_cufes = len(cufes)

            logger.info(f"\nTotal de CUFEs a procesar: {total_cufes}\n")
            print(f"\n{'='*60}")
            print(f"Procesando {total_cufes} CUFEs")
            print(f"{'='*60}\n")

            # Procesar cada CUFE
            for index, cufe in enumerate(cufes, start=1):
                print(f"Procesando {index}/{total_cufes}: {cufe}")
                logger.info(f"Procesando CUFE {index}/{total_cufes}: {cufe}")

                self._notify_progress(index, total_cufes, cufe, None)
                result = self._process_single_cufe(cufe)
                self._notify_progress(index, total_cufes, cufe, result)

                if result.success:
                    print(f"  ✓ Completado exitosamente")
                else:
                    print(f"  ✗ Falló en fase '{result.phase}': {result.error}")

                print()  # Línea en blanco para separación

            # Generar CSV consolidado
            logger.info("\nGenerando CSV consolidado...")
            print(f"\n{'='*60}")
            print("Generando CSV consolidado...")

            csv_path = self.csv_generator.generate_csv()

            print(f"CSV generado: {csv_path}")
            print(f"{'='*60}\n")

            # Obtener métricas finales
            metrics_summary = self.metrics.get_summary()
            metrics_summary['csv_output_path'] = csv_path
            metrics_summary['total_cufes'] = total_cufes

            # Agregar contadores de éxito/fallo
            metrics_summary['successful_downloads'] = self.metrics.downloads_success
            metrics_summary['failed_downloads'] = self.metrics.downloads_failed
            metrics_summary['successful_extractions'] = self.metrics.extractions_success
            metrics_summary['failed_extractions'] = self.metrics.extractions_failed

            logger.info("Proceso completado")

            return metrics_summary

        finally:
            # Cerrar navegador en finally para asegurar liberación de recursos
            logger.info("Cerrando navegador...")
            self.pdf_downloader.close()
            logger.info("Recursos liberados")

    def _notify_progress(self, index: int, total: int, cufe: str, result) -> None:
        """Invoca el callback de progreso sin permitir que rompa el pipeline."""
        if not self.progress_callback:
            return
        try:
            self.progress_callback(index, total, cufe, result)
        except Exception as e:
            logger.warning(f"Error en progress_callback: {e}")

    def _read_cufes(self) -> List[str]:
        """
        Lee el archivo de CUFEs y retorna lista limpia.

        Lee el archivo línea por línea, elimina espacios en blanco
        y líneas vacías.

        Returns:
            Lista de códigos CUFE

        Raises:
            FileNotFoundError: Si el archivo no existe
            ValueError: Si el archivo está vacío
        """
        input_path = Path(self.input_file)

        if not input_path.exists():
            raise FileNotFoundError(f"Archivo de entrada no encontrado: {self.input_file}")

        with open(input_path, 'r', encoding='utf-8') as f:
            cufes = [line.strip() for line in f if line.strip()]

        if not cufes:
            raise ValueError(f"Archivo de entrada vacío: {self.input_file}")

        logger.info(f"Leídos {len(cufes)} CUFEs desde {self.input_file}")
        return cufes

    def _process_single_cufe(self, cufe: str) -> ProcessResult:
        """
        Procesa un CUFE individual a través del pipeline completo.

        Ejecuta todas las fases en orden:
        1. Descarga de PDF (incluye resolución de Turnstile)
        2. Extracción de texto
        3. Parsing de datos
        4. Acumulación en CSV

        Registra métricas en cada fase y maneja errores de forma
        robusta para continuar con el siguiente CUFE.

        Args:
            cufe: Código CUFE a procesar

        Returns:
            ProcessResult con información del resultado
        """
        try:
            # Fase 1: Descarga de PDF
            logger.debug(f"  [{cufe}] Fase 1: Descargando PDF")
            try:
                pdf_path = self.pdf_downloader.download_pdf(cufe, self.nit_prueba)
                # Si se descargó el PDF, los Turnstile del flujo se resolvieron
                self.metrics.record_turnstile_success()
                self.metrics.record_download_success()
                logger.info(f"  [{cufe}] PDF descargado: {pdf_path}")
            except InvalidCUFEError as e:
                self.metrics.record_download_failure(cufe, f"CUFE inválido: {str(e)}")
                return ProcessResult(
                    cufe=cufe,
                    success=False,
                    phase="download",
                    error=f"CUFE inválido: {str(e)}"
                )
            except TurnstileSolveError as e:
                self.metrics.record_turnstile_failure(cufe, str(e))
                self.metrics.record_download_failure(cufe, f"Turnstile: {str(e)}")
                return ProcessResult(
                    cufe=cufe,
                    success=False,
                    phase="download",
                    error=f"Error Turnstile: {str(e)}"
                )
            except (DownloadError, NetworkError) as e:
                self.metrics.record_download_failure(cufe, str(e))
                return ProcessResult(
                    cufe=cufe,
                    success=False,
                    phase="download",
                    error=str(e)
                )
            except Exception as e:
                logger.error(f"  [{cufe}] Error inesperado en descarga: {str(e)}", exc_info=True)
                self.metrics.record_download_failure(cufe, f"Error inesperado: {str(e)}")
                return ProcessResult(
                    cufe=cufe,
                    success=False,
                    phase="download",
                    error=f"Error inesperado: {str(e)}"
                )

            # Fase 2: Extracción de texto
            logger.debug(f"  [{cufe}] Fase 2: Extrayendo texto")
            try:
                text = self.ocr_extractor.extract_text(pdf_path, nit=self.nit_prueba)
                self.metrics.record_extraction_success()
                logger.info(f"  [{cufe}] Texto extraído: {len(text)} caracteres")
            except ExtractionError as e:
                self.metrics.record_extraction_failure(cufe, str(e))
                return ProcessResult(
                    cufe=cufe,
                    success=False,
                    phase="extraction",
                    error=str(e)
                )
            except Exception as e:
                logger.error(f"  [{cufe}] Error inesperado en extracción: {str(e)}", exc_info=True)
                self.metrics.record_extraction_failure(cufe, f"Error inesperado: {str(e)}")
                return ProcessResult(
                    cufe=cufe,
                    success=False,
                    phase="extraction",
                    error=f"Error inesperado: {str(e)}"
                )

            # Fase 3: Parsing de datos
            logger.debug(f"  [{cufe}] Fase 3: Parseando datos")
            try:
                df = self.data_parser.parse_invoice(text, cufe)
                logger.info(f"  [{cufe}] Datos parseados: {len(df)} productos")
            except ParsingError as e:
                # Aunque el parsing falle, la extracción fue exitosa
                # No registramos como fallo de extracción
                logger.error(f"  [{cufe}] Error en parsing: {str(e)}")
                self.metrics.record_parsing_failure(cufe, str(e))
                return ProcessResult(
                    cufe=cufe,
                    success=False,
                    phase="parsing",
                    error=str(e)
                )
            except Exception as e:
                logger.error(f"  [{cufe}] Error inesperado en parsing: {str(e)}", exc_info=True)
                self.metrics.record_parsing_failure(cufe, f"Error inesperado: {str(e)}")
                return ProcessResult(
                    cufe=cufe,
                    success=False,
                    phase="parsing",
                    error=f"Error inesperado: {str(e)}"
                )

            # Fase 4: Acumular en CSV
            logger.debug(f"  [{cufe}] Fase 4: Acumulando datos en CSV")
            self.csv_generator.add_invoice_data(df)

            logger.info(f"  [{cufe}] ✓ Procesado exitosamente")
            return ProcessResult(
                cufe=cufe,
                success=True,
                phase="complete",
                error=None
            )

        except Exception as e:
            # Captura de errores no esperados
            logger.error(
                f"  [{cufe}] Error crítico no manejado: {str(e)}",
                exc_info=True
            )
            return ProcessResult(
                cufe=cufe,
                success=False,
                phase="unknown",
                error=f"Error crítico: {str(e)}"
            )
