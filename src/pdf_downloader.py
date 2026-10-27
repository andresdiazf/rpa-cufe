"""
Módulo para descargar PDFs de facturas desde el portal DIAN.

Este módulo implementa PDFDownloader que usa Playwright con playwright-stealth
para navegar el portal DIAN, resolver desafíos de Cloudflare Turnstile y
descargar representaciones gráficas de facturas en formato PDF.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, Page, Download, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log
)

from .exceptions import (
    DownloadError,
    DownloadLinkNotFoundError,
    InvalidCUFEError,
    NetworkError,
    TurnstileSolveError
)
from .config import TIMEOUTS, DIAN_PORTAL_URL, BROWSER_CONFIG, RETRY_CONFIG, LOG_CONFIG
from .turnstile_solver import TurnstileSolver


logger = logging.getLogger(__name__)

# Texto del enlace de descarga en la página de la factura
DOWNLOAD_LINK_SELECTOR = 'a:has-text("Descargar PDF"), button:has-text("Descargar PDF")'


def _is_retryable(error: BaseException) -> bool:
    """Se reintentan los errores transitorios, no los deterministas."""
    return (
        isinstance(error, (NetworkError, DownloadError))
        and not isinstance(error, DownloadLinkNotFoundError)
    )


class PDFDownloader:
    """
    Descarga PDFs de facturas desde el portal DIAN.
    
    Utiliza Playwright con configuración anti-detección y playwright-stealth
    para evadir sistemas de protección. Maneja resolución de Cloudflare Turnstile
    en múltiples puntos del flujo de navegación.
    
    Attributes:
        turnstile_solver: Instancia de TurnstileSolver para resolver CAPTCHAs
        download_dir: Directorio donde guardar los PDFs descargados
        headless: Si True, ejecuta el navegador sin interfaz gráfica
        playwright: Instancia de Playwright
        browser: Instancia del navegador
        context: Contexto del navegador con configuración anti-detección
    """
    
    def __init__(self, 
                 turnstile_solver: TurnstileSolver,
                 download_dir: str,
                 headless: bool = False,
                 cdp_url: Optional[str] = None):
        """
        Inicializa el descargador de PDFs.

        Args:
            turnstile_solver: Instancia de TurnstileSolver
            download_dir: Directorio para PDFs descargados
            headless: Ejecutar navegador sin interfaz gráfica.
                     Nota: headless=False mejora la tasa de éxito de Turnstile
            cdp_url: Si se indica (ej. http://127.0.0.1:9222), en lugar de lanzar
                     un navegador se conecta a un Chrome ya abierto con
                     --remote-debugging-port. Cloudflare rechaza el navegador
                     que lanza Playwright pero acepta un Chrome abierto por el usuario.
        """
        self.turnstile_solver = turnstile_solver
        self.download_dir = download_dir
        self.headless = headless
        self.cdp_url = cdp_url
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None  # pestaña de trabajo, reutilizada entre CUFEs

        # Crear directorio de descarga si no existe
        os.makedirs(download_dir, exist_ok=True)
        
        logger.info(
            f"PDFDownloader inicializado (headless={headless}, download_dir={download_dir})"
        )
    
    def _init_browser(self):
        """
        Inicializa Playwright y navegador con configuración anti-detección.
        
        Configura el navegador Chromium con:
        - Banderas para deshabilitar detección de automatización
        - User-Agent realista
        - Viewport de resolución común
        - Locale y timezone de Colombia
        """
        logger.info("Inicializando navegador Playwright")

        self.playwright = sync_playwright().start()

        if self.cdp_url:
            self._connect_to_chrome()
            return

        # Se prefiere un navegador real instalado (Chrome, luego Edge) porque
        # Turnstile desconfía más del Chromium empaquetado con Playwright
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
        ]
        if not self.headless:
            launch_args.append('--start-maximized')

        for channel in BROWSER_CONFIG['channels']:
            try:
                self.browser = self.playwright.chromium.launch(
                    channel=channel,
                    headless=self.headless,
                    args=launch_args
                )
                logger.info(f"Navegador lanzado: {channel or 'chromium de Playwright'}")
                break
            except Exception as e:
                logger.warning(
                    f"No se pudo lanzar {channel or 'chromium de Playwright'}: "
                    f"{str(e).splitlines()[0]}"
                )

        if not self.browser:
            raise NetworkError("No se pudo lanzar ningún navegador")

        # Sin user_agent forzado: el del navegador real es coherente con su versión
        context_kwargs = dict(
            locale=BROWSER_CONFIG['locale'],
            timezone_id=BROWSER_CONFIG['timezone_id'],
            accept_downloads=True
        )
        if self.headless:
            context_kwargs['viewport'] = BROWSER_CONFIG['viewport']
        else:
            # Con ventana visible no se emula un viewport: con el escalado de
            # pantalla de Windows desajusta las coordenadas del mouse y los clics
            # sobre Turnstile caen fuera del widget
            context_kwargs['no_viewport'] = True
        self.context = self.browser.new_context(**context_kwargs)
        
        logger.info("Navegador inicializado correctamente")
    
    def _connect_to_chrome(self):
        """
        Se conecta a un Chrome real ya abierto con --remote-debugging-port.

        Se reutiliza su contexto por defecto: el navegador, su perfil y su
        configuración los controla el usuario, no Playwright.
        """
        logger.info(f"Conectando a Chrome existente en {self.cdp_url}")
        try:
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
        except Exception as e:
            self.playwright.stop()
            self.playwright = None
            raise NetworkError(
                f"No se pudo conectar a Chrome en {self.cdp_url}. Abre Chrome con "
                f"iniciar_chrome.bat y vuelve a intentar. Detalle: {str(e).splitlines()[0]}"
            )

        if not self.browser.contexts:
            raise NetworkError("El Chrome conectado no tiene ninguna ventana abierta")

        self.context = self.browser.contexts[0]
        logger.info(f"Conectado a Chrome {self.browser.version}")

    @retry(
        stop=stop_after_attempt(RETRY_CONFIG['max_attempts']),
        wait=wait_exponential(
            multiplier=RETRY_CONFIG['backoff_multiplier'],
            min=RETRY_CONFIG['backoff_min'],
            max=RETRY_CONFIG['backoff_max']
        ),
        retry=retry_if_exception(_is_retryable),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True  # propagar el error real y no un RetryError opaco
    )
    def download_pdf(self, cufe: str, nit: str) -> str:
        """
        Descarga PDF para un CUFE específico.
        
        Flujo:
        1. Navegar a portal DIAN
        2. Resolver primer Cloudflare Turnstile (si está presente en página inicial)
        3. Llenar formulario con CUFE y NIT
        4. Enviar formulario
        5. Resolver segundo Turnstile en página de detalle (si está presente)
        6. Verificar que el CUFE es válido
        7. Descargar PDF
        
        Args:
            cufe: Código CUFE de la factura
            nit: NIT del emisor
            
        Returns:
            Ruta completa al PDF descargado
            
        Raises:
            DownloadError: Si falla después de reintentos
            InvalidCUFEError: Si CUFE no existe
            TurnstileSolveError: Si Turnstile no se resuelve después de timeout
            NetworkError: Si hay problemas de conectividad
        """
        if not self.browser:
            self._init_browser()
        
        page = self._get_page()

        logger.info(f"Iniciando descarga de PDF para CUFE: {cufe}")
        
        try:
            # 1. Navegar a portal DIAN
            logger.debug(f"Navegando a {DIAN_PORTAL_URL}")
            try:
                page.goto(
                    DIAN_PORTAL_URL,
                    # "networkidle" nunca se alcanza: el portal mantiene peticiones
                    # abiertas (Turnstile) y el DOM ya está listo tras domcontentloaded
                    wait_until="domcontentloaded",
                    timeout=TIMEOUTS['page_load'] * 1000
                )
            except PlaywrightTimeoutError as e:
                logger.error(f"Timeout navegando al portal DIAN: {str(e)}")
                raise NetworkError(f"Timeout navegando al portal DIAN: {str(e)}")
            except Exception as e:
                logger.error(f"Error navegando al portal DIAN: {str(e)}")
                raise NetworkError(f"Error de red: {str(e)}")
            
            # 2. Resolver primer Cloudflare Turnstile (si está presente en página inicial)
            logger.debug("Verificando primer Turnstile en página inicial")
            turnstile_resolved = self.turnstile_solver.solve_turnstile(page)
            
            if not turnstile_resolved:
                raise TurnstileSolveError(
                    f"Primer Turnstile no se resolvió después de {self.turnstile_solver.timeout}s"
                )
            
            # 3. Llenar formulario con CUFE y NIT
            logger.debug(f"Llenando formulario con CUFE={cufe}, NIT={nit}")
            try:
                page.fill('#DocumentKey', cufe)
                # El campo del NIT se muestra solo cuando DocumentKey tiene texto
                page.wait_for_selector('#SearchDocumentNit', state='visible', timeout=10000)
                page.fill('#SearchDocumentNit', nit)
            except Exception as e:
                logger.error(f"Error llenando formulario: {str(e)}")
                raise DownloadError(f"Error llenando formulario: {str(e)}")
            
            # 4. Enviar formulario
            logger.debug("Enviando formulario de búsqueda")
            try:
                # El botón no declara type="submit" (lo es por defecto), así que
                # se identifica por su clase
                # El clic navega a la página de resultados. Se espera esa navegación
                # y no solo "domcontentloaded": la página vieja ya está cargada y
                # esa espera terminaría al instante. ("networkidle" no se alcanza
                # en el portal.)
                with page.expect_navigation(
                    wait_until="domcontentloaded",
                    timeout=TIMEOUTS['page_load'] * 1000
                ):
                    page.click('#search-document-form button.search-document', timeout=10000)
            except PlaywrightTimeoutError as e:
                logger.error(f"Timeout esperando respuesta del formulario: {str(e)}")
                raise NetworkError(f"Timeout esperando respuesta: {str(e)}")
            except Exception as e:
                logger.error(f"Error enviando formulario: {str(e)}")
                raise DownloadError(f"Error enviando formulario: {str(e)}")
            
            # 5. Resolver segundo Turnstile en página de detalle (si está presente)
            logger.debug("Verificando segundo Turnstile en página de detalle")
            second_turnstile_resolved = self.turnstile_solver.solve_turnstile(page)
            
            if not second_turnstile_resolved:
                raise TurnstileSolveError(
                    f"Segundo Turnstile no se resolvió después de {self.turnstile_solver.timeout}s"
                )
            
            # 6. Verificar si CUFE es válido
            logger.debug("Verificando validez del CUFE")
            page_content = page.content()
            
            if "No se encontraron resultados" in page_content or "No se encontró" in page_content:
                logger.warning(f"CUFE inválido o no encontrado: {cufe}")
                raise InvalidCUFEError(f"CUFE {cufe} no existe en el sistema DIAN")
            
            # 7. Localizar el enlace "Descargar PDF" de la página de la factura
            logger.debug("Descargando archivo PDF")
            link = page.locator(DOWNLOAD_LINK_SELECTOR).first
            try:
                link.wait_for(state='visible', timeout=15000)
            except PlaywrightTimeoutError:
                self._log_download_diagnostics(page)
                raise DownloadLinkNotFoundError(
                    "No se encontró el enlace 'Descargar PDF' en la página de la factura"
                )

            href = link.get_attribute('href')
            logger.info(f"Enlace de descarga encontrado (href={href})")

            # Guardar con nombre único
            pdf_path = os.path.join(self.download_dir, f"{cufe}.pdf")

            try:
                try:
                    with page.expect_download(timeout=TIMEOUTS['pdf_download'] * 1000) as download_info:
                        link.click(timeout=10000)
                        # El portal avisa en un modal que el PDF tiene contraseña
                        # (el NIT) y la descarga empieza al aceptarlo
                        self._accept_download_modal(page)
                    download_info.value.save_as(pdf_path)
                except PlaywrightTimeoutError:
                    # El clic no inició una descarga (p. ej. abre el visor de PDF):
                    # se pide el archivo directamente con la sesión del navegador
                    if not href or href.startswith(('#', 'javascript:')):
                        raise
                    logger.info("El clic no inició una descarga, pidiendo el PDF por su URL")
                    response = page.context.request.get(urljoin(page.url, href))
                    content_type = response.headers.get('content-type', '').lower()
                    if not response.ok or 'pdf' not in content_type:
                        raise DownloadError(
                            f"La URL de descarga no devolvió un PDF "
                            f"(estado {response.status}, tipo '{content_type}')"
                        )
                    with open(pdf_path, 'wb') as f:
                        f.write(response.body())

                logger.info(f"PDF descargado exitosamente: {pdf_path}")
                self._return_to_search(page)
                return pdf_path

            except DownloadError:
                raise
            except PlaywrightTimeoutError as e:
                logger.error(f"Timeout descargando PDF: {str(e)}")
                raise DownloadError(f"Timeout descargando PDF: {str(e)}")
            except Exception as e:
                logger.error(f"Error descargando PDF: {str(e)}")
                raise DownloadError(f"Error descargando PDF: {str(e)}")
            
        except Exception:
            # La pestaña se reutiliza entre CUFEs; si el fallo la dejó cerrada se descarta
            if page.is_closed():
                self.page = None
            raise

    def _get_page(self) -> Page:
        """Retorna la pestaña de trabajo, creándola la primera vez."""
        if self.page is None or self.page.is_closed():
            self.page = self.context.new_page()

            # playwright-stealth solo aplica al navegador lanzado por Playwright;
            # en un Chrome real conectado por CDP no hace falta
            if not self.cdp_url:
                Stealth().apply_stealth_sync(self.page)
        return self.page

    def _return_to_search(self, page: Page) -> None:
        """
        Vuelve a la página de consulta tras descargar el PDF, lista para el
        siguiente documento. Usa el enlace "Volver" de la factura y, si no
        funciona, navega directamente al portal. Un fallo aquí no invalida
        la descarga ya hecha.
        """
        try:
            back = page.locator('a:has-text("Volver")').first
            try:
                with page.expect_navigation(
                    wait_until="domcontentloaded",
                    timeout=TIMEOUTS['page_load'] * 1000
                ):
                    back.click(timeout=10000)
            except PlaywrightTimeoutError:
                logger.info("El enlace 'Volver' no funcionó, navegando al portal")
                page.goto(
                    DIAN_PORTAL_URL,
                    wait_until="domcontentloaded",
                    timeout=TIMEOUTS['page_load'] * 1000
                )
            page.wait_for_selector('#DocumentKey', state='visible', timeout=15000)
            logger.info("De vuelta en la página de consulta")
        except Exception as e:
            logger.warning(f"No se pudo volver a la página de consulta: {str(e)}")

    @staticmethod
    def _accept_download_modal(page: Page) -> None:
        """
        Acepta el modal que aparece tras pulsar "Descargar PDF".

        Si no aparece en pocos segundos se continúa: en ese caso la descarga
        pudo iniciarse directamente con el clic en el enlace.
        """
        accept = page.locator('.modal:visible').locator(
            'button:has-text("Aceptar"), a:has-text("Aceptar")'
        ).first
        try:
            accept.wait_for(state='visible', timeout=8000)
        except PlaywrightTimeoutError:
            logger.info("No apareció el modal de aceptación, se continúa sin él")
            return
        logger.info("Aceptando el modal de descarga")
        accept.click(timeout=10000)

    @staticmethod
    def _log_download_diagnostics(page: Page) -> None:
        """Registra los enlaces candidatos y guarda una captura de la página de la factura."""
        try:
            candidates = page.evaluate(
                """() => [...document.querySelectorAll('a, button')]
                    .map(e => ({tag: e.tagName, text: (e.innerText || e.value || '').trim().slice(0, 40),
                                href: e.getAttribute('href')}))
                    .filter(e => /pdf|descarg|download/i.test(e.text + ' ' + (e.href || '')))"""
            )
            logger.error(f"Enlaces de descarga candidatos en {page.url}: {candidates}")

            log_dir = Path(LOG_CONFIG['log_dir'])
            log_dir.mkdir(exist_ok=True)
            path = log_dir / f"descarga_fallo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            page.screenshot(path=str(path))
            logger.error(f"Captura guardada en: {path}")
        except Exception as e:
            logger.debug(f"No se pudo registrar el diagnóstico: {str(e)}")

    def close(self):
        """
        Cierra el navegador y libera recursos.
        
        Debe llamarse al finalizar el uso del PDFDownloader para
        evitar fugas de recursos.
        """
        logger.info("Cerrando navegador y liberando recursos")

        # La pestaña de trabajo queda abierta en la página de consulta en el Chrome
        # del usuario, o se cierra junto con el contexto si el navegador es del RPA
        self.page = None

        if self.cdp_url:
            # El Chrome es del usuario: solo se suelta la conexión, no se cierra
            self.context = None
            self.browser = None
        else:
            if self.context:
                self.context.close()
                self.context = None

            if self.browser:
                self.browser.close()
                self.browser = None
        
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        
        logger.info("Recursos liberados correctamente")
