"""
Módulo de generación de archivos CSV consolidados.

Este módulo proporciona la clase CSVGenerator que consolida todos los datos
extraídos de facturas en un único archivo CSV con timestamp.
"""

import pandas as pd
import logging
from datetime import datetime
from pathlib import Path
from typing import List


logger = logging.getLogger(__name__)


class CSVGenerator:
    """
    Generador de archivos CSV consolidados para datos de facturas.
    
    Acumula DataFrames de facturas individuales y genera un CSV consolidado
    con todas las filas y timestamp en el nombre del archivo.
    
    Attributes:
        output_dir: Directorio donde se guardará el CSV
        invoice_dataframes: Lista de DataFrames acumulados
    """
    
    def __init__(self, output_dir: str):
        """
        Inicializa el generador de CSV.
        
        Args:
            output_dir: Directorio donde se guardará el archivo CSV
        """
        self.output_dir = Path(output_dir)
        self.invoice_dataframes: List[pd.DataFrame] = []
        
        # Asegurar que el directorio existe
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"CSVGenerator inicializado con directorio: {output_dir}")
    
    def add_invoice_data(self, df: pd.DataFrame) -> None:
        """
        Agrega un DataFrame de factura a la lista de acumulación.
        
        Args:
            df: DataFrame con datos de una factura (puede tener múltiples filas
                para múltiples productos)
        """
        if df is not None and not df.empty:
            self.invoice_dataframes.append(df)
            logger.debug(
                f"DataFrame agregado: {len(df)} filas. "
                f"Total acumulado: {len(self.invoice_dataframes)} facturas"
            )
        else:
            logger.warning("Intento de agregar DataFrame vacío o None, ignorado")
    
    def generate_csv(self) -> str:
        """
        Genera el archivo CSV consolidado con todos los datos acumulados.
        
        Consolida todos los DataFrames usando pd.concat() y guarda el resultado
        en un archivo CSV con timestamp en el nombre.
        
        Returns:
            Ruta completa al archivo CSV generado
            
        Notes:
            - Nombre de archivo: facturas_YYYYMMDD_HHMMSS.csv
            - Encoding: UTF-8
            - Delimitador: coma
            - Incluye headers en primera fila
            - Si no hay datos, genera CSV vacío con solo headers
        """
        # Generar timestamp para nombre de archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"facturas_{timestamp}.csv"
        output_path = self.output_dir / filename
        
        # Definir columnas esperadas (orden específico)
        columns = [
            'cufe',
            'numero_factura',
            'fecha_emision',
            'nit_emisor',
            'codigo_producto',
            'descripcion_producto',
            'cantidad',
            'precio_unitario'
        ]
        
        if self.invoice_dataframes:
            # Consolidar todos los DataFrames
            consolidated_df = pd.concat(
                self.invoice_dataframes,
                ignore_index=True
            )
            
            # Asegurar orden de columnas correcto
            consolidated_df = consolidated_df[columns]
            
            # Guardar a CSV
            consolidated_df.to_csv(
                output_path,
                index=False,
                encoding='utf-8',
                sep=','
            )
            
            logger.info(
                f"CSV generado exitosamente: {output_path} "
                f"({len(consolidated_df)} filas, "
                f"{len(self.invoice_dataframes)} facturas)"
            )
        else:
            # Crear CSV vacío con solo headers
            empty_df = pd.DataFrame(columns=columns)
            empty_df.to_csv(
                output_path,
                index=False,
                encoding='utf-8',
                sep=','
            )
            
            logger.warning(
                f"CSV vacío generado (solo headers): {output_path}. "
                f"No se procesaron facturas exitosamente"
            )
        
        return str(output_path)
    
    def get_invoice_count(self) -> int:
        """
        Retorna el número de facturas acumuladas.
        
        Returns:
            Cantidad de DataFrames en la lista de acumulación
        """
        return len(self.invoice_dataframes)
    
    def get_total_rows(self) -> int:
        """
        Retorna el número total de filas acumuladas (productos).
        
        Returns:
            Suma de todas las filas en los DataFrames acumulados
        """
        if not self.invoice_dataframes:
            return 0
        
        return sum(len(df) for df in self.invoice_dataframes)
    
    def clear(self) -> None:
        """
        Limpia todos los datos acumulados.
        
        Útil para reiniciar el generador sin crear una nueva instancia.
        """
        self.invoice_dataframes.clear()
        logger.info("Datos acumulados limpiados")
