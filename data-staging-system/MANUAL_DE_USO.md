# Manual de Uso: Asistente de Importación de Datos

Este documento describe el flujo de trabajo utilizando el **Asistente de Importación (Import Wizard)**, una interfaz gráfica paso a paso diseñada para garantizar la calidad e integridad de los datos.

## Flujo de Trabajo (4 Pasos)

### Paso 1: Carga y Selección (Upload & Select Table)
1.  **Seleccionar Archivo**: Arrastre o seleccione su archivo `.csv` o `.xlsx`.
    *   *Nota*: El sistema analizará automáticamente el separador y la codificación (UTF-8, Latin-1, etc.).
2.  **Schema & Table**: Seleccione el esquema (ej: `public`, `m8_schema`) y la tabla destino en la base de datos.
3.  Click en **"Analyze File"** para avanzar.

### Paso 2: Mapeo de Columnas (Map Columns)
En este paso se alinean las columnas del archivo con las de la base de datos.

*   **Auto-Mapeo**: El sistema intentará emparejar columnas por nombre automáticamente.
*   **Mapeo Manual**: Use los desplegables para asignar columnas.
*   **Columnas Requeridas**: Las columnas marcadas con `*` son obligatorias (NOT NULL en base de datos).
*   **Toggle**: Use el switch para incluir/excluir columnas de la importación.

### Paso 3: Previsualización y Validación (Preview & Validate)
El sistema carga una muestra de los primeros 100 registros y aplica validaciones:

*   **Tipos de Dato**: Verifica si textos, números y fechas coinciden con el destino.
*   **Restricciones**: Comprueba `NOT NULL`, longitudes máximas, etc.
*   **Resumen**: Revise el cuadro de "Validation Stats" (Filas Válidas vs Inválidas).
*   *Acción*: Si hay muchos errores, puede volver atrás (Back) para corregir el mapeo o arreglar su archivo origen.

### Paso 4: Procesamiento (Process to Staging)
Inicia la carga masiva.

1.  **Status**: Verá una barra de progreso en tiempo real.
2.  **Resultado**: Al finalizar, verá el total de registros insertados en `Staging`.
3.  **Registros Rechazados**: Si hubo filas con errores, podrá descargar un CSV con el detalle (`Download Rejected`).

### Paso 5: Promoción (Promote to Production)
Una vez los datos están en Staging y validados:

1.  El sistema verificará duplicados si se configuró (Deduplicación).
2.  Click en **"Promote to Production"** para mover los datos finales.
3.  Los datos se insertarán en la tabla productiva y se limpiarán de Staging.

---

## Solución de Problemas Frecuentes

*   **Error de Fecha**: Asegúrese de que sus fechas estén en formato ISO (`YYYY-MM-DD`) o estándar (`DD/MM/YYYY`).
*   **Encoding**: Si ve caracteres extraños (ñ, tildes), convierta su CSV a `UTF-8` antes de subirlo.
*   **Timeout**: Para archivos mayores a 1 millón de filas, el proceso puede tardar. No cierre la pestaña hasta que el Worker confirme la recepción.
