"""
Módulo de extracción de texto de PDFs usando métodos nativos y OCR.

Este módulo proporciona la clase OCRExtractor que implementa una estrategia
híbrida para extraer texto de PDFs: primero intenta extracción nativa con PyMuPDF
y si falla o el texto es insuficiente, recurre a OCR con Tesseract.

Maneja PDFs protegidos con contraseña desbloqueándolos con el NIT proporcionado.
"""

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import os
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_fixed

from src.config import OCR_CONFIG
from src.exceptions import ExtractionError


logger = logging.getLogger(__name__)


class OCRExtractor:
    """
    Extractor de texto de archivos PDF usando extracción nativa y OCR.
    
    Esta clase implementa una estrategia de extracción en múltiples pasos:
    1. Verificar si el PDF está protegido con contraseña
    2. Desbloquear el PDF con NIT si es necesario
    3. Intentar extracción nativa con PyMuPDF
    4. Si falla o el texto es insuficiente, usar OCR con Tesseract
    
    Attributes:
        tesseract_path: Ruta opcional al ejecutable de Tesseract
        native_success: Contador de extracciones nativas exitosas
        ocr_fallback: Contador de veces que se usó OCR como fallback
        unlocked_pdfs: Contador de PDFs desbloqueados
    """
    
    def __init__(self, tesseract_path: Optional[str] = None):
        """
        Inicializa el extractor de texto.
        
        Args:
            tesseract_path: Ruta al ejecutable de Tesseract.
                          Si es None, se usa la ruta del PATH del sistema.
        """
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        self.native_success = 0
        self.ocr_fallback = 0
        self.unlocked_pdfs = 0
        
        logger.info("OCRExtractor inicializado")
    
    @retry(stop=stop_after_attempt(2), wait=wait_fixed(3))
    def extract_text(self, pdf_path: str, nit: Optional[str] = None) -> str:
        """
        Extrae texto de un PDF.
        
        Verifica si está protegido y lo desbloquea con NIT si es necesario.
        Intenta primero extracción nativa, fallback a OCR si falla.
        
        Args:
            pdf_path: Ruta al archivo PDF
            nit: NIT para desbloquear PDF si está protegido con contraseña
            
        Returns:
            Texto completo extraído del PDF
            
        Raises:
            ExtractionError: Si el PDF no puede ser desbloqueado o ambos métodos fallan
        """
        working_pdf_path = pdf_path
        
        # 1. Verificar si el PDF está protegido con contraseña
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                if not nit:
                    raise ExtractionError(
                        "PDF protegido con contraseña pero no se proporcionó NIT"
                    )
                # Desbloquear PDF con NIT
                working_pdf_path = self._unlock_pdf(pdf_path, nit)
                self.unlocked_pdfs += 1
                logger.info(f"PDF desbloqueado: {pdf_path} con NIT: {nit}")
        except ImportError:
            logger.warning("pypdf no está instalado, no se puede verificar si el PDF está protegido")
        except Exception as e:
            logger.warning(f"Fallo al verificar protección del PDF: {e}")
        
        # 2. Intentar extracción nativa primero
        try:
            text = self._extract_native(working_pdf_path)
            if len(text.strip()) > OCR_CONFIG['min_text_length']:
                self.native_success += 1
                logger.info(f"Extracción nativa exitosa: {pdf_path}")
                return text
            else:
                logger.debug(
                    f"Texto nativo insuficiente ({len(text.strip())} chars), "
                    f"intentando OCR"
                )
        except Exception as e:
            logger.debug(f"Extracción nativa falló: {e}")
        
        # 3. Fallback a OCR
        try:
            text = self._extract_ocr(working_pdf_path)
            self.ocr_fallback += 1
            logger.info(f"Extracción OCR exitosa: {pdf_path}")
            return text
        except Exception as e:
            error_msg = f"Ambos métodos fallaron para {pdf_path}: {e}"
            logger.error(error_msg)
            raise ExtractionError(error_msg)
    
    def _unlock_pdf(self, pdf_path: str, nit: str) -> str:
        """
        Desbloquea PDF protegido con contraseña usando pypdf.
        
        Args:
            pdf_path: Ruta al PDF protegido
            nit: NIT usado como contraseña
            
        Returns:
            Ruta al PDF desbloqueado
            
        Raises:
            ExtractionError: Si no se puede desbloquear el PDF
        """
        try:
            from pypdf import PdfReader, PdfWriter
            
            reader = PdfReader(pdf_path)
            
            # Intentar desbloquear con el NIT
            if not reader.decrypt(nit):
                raise ExtractionError(
                    f"No se pudo desbloquear PDF con NIT proporcionado: {nit}"
                )
            
            # Crear nuevo PDF desbloqueado
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            
            # Guardar PDF desbloqueado
            unlocked_path = pdf_path.replace('.pdf', '_unlocked.pdf')
            with open(unlocked_path, 'wb') as output_file:
                writer.write(output_file)
            
            logger.debug(f"PDF desbloqueado guardado en: {unlocked_path}")
            return unlocked_path
            
        except ImportError:
            raise ExtractionError("pypdf no está instalado, no se puede desbloquear PDF")
        except Exception as e:
            raise ExtractionError(f"Error desbloqueando PDF: {e}")
    
    def _extract_native(self, pdf_path: str) -> str:
        """
        Extrae texto nativo del PDF usando PyMuPDF.
        
        Args:
            pdf_path: Ruta al archivo PDF
            
        Returns:
            Texto extraído del PDF
            
        Raises:
            Exception: Si falla la extracción
        """
        doc = fitz.open(pdf_path)
        text = ""
        
        try:
            for page in doc:
                text += page.get_text()
        finally:
            doc.close()
        
        return text
    
    def _extract_ocr(self, pdf_path: str) -> str:
        """
        Extrae texto usando OCR (Tesseract) para PDFs escaneados.
        
        Convierte cada página del PDF a imagen y aplica OCR con
        configuración optimizada para español.
        
        Args:
            pdf_path: Ruta al archivo PDF
            
        Returns:
            Texto extraído mediante OCR
            
        Raises:
            Exception: Si falla el OCR
        """
        doc = fitz.open(pdf_path)
        text = ""
        
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Convertir página a imagen con zoom para mejorar calidad
                zoom_factor = OCR_CONFIG['zoom_factor']
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom_factor, zoom_factor))
                img = Image.open(io.BytesIO(pix.tobytes()))
                
                # OCR con Tesseract (configurado para español)
                page_text = pytesseract.image_to_string(
                    img,
                    lang=OCR_CONFIG['language'],
                    config=f'--psm {OCR_CONFIG["psm_mode"]}'
                )
                text += page_text + "\n"
        finally:
            doc.close()
        
        return text
    
    def get_stats(self) -> dict:
        """
        Retorna estadísticas de extracción.
        
        Returns:
            Diccionario con contadores de éxito, fallbacks y PDFs desbloqueados
        """
        return {
            'native_success': self.native_success,
            'ocr_fallback': self.ocr_fallback,
            'unlocked_pdfs': self.unlocked_pdfs,
            'total_extractions': self.native_success + self.ocr_fallback
        }
