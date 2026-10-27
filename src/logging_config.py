"""
Configuración de logging para el sistema RPA CUFE DIAN.

Este módulo configura el sistema de logging para escribir tanto a archivo
como a consola, con formato estandarizado que incluye timestamps y niveles.
"""

import logging
import os
from pathlib import Path
from .config import LOG_CONFIG


def setup_logging():
    """
    Configura el sistema de logging con salida a archivo y consola.
    
    Crea el directorio de logs si no existe y configura handlers para:
    - Archivo: logs/rpa_cufe.log con nivel INFO
    - Consola: stdout con nivel INFO
    
    El formato incluye timestamp, nombre del logger, nivel y mensaje.
    """
    # Crear directorio de logs si no existe
    log_dir = Path(LOG_CONFIG['log_dir'])
    log_dir.mkdir(exist_ok=True)
    
    # Ruta completa al archivo de log
    log_file = log_dir / LOG_CONFIG['log_file']
    
    # Configurar el logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capturar todos los niveles
    
    # Limpiar handlers existentes para evitar duplicados
    root_logger.handlers.clear()
    
    # Formato de log
    formatter = logging.Formatter(
        fmt=LOG_CONFIG['format'],
        datefmt=LOG_CONFIG['date_format']
    )
    
    # Handler para archivo
    file_handler = logging.FileHandler(
        log_file,
        encoding='utf-8',
        mode='a'  # Append mode
    )
    file_handler.setLevel(getattr(logging, LOG_CONFIG['file_level']))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_CONFIG['console_level']))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Log inicial indicando que el sistema de logging está configurado
    logging.info("Sistema de logging configurado correctamente")
    logging.info(f"Archivo de log: {log_file.absolute()}")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger específico para un módulo.
    
    Args:
        name: Nombre del módulo (típicamente __name__)
        
    Returns:
        Logger configurado para el módulo específico
    """
    return logging.getLogger(name)
