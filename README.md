# Data Staging System (v2.0) - Importación de Datos Empresarial

Sistema avanzado de ingesta, validación y promoción de datos. Diseñado para manejar grandes volúmenes de información mediante un **Asistente de Importación de 4 Pasos** que garantiza la calidad de los datos antes de llegar a producción.

## 🚀 Características Principales

*   **Asistente de Importación (Wizard)**: Interfaz paso a paso para carga, mapeo y validación.
*   **Validación Inteligente**: Detección automática de tipos, formatos de fecha y restricciones (NOT NULL, FK).
*   **Mapeo Flexible**: Mapeo visual de columnas origen -> destino, con soporte para valores por defecto.
*   **Procesamiento Asíncrono**: Cola de trabajos robusta para procesar cargas masivas sin bloquear la UI.
*   **Promoción Segura**: Inserción en lotes (Batch Insert) con deduplicación y manejo de transacciones.

## 📋 Requisitos Previos

*   **Python**: 3.10+
*   **PostgreSQL**: 13+
*   **Node.js**: 18+ (Para el Frontend)

## 🛠️ Instalación y Configuración

1.  **Configuración Backend:**
    ```bash
    cd data-staging-system
    python -m venv venv
    .\venv\Scripts\activate  # Windows
    # source venv/bin/activate # Linux/Mac
    pip install -r requirements.txt
    ```

2.  **Configuración Frontend:**
    ```bash
    cd frontend
    npm install
    ```

3.  **Base de Datos:**
    Cree un archivo `.env` en la raíz con su conexión a base de datos:
    ```ini
    DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
    ```

## ▶️ Ejecución del Sistema

El sistema requiere 3 procesos terminales:

1.  **API Backend (FastAPI):**
    ```bash
    python run_app.py
    ```
    *API en: http://localhost:8000*

2.  **Workers (Procesamiento de Fondo):**
    ```bash
    python run_workers.py
    ```

3.  **Frontend (Interfaz React):**
    ```bash
    cd frontend
    npm run dev
    ```
    *UI en: http://localhost:5173* (por defecto)

## 📂 Flujo de Trabajo (Wizard)

1.  **Carga (Upload)**: Carga de archivo y análisis de estructura.
2.  **Mapeo (Map)**: Selección de tabla destino y mapeo de columnas.
3.  **Previsualización (Preview)**: Verificación de datos y corrección de errores de validación.
4.  **Procesamiento (Process)**: Carga a Staging y Promoción a Producción.

## 📖 Documentación

*   **`MANUAL_DE_USO.md`**: Guía detallada del usuario para el Asistente de Importación.
*   Doc API (Swagger): `http://localhost:8000/docs`