"""
Módulo para resolver desafíos de Cloudflare Turnstile en el portal DIAN.

Este módulo implementa TurnstileSolver que usa playwright-stealth para evadir
detección de bots y espera a que Cloudflare Turnstile se resuelva automáticamente
en modo pasivo (sin servicios de pago).
"""

import time
import random
import logging
from datetime import datetime
from pathlib import Path
from playwright.sync_api import Page, Error as PlaywrightError

from .exceptions import TurnstileSolveError
from .config import TIMEOUTS, LOG_CONFIG


logger = logging.getLogger(__name__)


class TurnstileSolver:
    """
    Resuelve desafíos de Cloudflare Turnstile usando técnicas de evasión de detección.
    
    En lugar de usar servicios de pago, este componente usa playwright-stealth
    para evitar detección de bots y espera a que Turnstile se resuelva automáticamente
    en modo pasivo.
    
    Attributes:
        timeout: Tiempo máximo de espera en segundos (default: 60)
        successful_solves: Contador de resoluciones exitosas
        failed_solves: Contador de resoluciones fallidas
    """
    
    def __init__(self, timeout: int = None, first_click_delay: float = 3):
        """
        Inicializa el solver de Turnstile.

        Args:
            timeout: Tiempo máximo de espera en segundos.
                    Si es None, usa el valor de config.TIMEOUTS['turnstile_solve']
            first_click_delay: Segundos de espera antes del primer clic. En un
                    Chrome real el widget suele resolverse solo, así que conviene
                    darle tiempo antes de pulsarlo.
        """
        self.timeout = timeout if timeout is not None else TIMEOUTS['turnstile_solve']
        self.first_click_delay = first_click_delay
        self.successful_solves = 0
        self.failed_solves = 0
        
        logger.info(f"TurnstileSolver inicializado con timeout de {self.timeout}s")
    
    def solve_turnstile(self, page: Page) -> bool:
        """
        Espera a que Cloudflare Turnstile se resuelva automáticamente.
        
        Estrategia:
        1. Detectar si hay un iframe de Turnstile
        2. Simular comportamiento humano (movimientos de mouse, delays)
        3. Esperar a que el token cf-turnstile-response se genere
        4. Verificar que el token es válido (longitud > 0)
        
        Args:
            page: Instancia de Page de Playwright ya navegada al portal DIAN
            
        Returns:
            True si se resolvió exitosamente, False si ocurrió timeout
            
        Raises:
            TurnstileSolveError: Si ocurre un error inesperado
        """
        try:
            logger.debug("Verificando presencia de Cloudflare Turnstile")

            # El widget se inyecta unos segundos después de cargar el DOM, así que
            # se espera un tiempo antes de concluir que no hay Turnstile
            if not self._wait_for_turnstile(page):
                logger.info("No se detectó Cloudflare Turnstile, continuando")
                self.successful_solves += 1
                return True

            if self._has_token(page):
                logger.info("Cloudflare Turnstile ya resuelto")
                self.successful_solves += 1
                return True

            logger.info("Cloudflare Turnstile detectado, iniciando resolución")

            # Simular comportamiento humano
            self._simulate_human_behavior(page)

            # El widget del portal es interactivo: no emite token solo, hay que
            # marcar el checkbox. Se intenta cada pocos segundos hasta el timeout.
            logger.debug(f"Esperando token de Turnstile (timeout: {self.timeout}s)")
            deadline = time.time() + self.timeout
            next_click = time.time() + self.first_click_delay
            clicks = 0

            while time.time() < deadline:
                if self._has_token(page):
                    # Delay adicional para asegurar que el token es estable
                    time.sleep(random.uniform(1, 2))
                    logger.info(f"Cloudflare Turnstile resuelto exitosamente ({clicks} clics)")
                    self.successful_solves += 1
                    return True

                if time.time() >= next_click and clicks < self.MAX_CLICKS:
                    self._click_checkbox(page)
                    clicks += 1
                    next_click = time.time() + 12

                time.sleep(0.5)

            logger.warning(f"Timeout resolviendo Cloudflare Turnstile después de {self.timeout}s")
            self._save_failure_screenshot(page)
            self.failed_solves += 1
            return False

        except Exception as e:
            logger.error(f"Error inesperado resolviendo Cloudflare Turnstile: {str(e)}", exc_info=True)
            self.failed_solves += 1
            raise TurnstileSolveError(f"Error inesperado resolviendo Turnstile: {str(e)}")
    
    # Máximo de clics sobre el checkbox por cada resolución
    MAX_CLICKS = 4

    @staticmethod
    def _turnstile_frame(page: Page):
        """Retorna el frame de Turnstile si existe. page.frames sí ve el iframe
        aunque esté en un shadow DOM cerrado, donde query_selector no llega."""
        for frame in page.frames:
            if 'challenges.cloudflare.com' in frame.url:
                return frame
        return None

    @staticmethod
    def _evaluate(page: Page, expression: str, attempts: int = 4):
        """
        Ejecuta JavaScript en la página tolerando navegaciones en curso.

        Si la página navega mientras se evalúa (por ejemplo, justo después de
        enviar el formulario), el contexto de ejecución se destruye. En ese caso
        se espera a que cargue la página nueva y se reintenta.
        """
        for attempt in range(attempts):
            try:
                return page.evaluate(expression)
            except PlaywrightError as e:
                message = str(e).lower()
                transient = 'context was destroyed' in message or 'navigation' in message
                if not transient or attempt == attempts - 1:
                    raise
                logger.debug("Navegación en curso, esperando a que cargue la página")
                try:
                    page.wait_for_load_state('domcontentloaded', timeout=15000)
                except PlaywrightError:
                    time.sleep(1)

    def _wait_for_turnstile(self, page: Page) -> bool:
        """Espera hasta TIMEOUTS['turnstile_detect'] s a que aparezca el widget."""
        deadline = time.time() + TIMEOUTS['turnstile_detect']
        while True:
            if self._turnstile_frame(page) or self._evaluate(
                page,
                "() => !!document.querySelector('.cf-turnstile, [name=\"cf-turnstile-response\"]')"
            ):
                return True
            if time.time() >= deadline:
                return False
            time.sleep(0.5)

    @staticmethod
    def _has_token(page: Page) -> bool:
        """True si el campo cf-turnstile-response ya contiene un token."""
        return TurnstileSolver._evaluate(
            page,
            """() => {
                const el = document.querySelector('[name="cf-turnstile-response"]');
                return !!(el && (el.value || '').length > 0);
            }"""
        )

    def _click_checkbox(self, page: Page) -> None:
        """
        Pulsa el checkbox del widget moviendo el mouse de forma gradual.

        Se calcula la posición a partir del elemento iframe, porque el contenido
        del widget no es accesible desde la página.
        """
        try:
            frame = self._turnstile_frame(page)
            if not frame:
                logger.debug("Frame de Turnstile aún no disponible para hacer clic")
                return

            box = frame.frame_element().bounding_box()
            if not box:
                logger.debug("Frame de Turnstile sin dimensiones visibles")
                return

            # El checkbox está a la izquierda del widget, centrado en vertical
            x = box['x'] + random.uniform(24, 34)
            y = box['y'] + box['height'] / 2 + random.uniform(-3, 3)

            view = self._evaluate(
                page,
                "() => ({w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio})"
            )
            if not (0 <= x <= view['w'] and 0 <= y <= view['h']):
                logger.warning(
                    f"Widget de Turnstile fuera del viewport ({view['w']}x{view['h']}, "
                    f"dpr={view['dpr']}): clic omitido en ({x:.0f}, {y:.0f})"
                )
                return

            page.mouse.move(x - random.randint(80, 200), y - random.randint(40, 120),
                            steps=random.randint(8, 14))
            page.mouse.move(x, y, steps=random.randint(10, 18))
            time.sleep(random.uniform(0.2, 0.5))
            page.mouse.click(x, y)
            logger.info(
                f"Clic en checkbox de Turnstile en ({x:.0f}, {y:.0f}); "
                f"widget en x={box['x']:.0f} y={box['y']:.0f} "
                f"{box['width']:.0f}x{box['height']:.0f}; "
                f"viewport {view['w']}x{view['h']} dpr={view['dpr']}"
            )
        except Exception as e:
            logger.warning(f"No se pudo hacer clic en Turnstile: {str(e)}")

    @staticmethod
    def _save_failure_screenshot(page: Page) -> None:
        """Guarda una captura de la página para diagnosticar por qué no se resolvió."""
        try:
            log_dir = Path(LOG_CONFIG['log_dir'])
            log_dir.mkdir(exist_ok=True)
            path = log_dir / f"turnstile_timeout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            page.screenshot(path=str(path))
            logger.warning(f"Captura del fallo de Turnstile guardada en: {path}")
        except Exception as e:
            logger.debug(f"No se pudo guardar la captura: {str(e)}")

    def _simulate_human_behavior(self, page: Page):
        """
        Simula comportamiento humano para evitar detección.
        
        Técnicas:
        - Movimientos aleatorios del mouse
        - Delays variables entre acciones
        - Scroll ocasional
        
        Args:
            page: Instancia de Page de Playwright
        """
        logger.debug("Simulando comportamiento humano")
        
        try:
            # Movimientos aleatorios del mouse
            for _ in range(random.randint(3, 5)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                page.mouse.move(x, y)
                time.sleep(random.uniform(0.1, 0.3))
            
            # Scroll aleatorio (simular que el usuario está leyendo)
            if random.random() > 0.5:
                page.mouse.wheel(0, random.randint(100, 300))
                time.sleep(random.uniform(0.5, 1))
            
            # Delay principal (esperar como un humano)
            time.sleep(random.uniform(2, 4))
            
        except Exception as e:
            # No lanzar excepción si falla la simulación, solo registrar
            logger.debug(f"Error simulando comportamiento humano: {str(e)}")
    
    def get_success_rate(self) -> float:
        """
        Calcula la tasa de éxito de resoluciones de Turnstile.
        
        Returns:
            Tasa de éxito entre 0.0 y 1.0.
            Retorna 0.0 si no se han intentado resoluciones.
        """
        total = self.successful_solves + self.failed_solves
        if total == 0:
            return 0.0
        
        success_rate = self.successful_solves / total
        logger.debug(f"Tasa de éxito de Turnstile: {success_rate:.2%} ({self.successful_solves}/{total})")
        return success_rate
