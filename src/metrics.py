"""
Módulo de recopilación y reporte de métricas del proceso RPA.

Este módulo proporciona la clase MetricsCollector que rastrea contadores
de éxito/fallo para cada fase del proceso y genera reportes resumen.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class FailedCUFE:
    """
    Información sobre un CUFE que falló en alguna fase del proceso.
    
    Attributes:
        cufe: Código CUFE que falló
        phase: Fase en la que ocurrió el fallo (download, extraction, parsing)
        error: Descripción del error
        timestamp: Momento en que ocurrió el error
    """
    cufe: str
    phase: str
    error: str
    timestamp: datetime = field(default_factory=datetime.now)


class MetricsCollector:
    """
    Recopilador de métricas del proceso RPA CUFE DIAN.
    
    Rastrea contadores de éxito/fallo para cada fase del proceso:
    - Descarga de PDFs
    - Resolución de Cloudflare Turnstile
    - Extracción de texto (OCR)
    
    También mantiene una lista de CUFEs fallidos con detalles del error.
    
    Attributes:
        downloads_success: Cantidad de descargas exitosas
        downloads_failed: Cantidad de descargas fallidas
        extractions_success: Cantidad de extracciones exitosas
        extractions_failed: Cantidad de extracciones fallidas
        turnstile_success: Cantidad de resoluciones Turnstile exitosas
        turnstile_failed: Cantidad de resoluciones Turnstile fallidas
        failed_cufes: Lista de CUFEs fallidos con detalles
        start_time: Momento de inicio del proceso
    """
    
    def __init__(self):
        """Inicializa todos los contadores en cero."""
        # Contadores de descarga
        self.downloads_success: int = 0
        self.downloads_failed: int = 0
        
        # Contadores de extracción
        self.extractions_success: int = 0
        self.extractions_failed: int = 0
        
        # Contadores de Cloudflare Turnstile
        self.turnstile_success: int = 0
        self.turnstile_failed: int = 0
        
        # Lista de CUFEs fallidos con detalles
        self.failed_cufes: List[FailedCUFE] = []
        
        # Tiempo de inicio del proceso
        self.start_time: datetime = datetime.now()
        
        logger.info("MetricsCollector inicializado")
    
    def record_download_success(self) -> None:
        """Incrementa contador de descargas exitosas."""
        self.downloads_success += 1
        logger.debug(f"Download success: {self.downloads_success}")
    
    def record_download_failure(self, cufe: str, error: str) -> None:
        """
        Incrementa contador de descargas fallidas y registra el CUFE.
        
        Args:
            cufe: Código CUFE que falló
            error: Descripción del error
        """
        self.downloads_failed += 1
        self.failed_cufes.append(
            FailedCUFE(cufe=cufe, phase="download", error=error)
        )
        logger.debug(f"Download failed: {self.downloads_failed}, CUFE: {cufe}")
    
    def record_extraction_success(self) -> None:
        """Incrementa contador de extracciones exitosas."""
        self.extractions_success += 1
        logger.debug(f"Extraction success: {self.extractions_success}")
    
    def record_extraction_failure(self, cufe: str, error: str) -> None:
        """
        Incrementa contador de extracciones fallidas y registra el CUFE.
        
        Args:
            cufe: Código CUFE que falló
            error: Descripción del error
        """
        self.extractions_failed += 1
        self.failed_cufes.append(
            FailedCUFE(cufe=cufe, phase="extraction", error=error)
        )
        logger.debug(f"Extraction failed: {self.extractions_failed}, CUFE: {cufe}")
    
    def record_parsing_failure(self, cufe: str, error: str) -> None:
        """
        Registra un CUFE cuyo texto se extrajo pero no pudo ser parseado.

        No modifica los contadores de extracción, solo la lista de fallidos.

        Args:
            cufe: Código CUFE que falló
            error: Descripción del error
        """
        self.failed_cufes.append(
            FailedCUFE(cufe=cufe, phase="parsing", error=error)
        )
        logger.debug(f"Parsing failed, CUFE: {cufe}")

    def record_turnstile_success(self) -> None:
        """Incrementa contador de resoluciones Turnstile exitosas."""
        self.turnstile_success += 1
        logger.debug(f"Turnstile success: {self.turnstile_success}")
    
    def record_turnstile_failure(self, cufe: str, error: str) -> None:
        """
        Incrementa contador de resoluciones Turnstile fallidas y registra el CUFE.
        
        Args:
            cufe: Código CUFE que falló
            error: Descripción del error
        """
        self.turnstile_failed += 1
        self.failed_cufes.append(
            FailedCUFE(cufe=cufe, phase="turnstile", error=error)
        )
        logger.debug(f"Turnstile failed: {self.turnstile_failed}, CUFE: {cufe}")
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Genera un resumen completo de todas las métricas.
        
        Returns:
            Diccionario con:
            - total_time_seconds: Tiempo total de ejecución en segundos
            - downloads: Dict con success, failed, total, success_rate
            - extractions: Dict con success, failed, total, success_rate
            - turnstile: Dict con success, failed, total, success_rate
            - failed_cufes: Lista de dicts con cufe, phase, error, timestamp
        """
        end_time = datetime.now()
        total_time = (end_time - self.start_time).total_seconds()
        
        # Calcular totales y tasas de éxito
        downloads_total = self.downloads_success + self.downloads_failed
        downloads_rate = (
            self.downloads_success / downloads_total if downloads_total > 0 else 0.0
        )
        
        extractions_total = self.extractions_success + self.extractions_failed
        extractions_rate = (
            self.extractions_success / extractions_total if extractions_total > 0 else 0.0
        )
        
        turnstile_total = self.turnstile_success + self.turnstile_failed
        turnstile_rate = (
            self.turnstile_success / turnstile_total if turnstile_total > 0 else 0.0
        )
        
        summary = {
            'total_time_seconds': round(total_time, 2),
            'downloads': {
                'success': self.downloads_success,
                'failed': self.downloads_failed,
                'total': downloads_total,
                'success_rate': round(downloads_rate, 2)
            },
            'extractions': {
                'success': self.extractions_success,
                'failed': self.extractions_failed,
                'total': extractions_total,
                'success_rate': round(extractions_rate, 2)
            },
            'turnstile': {
                'success': self.turnstile_success,
                'failed': self.turnstile_failed,
                'total': turnstile_total,
                'success_rate': round(turnstile_rate, 2)
            },
            'failed_cufes': [
                {
                    'cufe': fc.cufe,
                    'phase': fc.phase,
                    'error': fc.error,
                    'timestamp': fc.timestamp.isoformat()
                }
                for fc in self.failed_cufes
            ]
        }
        
        logger.info(f"Resumen de métricas generado: {total_time:.2f}s de ejecución")
        
        return summary
    
    def get_failed_cufes_by_phase(self, phase: str) -> List[FailedCUFE]:
        """
        Retorna lista de CUFEs fallidos filtrados por fase.
        
        Args:
            phase: Fase a filtrar (download, extraction, turnstile)
            
        Returns:
            Lista de FailedCUFE para la fase especificada
        """
        return [fc for fc in self.failed_cufes if fc.phase == phase]
    
    def print_summary(self) -> None:
        """
        Imprime un resumen formateado de las métricas en la consola.
        
        Útil para visualización rápida durante desarrollo o debugging.
        """
        summary = self.get_summary()
        
        print("\n" + "="*60)
        print("RESUMEN DE MÉTRICAS - RPA CUFE DIAN")
        print("="*60)
        
        print(f"\nTiempo total de ejecución: {summary['total_time_seconds']:.2f}s")
        
        print("\n--- DESCARGAS ---")
        print(f"  Exitosas: {summary['downloads']['success']}")
        print(f"  Fallidas: {summary['downloads']['failed']}")
        print(f"  Total: {summary['downloads']['total']}")
        print(f"  Tasa de éxito: {summary['downloads']['success_rate']:.0%}")
        
        print("\n--- EXTRACCIONES ---")
        print(f"  Exitosas: {summary['extractions']['success']}")
        print(f"  Fallidas: {summary['extractions']['failed']}")
        print(f"  Total: {summary['extractions']['total']}")
        print(f"  Tasa de éxito: {summary['extractions']['success_rate']:.0%}")
        
        print("\n--- CLOUDFLARE TURNSTILE ---")
        print(f"  Exitosas: {summary['turnstile']['success']}")
        print(f"  Fallidas: {summary['turnstile']['failed']}")
        print(f"  Total: {summary['turnstile']['total']}")
        print(f"  Tasa de éxito: {summary['turnstile']['success_rate']:.0%}")
        
        if summary['failed_cufes']:
            print(f"\n--- CUFEs FALLIDOS ({len(summary['failed_cufes'])}) ---")
            for fc in summary['failed_cufes']:
                print(f"  • {fc['cufe']} ({fc['phase']}): {fc['error']}")
        else:
            print("\n✓ No hubo CUFEs fallidos")
        
        print("\n" + "="*60 + "\n")
    
    def reset(self) -> None:
        """
        Reinicia todos los contadores y limpia la lista de CUFEs fallidos.
        
        Útil para reutilizar la misma instancia en múltiples ejecuciones.
        """
        self.downloads_success = 0
        self.downloads_failed = 0
        self.extractions_success = 0
        self.extractions_failed = 0
        self.turnstile_success = 0
        self.turnstile_failed = 0
        self.failed_cufes.clear()
        self.start_time = datetime.now()
        
        logger.info("Métricas reiniciadas")
