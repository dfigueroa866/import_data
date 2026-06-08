# Instala dependencias del backend en el venv activo
$ErrorActionPreference = "Stop"

Write-Host "Instalando dependencias de M8 Connect..." -ForegroundColor Cyan

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install bcrypt "python-jose[cryptography]" python-dateutil --force-reinstall

Write-Host ""
Write-Host "Verificando imports..." -ForegroundColor Cyan
python -c "import bcrypt, jose, dateutil, pandas; print('OK: bcrypt, jose, dateutil, pandas')"

Write-Host ""
Write-Host "Listo. Ejecuta: python run_app.py" -ForegroundColor Green
