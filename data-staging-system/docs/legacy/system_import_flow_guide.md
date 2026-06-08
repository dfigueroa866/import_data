# Documentación del Flujo de Importación de Datos

> **Legacy — no usar.** Este documento describe el flujo antiguo (BackgroundTasks, COPY a `staging_data.stage_*`, `/api/v1/upload/file` como entrada principal).
>
> **Documentación canónica:** [`../FUNCIONAMIENTO_APLICACION.md`](../FUNCIONAMIENTO_APLICACION.md)

## Introducción
Este documento detalla el funcionamiento estándar del proceso de importación de datos en M8 Connect. Está diseñado para que cualquier usuario, nuevo o experimentado, comprenda cómo viaja la información desde un archivo local hasta la base de datos de producción.

## Diagrama del Flujo General

1.  **Carga (Upload)**: Recepción del archivo CSV.
2.  **Staging (Intermedio)**: Procesamiento asíncrono en bloques.
3.  **Promoción**: Transferencia automática o manual a Producción.

---

## Paso a Paso Detallado

### 1. Carga del Archivo (Upload)
El proceso inicia cuando un usuario o sistema externo envía un archivo para su procesamiento.

*   **Punto de Entrada**: Endpoint de API `/api/v1/upload/file`.
*   **Parámetros Clave**:
    *   `source_name`: Identificador del origen (ej. `sales_transactions`).
    *   `auto_process`: Si es `True`, inicia la ingesta a staging inmediatamente.
    *   `auto_production`: Si es `True`, promueve los datos a producción automáticamente al terminar el staging. (Útil para integraciones vía API automática, en la interfaz visual está desactivado por defecto).
    *   `production_table`: Tabla final de destino.
*   **Acción del Sistema**:
    *   El servidor recibe el archivo y lo guarda en la carpeta `data/uploads/` con un ID único (Batch ID) para evitar colisiones.
    *   *Ejemplo de archivo*: `9967..._sales_data.csv`.

### 2. Procesamiento en Staging (Ingesta Asíncrona)
Una vez guardado el archivo, el sistema libera la conexión del usuario (responde "OK") y comienza el trabajo pesado en segundo plano (Background Task).

*   **División en Bloques (Chunking)**:
    *   Para manejar archivos grandes (millones de registros) sin saturar la memoria, el sistema lee el archivo en "chunks" o bloques de **100,000 registros**.
*   **Inserción Optimizada**:
    *   Utiliza el comando `COPY` de base de datos para una inserción de ultra-alta velocidad en las tablas de "Staging" (ej. `staging_data.stage_sales_transactions`).
*   **Verificación Continua**:
    *   Después de cada bloque, el sistema verifica que los registros sean visibles en la base de datos antes de continuar con el siguiente.

### 3. Promoción a Producción
Esta es la etapa crítica donde los datos pasan de ser "temporales" (Staging) a estar "disponibles" (Producción). En el flujo de la interfaz de usuario, este es un paso de **confirmación manual** que permite revisar los errores antes de hacer efectivos los cambios. Alternativamente, si la carga se hace vía API directa con `auto_production=True`, la promoción sucede automáticamente después de cargar el último bloque.

*   **Procesamiento por Lotes (Batch Processing)**:
    *   Para optimizar el rendimiento y no bloquear la base de datos, la promoción se realiza en **lotes de 5,000 registros**.
    *   El sistema toma 5,000 registros de staging, los transforma al formato final y los inserta en producción en una sola transacción segura.
    *   Si un lote de 5,000 falla, el sistema intenta recuperar o reportar el error específico de ese grupo, sin afectar los datos ya guardados.

*   **Modos de Operación**:
    1.  **Append Only (Solo Agregar)**: Si no se definen columnas de deduplicación, el sistema inserta todos los registros nuevos directamente. Es el método más rápido (Bulk Mode).
    2.  **Deduplicación (Upsert)**: El sistema permite definir **uno o más campos** como clave única (ej. `product_id` o `transaction_id,source_system`).
        *   Si un registro entrante coincide con uno existente en estos campos, el sistema **actualizará** la información del registro existente con la nueva.
        *   Esto garantiza que no haya duplicados basados en los criterios que usted defina.

*   **Tablas Destino**:
    *   Los datos se mueven del esquema `staging_data` al esquema de producción (ej. `m8_schema`).

### 4. Monitoreo y Logs
El usuario puede seguir el progreso del sistema a través de los logs de aplicación o el dashboard de monitoreo.

*   **Indicadores de Éxito**:
    *   Mensajes de *Processed chunk X: 100000 records*.
    *   Mensaje final: *Staging-to-production processing completed*.
*   **Indicadores de Error**:
    *   El sistema está diseñado para detenerse y registrar el error si un bloque falla, asegurando la integridad de los datos.

## Glosario para el Usuario
*   **Batch ID**: Código único que identifica una carga específica. Útil para rastrear errores.
*   **Staging**: Área temporal de "preparación" donde los datos se limpian y validan antes de ser oficiales.
*   **Producción**: Área final donde los datos son consumidos por los reportes y usuarios finales.
