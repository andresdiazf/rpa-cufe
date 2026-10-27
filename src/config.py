"""
Configuración centralizada para el sistema RPA CUFE DIAN.

Este módulo contiene todos los valores de configuración, timeouts y constantes
utilizadas por el sistema.
"""

# Timeouts en segundos para las diferentes operaciones del sistema
TIMEOUTS = {
    # Tiempo máximo para cargar una página web
    'page_load': 30,
    
    # Tiempo máximo para resolver Cloudflare Turnstile
    # Nota: Turnstile puede tardar 20-40 segundos en modo automático sin servicios de pago
    'turnstile_solve': 60,

    # Tiempo máximo para que aparezca el widget Turnstile tras cargar la página
    'turnstile_detect': 10,

    # Tiempo máximo para descargar un archivo PDF
    'pdf_download': 60,
    
    # Tiempo máximo para procesar un PDF con OCR
    'ocr_processing': 45,
}

# URL del portal DIAN
DIAN_PORTAL_URL = "https://catalogo-vpfe.dian.gov.co/User/SearchDocument"

# Configuración del navegador para evasión de detección
BROWSER_CONFIG = {
    'viewport': {'width': 1920, 'height': 1080},
    # Navegadores a intentar en orden; None es el Chromium de Playwright
    'channels': ['chrome', 'msedge', None],
    'locale': 'es-CO',
    'timezone_id': 'America/Bogota',
}

# Dirección de depuración remota del Chrome que abre iniciar_chrome.bat
CHROME_DEBUG_URL = "http://127.0.0.1:9222"

# Configuración de reintentos
RETRY_CONFIG = {
    'max_attempts': 3,
    'backoff_multiplier': 1,
    'backoff_min': 2,
    'backoff_max': 10,
}

# Configuración de OCR
OCR_CONFIG = {
    'language': 'spa',  # Español
    'psm_mode': '6',    # Assume uniform block of text
    'zoom_factor': 2,   # Factor de zoom para mejorar calidad de imagen en OCR
    'min_text_length': 50,  # Mínimo de caracteres para considerar extracción nativa exitosa
}

# Configuración de logging
LOG_CONFIG = {
    'log_dir': 'logs',
    'log_file': 'rpa_cufe.log',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'date_format': '%Y-%m-%d %H:%M:%S',
    'file_level': 'INFO',
    'console_level': 'INFO',
}

# Configuración de salida CSV
CSV_CONFIG = {
    'encoding': 'utf-8',
    'delimiter': ',',
    'include_headers': True,
    'timestamp_format': '%Y%m%d_%H%M%S',
}
