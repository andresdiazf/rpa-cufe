# Requirements Document

## Introduction

Este documento especifica los requerimientos para un sistema RPA (Robotic Process Automation) que automatiza la consulta y descarga de facturas electrónicas desde el portal de validación de la DIAN (Dirección de Impuestos y Aduanas Nacionales de Colombia), extrae información específica de los documentos y genera un archivo CSV consolidado con los datos extraídos.

## Glossary

- **RPA_System**: El sistema de automatización robótica de procesos que ejecuta todas las operaciones
- **DIAN_Portal**: Portal web de la DIAN en https://catalogo-vpfe.dian.gov.co/User/SearchDocument
- **CUFE**: Código Único de Facturación Electrónica, identificador único de cada factura electrónica
- **Cloudflare_Turnstile**: Sistema de verificación de seguridad usado por el portal DIAN para prevenir accesos automatizados no autorizados
- **CAPTCHA_Solver**: Componente del sistema que resuelve verificaciones de Cloudflare Turnstile
- **PDF_Downloader**: Componente que descarga las representaciones gráficas de las facturas
- **OCR_Extractor**: Componente que extrae texto de imágenes usando tecnología OCR (Optical Character Recognition)
- **Data_Parser**: Componente que procesa y estructura los datos extraídos
- **CSV_Generator**: Componente que genera el archivo CSV con los datos consolidados
- **NIT**: Número de Identificación Tributaria del emisor de la factura

## Requirements

### Requirement 1: Consulta de CUFE y Descarga de PDF

**User Story:** Como usuario del sistema, quiero consultar códigos CUFE en el portal DIAN y descargar automáticamente las representaciones gráficas en PDF, para obtener las facturas electrónicas de manera automatizada.

#### Acceptance Criteria

1. THE RPA_System SHALL aceptar una lista de códigos CUFE como entrada
2. THE RPA_System SHALL aceptar un NIT de prueba como entrada para autenticación
3. WHEN un código CUFE es proporcionado, THE RPA_System SHALL navegar al DIAN_Portal
4. WHEN el formulario de búsqueda es mostrado, THE RPA_System SHALL ingresar el código CUFE y el NIT de prueba
5. WHEN un CUFE válido es encontrado, THE PDF_Downloader SHALL descargar la representación PDF de la factura
6. THE RPA_System SHALL almacenar los PDFs descargados con una convención de nombres que incluya el código CUFE
7. IF un código CUFE es inválido o no es encontrado, THEN THE RPA_System SHALL registrar el error y continuar con el siguiente CUFE
8. WHILE el proceso de descarga está en ejecución, THE RPA_System SHALL reportar el progreso en formato "X/Y archivos procesados"
9. THE RPA_System SHALL reportar el tiempo total empleado para el proceso de descarga
10. WHEN el proceso de descarga finaliza, THE RPA_System SHALL reportar la cantidad total de descargas exitosas versus descargas fallidas
11. WHEN el proceso de descarga finaliza, THE RPA_System SHALL generar una lista de todos los CUFEs que fallaron con la razón específica del error para cada uno

### Requirement 2: Resolución de Cloudflare Turnstile

**User Story:** Como sistema automatizado, necesito resolver la verificación de Cloudflare Turnstile en el portal DIAN, para poder acceder y consultar facturas sin intervención manual.

#### Acceptance Criteria

1. WHEN el DIAN_Portal presenta un desafío de Cloudflare_Turnstile en la página inicial, THE CAPTCHA_Solver SHALL detectarlo
2. WHEN un desafío de Cloudflare_Turnstile es detectado, THE CAPTCHA_Solver SHALL resolverlo automáticamente
3. WHEN el usuario accede a la página de detalle de la factura, THE CAPTCHA_Solver SHALL detectar y resolver un segundo desafío de Cloudflare_Turnstile si está presente
4. THE CAPTCHA_Solver SHALL completar la resolución de cada Cloudflare_Turnstile dentro de 60 segundos
5. IF la resolución de Cloudflare_Turnstile falla después de 3 intentos, THEN THE RPA_System SHALL registrar el fallo y abortar la consulta actual
6. WHEN el Cloudflare_Turnstile es resuelto exitosamente, THE RPA_System SHALL proceder con la consulta del CUFE
7. THE RPA_System SHALL reportar métricas sobre la tasa de éxito de resolución de Cloudflare_Turnstile y el tiempo promedio de resolución

### Requirement 3: Extracción de Datos de Documentos

**User Story:** Como analista de datos, quiero extraer automáticamente información específica de las facturas descargadas, para procesar y analizar los datos sin revisión manual.

#### Acceptance Criteria

1. WHEN un PDF de factura es descargado, THE OCR_Extractor SHALL verificar si el PDF está protegido con contraseña
2. IF el PDF está protegido con contraseña, THEN THE OCR_Extractor SHALL desbloquear el PDF usando el NIT proporcionado como contraseña
3. IF el desbloqueo del PDF falla, THEN THE RPA_System SHALL registrar el error y continuar con el siguiente CUFE
4. WHEN el PDF está desbloqueado o no requiere contraseña, THE OCR_Extractor SHALL extraer texto del documento
5. THE Data_Parser SHALL extraer los siguientes campos de la sección "Datos del Documento": Número de factura, Fecha de emisión
6. THE Data_Parser SHALL extraer el siguiente campo de la sección "Datos del Emisor/Vendedor": NIT del emisor
7. THE Data_Parser SHALL extraer los siguientes campos de la tabla "Detalles del Producto": Código, Descripción, Cantidad, Precio unitario
8. WHEN múltiples productos existen en una factura, THE Data_Parser SHALL crear una fila por producto en los datos de salida
9. THE Data_Parser SHALL crear una estructura de marco de datos para cada factura procesada
10. IF la extracción de texto falla para un PDF, THEN THE RPA_System SHALL registrar el error con el identificador CUFE y continuar procesando
11. WHILE el proceso de extracción está en ejecución, THE RPA_System SHALL reportar el progreso en formato "X/Y archivos procesados"
12. THE RPA_System SHALL reportar métricas sobre la tasa de éxito de extracción y el tiempo de procesamiento por documento
13. WHEN el proceso de extracción finaliza, THE RPA_System SHALL reportar la cantidad total de extracciones exitosas versus extracciones fallidas
14. WHEN el proceso de extracción finaliza, THE RPA_System SHALL generar una lista de todos los CUFEs que fallaron en la extracción con la razón específica del error para cada uno

### Requirement 4: Exportación de Datos a CSV

**User Story:** Como usuario final, quiero recibir todos los datos extraídos en un archivo CSV consolidado, para poder analizar la información en herramientas de análisis de datos.

#### Acceptance Criteria

1. THE CSV_Generator SHALL consolidar todos los datos extraídos en un único archivo CSV
2. THE archivo CSV SHALL contener las siguientes columnas: CUFE, Número de factura, Fecha de emisión, NIT del emisor, Código, Descripción, Cantidad, Precio unitario
3. WHEN una factura contiene múltiples productos, THE CSV_Generator SHALL crear una fila por producto con metadatos de factura repetidos
4. THE CSV_Generator SHALL usar codificación UTF-8 para el archivo de salida
5. THE CSV_Generator SHALL usar coma como delimitador de campos
6. THE CSV_Generator SHALL incluir encabezados en la primera fila
7. THE CSV_Generator SHALL guardar el archivo con una marca de tiempo en el nombre del archivo
8. IF ningún dato fue extraído exitosamente, THEN THE RPA_System SHALL crear un archivo CSV vacío con solo los encabezados

### Requirement 5: Métricas de Proceso y Reportes

**User Story:** Como supervisor del proceso, quiero recibir métricas detalladas sobre el tiempo empleado y las restricciones encontradas, para evaluar el rendimiento del sistema y optimizar el proceso.

#### Acceptance Criteria

1. THE RPA_System SHALL rastrear el tiempo total de ejecución para el proceso completo
2. THE RPA_System SHALL rastrear el tiempo empleado para cada fase: descarga de PDF, resolución de Cloudflare_Turnstile, extracción OCR, análisis de datos, generación de CSV
3. THE RPA_System SHALL rastrear el número de consultas CUFE exitosas versus consultas fallidas
4. THE RPA_System SHALL rastrear el número de descargas PDF exitosas versus descargas fallidas
5. THE RPA_System SHALL rastrear el número de extracciones de datos exitosas versus extracciones fallidas
6. THE RPA_System SHALL generar un reporte resumen con todas las métricas al finalizar la ejecución
7. THE RPA_System SHALL registrar todos los errores con marcas de tiempo e información de contexto
8. THE RPA_System SHALL reportar cualquier limitación de tasa o restricción de acceso encontrada durante la ejecución
9. WHILE cada fase está en ejecución, THE RPA_System SHALL mostrar el progreso en formato "X/Y archivos procesados"
10. WHEN el proceso completo finaliza, THE RPA_System SHALL generar una lista consolidada de todos los CUFEs que fallaron en cualquier fase, con la fase específica y la razón del error para cada uno
11. THE RPA_System SHALL reportar el tiempo total empleado para el proceso completo al finalizar
12. THE RPA_System SHALL reportar contadores finales de éxito versus error para cada fase del proceso

### Requirement 6: Manejo de Errores y Resiliencia

**User Story:** Como operador del sistema, quiero que el RPA maneje errores de manera robusta y continúe procesando, para maximizar la cantidad de datos extraídos incluso cuando algunos documentos fallen.

#### Acceptance Criteria

1. IF el DIAN_Portal no está disponible, THEN THE RPA_System SHALL reintentar la conexión hasta 3 veces con retroceso exponencial
2. IF ocurre un error de red durante la descarga de PDF, THEN THE RPA_System SHALL reintentar la descarga hasta 2 veces
3. WHEN ocurre un error procesando un CUFE específico, THE RPA_System SHALL registrar el error y continuar con el siguiente CUFE en la lista
4. THE RPA_System SHALL implementar controles de tiempo de espera para cada operación: carga de página (30s), descarga (60s), procesamiento OCR (45s)
5. IF el DIAN_Portal retorna una estructura de página inesperada, THEN THE RPA_System SHALL registrar un error estructural con detalles de la página
6. THE RPA_System SHALL terminar de manera ordenada y guardar resultados parciales cuando sea interrumpido
7. WHEN el proceso se completa, THE RPA_System SHALL reportar un resumen de operaciones exitosas y fallidas
