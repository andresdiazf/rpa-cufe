"""
Módulo de parsing y estructuración de datos de facturas.

Este módulo proporciona la clase DataParser que extrae campos específicos
del texto de facturas usando patrones regex y estructura los datos en
DataFrames de pandas.

Los patrones están calibrados con la "Representación Gráfica" que genera la
DIAN (Solución Gratuita). En ese PDF cada celda de la tabla de productos sale
en su propia línea y los números usan formato colombiano (75.000,00).
"""

import re
import pandas as pd
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from src.exceptions import ParsingError


logger = logging.getLogger(__name__)


# Cantidad y precio llevan siempre decimales con coma (1,00 / 75.000,00). Exigir la
# coma evita confundirlos con una unidad de medida numérica, como 94
_DECIMAL = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d+$|^\d+,\d+$')
# Unidad de medida: código corto (NAR, NIU, 94...)
_UNIT = re.compile(r'^[A-Za-z0-9]{1,4}$')


class DataParser:
    """
    Parser de datos de facturas electrónicas.

    Extrae campos específicos del texto de facturas usando patrones regex:
    - Número de factura
    - Fecha de emisión
    - NIT del emisor
    - Tabla de productos (código, descripción, cantidad, precio unitario)

    Estructura los datos en un DataFrame de pandas con una fila por producto.
    """

    def __init__(self):
        """
        Inicializa el parser con patrones regex para extracción de campos.
        """
        self.patterns = {
            # "Número de Factura:   FEBQ-243564"
            'numero_factura': r'N[uú]mero\s+de\s+Factura\s*:?\s*([A-Za-z0-9-]+)',

            # "Fecha de Emisión:   05/11/2024" (también acepta AAAA-MM-DD)
            'fecha_emision': (
                r'Fecha\s+de\s+Emisi[oó]n\s*:?\s*'
                r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})'
            ),

            # "Nit del Emisor:   800033723". Debe ser el del emisor: el PDF trae
            # otros NIT (el del generador del PDF, el del proveedor tecnológico)
            'nit_emisor': r'Nit\s+del\s+Emisor\s*:?\s*([\d.\-]+)',

            # Sección de la tabla; puede repetirse en cada hoja de la factura
            'productos_tabla': (
                r'Detalles\s+de\s+Productos(.*?)'
                r'(?=Descuentos\s+y\s+Recargos|Notas\s+Finales|Datos\s+Totales|\Z)'
            ),
        }

        logger.info("DataParser inicializado con patrones regex")

    def parse_invoice(self, text: str, cufe: str) -> pd.DataFrame:
        """
        Parsea texto de factura y extrae campos requeridos.

        Args:
            text: Texto completo extraído del PDF
            cufe: Código CUFE (para incluir en datos de salida)

        Returns:
            DataFrame con columnas:
            - cufe: str
            - numero_factura: str
            - fecha_emision: str (formato YYYY-MM-DD)
            - nit_emisor: str
            - codigo_producto: str
            - descripcion_producto: str
            - cantidad: float
            - precio_unitario: float

            Si hay múltiples productos, retorna múltiples filas.

        Raises:
            ParsingError: Si campos críticos no pueden ser extraídos
        """
        try:
            # Extraer campos del documento
            numero_factura = self._extract_invoice_number(text)
            fecha_emision = self._extract_emission_date(text)
            nit_emisor = self._extract_nit(text)

            # Extraer productos
            products = self._extract_products(text)

            if not products:
                raise ParsingError("No se encontraron productos en la factura")

            # Crear DataFrame con una fila por producto
            rows = []
            for product in products:
                rows.append({
                    'cufe': cufe,
                    'numero_factura': numero_factura,
                    'fecha_emision': fecha_emision,
                    'nit_emisor': nit_emisor,
                    'codigo_producto': product['codigo'],
                    'descripcion_producto': product['descripcion'],
                    'cantidad': product['cantidad'],
                    'precio_unitario': product['precio_unitario']
                })

            df = pd.DataFrame(rows)
            logger.info(
                f"Factura parseada exitosamente: {numero_factura}, "
                f"{len(products)} productos"
            )
            return df

        except Exception as e:
            error_msg = f"Error parseando factura {cufe}: {e}"
            logger.error(error_msg)
            raise ParsingError(error_msg)

    def _extract_invoice_number(self, text: str) -> str:
        """
        Extrae número de factura del texto.

        Args:
            text: Texto de la factura

        Returns:
            Número de factura

        Raises:
            ParsingError: Si no se encuentra el número de factura
        """
        match = re.search(self.patterns['numero_factura'], text, re.IGNORECASE)
        if match:
            invoice_number = match.group(1).strip()
            logger.debug(f"Número de factura extraído: {invoice_number}")
            return invoice_number

        raise ParsingError("Número de factura no encontrado")

    def _extract_emission_date(self, text: str) -> str:
        """
        Extrae fecha de emisión del texto y la normaliza a formato YYYY-MM-DD.

        Args:
            text: Texto de la factura

        Returns:
            Fecha de emisión en formato YYYY-MM-DD

        Raises:
            ParsingError: Si no se encuentra la fecha de emisión
        """
        match = re.search(self.patterns['fecha_emision'], text, re.IGNORECASE)
        if match:
            date_str = match.group(1)

            # Intentar varios formatos comunes de fecha
            date_formats = [
                '%d/%m/%Y',
                '%d-%m-%Y',
                '%d/%m/%y',
                '%d-%m-%y',
                '%Y/%m/%d',
                '%Y-%m-%d'
            ]

            for fmt in date_formats:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    normalized_date = date_obj.strftime('%Y-%m-%d')
                    logger.debug(f"Fecha de emisión extraída: {normalized_date}")
                    return normalized_date
                except ValueError:
                    continue

            # Si ningún formato funciona, retornar la fecha original
            logger.warning(
                f"No se pudo normalizar fecha: {date_str}, "
                f"retornando formato original"
            )
            return date_str

        raise ParsingError("Fecha de emisión no encontrada")

    def _extract_nit(self, text: str) -> str:
        """
        Extrae NIT del emisor del texto.

        Args:
            text: Texto de la factura

        Returns:
            NIT del emisor, sin puntos

        Raises:
            ParsingError: Si no se encuentra el NIT
        """
        match = re.search(self.patterns['nit_emisor'], text, re.IGNORECASE)
        if match:
            nit = match.group(1).strip().replace('.', '')
            logger.debug(f"NIT del emisor extraído: {nit}")
            return nit

        raise ParsingError("NIT del emisor no encontrado")

    def _extract_products(self, text: str) -> List[Dict]:
        """
        Extrae la tabla de productos del texto.

        La tabla "Detalles de Productos" sale con una celda por línea:
        Nro., Código, Descripción (puede ocupar varias líneas), U/M, Cantidad,
        Precio unitario y luego descuentos, recargos e impuestos. Puede
        continuar en las hojas siguientes.

        Args:
            text: Texto de la factura

        Returns:
            Lista de diccionarios con codigo, descripcion, cantidad y precio_unitario

        Raises:
            ParsingError: Si no se encuentran productos
        """
        products: List[Dict] = []

        sections = re.finditer(
            self.patterns['productos_tabla'], text, re.IGNORECASE | re.DOTALL
        )
        for section in sections:
            products.extend(self._parse_product_section(section.group(1)))

        if not products:
            raise ParsingError("No se pudieron extraer productos de la factura")

        logger.info(f"Total de productos extraídos: {len(products)}")
        return products

    def _parse_product_section(self, section: str) -> List[Dict]:
        """Recorre las celdas de una sección de la tabla fila por fila."""
        # raw conserva los espacios de cada línea (necesarios para unir descripciones
        # partidas) y tokens es la misma lista sin ellos, para comparar
        raw = [line for line in section.splitlines() if line.strip()]
        tokens = [line.strip() for line in raw]

        # La fila 1 empieza en el primer número entero después del encabezado
        header_end = next(
            (k for k, token in enumerate(tokens) if token.lower().startswith('nro')),
            None
        )
        if header_end is None:
            return []

        i = header_end + 1
        while i < len(tokens) and not tokens[i].isdigit():
            i += 1

        products: List[Dict] = []
        while i < len(tokens) and tokens[i].isdigit():
            parsed = self._parse_product_row(tokens, raw, i)
            if parsed is None:
                break
            product, i = parsed
            products.append(product)
            logger.debug(f"Producto extraído: {product['codigo']}")

            # Saltar descuentos, recargos e impuestos hasta el Nro. de la siguiente fila
            next_nro = str(int(product['nro']) + 1)
            while i < len(tokens) and tokens[i] != next_nro:
                i += 1

        for product in products:
            product.pop('nro')
        return products

    def _parse_product_row(
        self, tokens: List[str], raw: List[str], i: int
    ) -> Optional[Tuple[Dict, int]]:
        """
        Parsea una fila que empieza en tokens[i] (el Nro.).

        Returns:
            (producto, índice del siguiente token) o None si no tiene la forma esperada
        """
        if i + 1 >= len(tokens):
            return None

        nro = tokens[i]

        # El código suele ir solo en su celda, pero en algunas facturas llega en la
        # misma línea que el inicio de la descripción ("85121701 CONSULTA DE...")
        codigo = tokens[i + 1]
        description_lines: List[str] = []
        first_word, _, rest = raw[i + 1].strip().partition(' ')
        if rest:
            if first_word.isalnum() and any(c.isdigit() for c in first_word):
                codigo = first_word
                description_lines.append(raw[i + 1].replace(first_word, '', 1))
            else:
                # Sin código: la celda ya es la primera línea de la descripción
                codigo = ''
                description_lines.append(raw[i + 1])

        # La descripción llega hasta la unidad de medida, que va seguida de
        # cantidad y precio unitario
        j = i + 2
        while j + 2 < len(tokens):
            if (_UNIT.match(tokens[j])
                    and _DECIMAL.match(tokens[j + 1])
                    and _DECIMAL.match(tokens[j + 2])):
                break
            description_lines.append(raw[j])
            j += 1
        else:
            return None

        try:
            product = {
                'nro': nro,
                'codigo': codigo,
                'descripcion': self._join_description(description_lines),
                'cantidad': self._to_number(tokens[j + 1]),
                'precio_unitario': self._to_number(tokens[j + 2]),
            }
        except ValueError as e:
            logger.warning(f"Error procesando fila de producto {nro}: {e}")
            return None

        return product, j + 3

    @staticmethod
    def _join_description(lines: List[str]) -> str:
        """
        Une las líneas de una descripción partida por el ancho de la celda.

        La celda parte el texto cada N caracteres, a veces a media palabra
        (UNILATERA|L) y a veces justo después de un espacio ("SUERO |U OTRO").
        Las líneas crudas conservan ese espacio, así que se unen tal cual.
        """
        return re.sub(r'\s+', ' ', ''.join(lines)).strip()

    @staticmethod
    def _to_number(value: str) -> float:
        """
        Convierte un número en formato colombiano (75.000,00) a float.

        Si viene en formato inglés (75,000.00), donde el último separador es
        el punto, también se interpreta correctamente.
        """
        if ',' in value and '.' in value and value.rfind('.') > value.rfind(','):
            return float(value.replace(',', ''))
        return float(value.replace('.', '').replace(',', '.'))
