"""
Ejemplo de uso de CSVGenerator y MetricsCollector.

Este script demuestra cómo integrar ambos módulos en el flujo del RPA.
"""

import pandas as pd
from src.csv_generator import CSVGenerator
from src.metrics import MetricsCollector


def main():
    """Ejemplo de flujo completo con métricas y generación CSV."""
    
    # Inicializar componentes
    csv_generator = CSVGenerator("./output")
    metrics = MetricsCollector()
    
    # Simular procesamiento de CUFEs
    cufes = ["CUFE001", "CUFE002", "CUFE003", "CUFE004"]
    
    print("Iniciando procesamiento de facturas...\n")
    
    for i, cufe in enumerate(cufes, 1):
        print(f"Procesando {i}/{len(cufes)}: {cufe}")
        
        # Simular fase de descarga
        if cufe == "CUFE003":
            # Simular fallo en descarga
            metrics.record_download_failure(cufe, "Network timeout")
            print(f"  ✗ Descarga falló: Network timeout")
            continue
        else:
            metrics.record_download_success()
            metrics.record_turnstile_success()
            print(f"  ✓ Descarga exitosa")
        
        # Simular fase de extracción
        if cufe == "CUFE004":
            # Simular fallo en extracción
            metrics.record_extraction_failure(cufe, "PDF corrupto")
            print(f"  ✗ Extracción falló: PDF corrupto")
            continue
        else:
            metrics.record_extraction_success()
            print(f"  ✓ Extracción exitosa")
        
        # Simular datos parseados
        df = pd.DataFrame([
            {
                'cufe': cufe,
                'numero_factura': f'F{i:03d}',
                'fecha_emision': '2024-01-15',
                'nit_emisor': '900123456',
                'codigo_producto': 'P001',
                'descripcion_producto': 'Producto Ejemplo',
                'cantidad': 1.0,
                'precio_unitario': 100.0
            }
        ])
        
        csv_generator.add_invoice_data(df)
        print(f"  ✓ Datos agregados al CSV")
        print()
    
    # Generar CSV consolidado
    print("Generando CSV consolidado...")
    csv_path = csv_generator.generate_csv()
    print(f"✓ CSV generado: {csv_path}\n")
    
    # Mostrar resumen de métricas
    metrics.print_summary()
    
    # Obtener resumen programático
    summary = metrics.get_summary()
    print(f"Tiempo total: {summary['total_time_seconds']:.2f}s")
    print(f"Tasa de éxito de descargas: {summary['downloads']['success_rate']:.0%}")
    print(f"Tasa de éxito de extracciones: {summary['extractions']['success_rate']:.0%}")


if __name__ == "__main__":
    main()
