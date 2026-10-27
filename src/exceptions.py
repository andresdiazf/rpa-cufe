"""
Jerarquía de excepciones personalizadas para el sistema RPA CUFE DIAN.

Esta módulo define todas las excepciones específicas del dominio que pueden
ocurrir durante el proceso de consulta, descarga y extracción de facturas.
"""


class RPAError(Exception):
    """
    Excepción base para todos los errores del sistema RPA.
    
    Todas las excepciones personalizadas del sistema heredan de esta clase,
    permitiendo capturar todos los errores específicos del RPA con un solo except.
    """
    pass


class TurnstileSolveError(RPAError):
    """
    Error al resolver el desafío de Cloudflare Turnstile.
    
    Se lanza cuando:
    - El timeout de resolución se excede (>60s por defecto)
    - Ocurre un error inesperado durante la resolución
    - El token de Turnstile no se genera correctamente
    """
    pass


class DownloadError(RPAError):
    """
    Error durante la descarga de archivos PDF.
    
    Se lanza cuando:
    - Falla la descarga del PDF después de reintentos
    - El archivo descargado está corrupto
    - Ocurre un error de E/S al guardar el archivo
    """
    pass


class DownloadLinkNotFoundError(DownloadError):
    """
    La página de la factura no tiene el enlace de descarga del PDF.

    Es un fallo determinista (reintentar no lo arregla), por lo que no se reintenta.
    """
    pass


class InvalidCUFEError(RPAError):
    """
    Error cuando el código CUFE no existe o es inválido.
    
    Se lanza cuando:
    - El CUFE no se encuentra en el sistema DIAN
    - El formato del CUFE es incorrecto
    - El portal retorna "No se encontró" o similar
    """
    pass


class NetworkError(RPAError):
    """
    Error de conectividad o problemas de red.
    
    Se lanza cuando:
    - El portal DIAN no está disponible
    - Ocurre timeout en la conexión
    - Falla la conexión después de reintentos con backoff exponencial
    """
    pass


class ExtractionError(RPAError):
    """
    Error durante la extracción de texto del PDF.
    
    Se lanza cuando:
    - No se puede desbloquear un PDF protegido con contraseña
    - Fallan tanto la extracción nativa como OCR
    - El PDF está corrupto o no es válido
    """
    pass


class ParsingError(RPAError):
    """
    Error al parsear y estructurar los datos extraídos.
    
    Se lanza cuando:
    - No se pueden identificar campos críticos (número de factura, NIT, etc.)
    - El formato del documento no coincide con los patrones esperados
    - No se encuentra la tabla de productos
    """
    pass
