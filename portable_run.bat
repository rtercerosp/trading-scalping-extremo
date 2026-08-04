@echo off
chcp 65001 >nul
echo ==========================================
echo V4.1.0 Portable - Ejecucion
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: No se encontro el entorno virtual.
    echo Ejecutá portable_install.bat primero.
    pause
    exit /b 1
)

if not exist ".env" (
    echo ERROR: No se encontro el archivo .env
    echo Copia .env.example a .env y completá tus credenciales.
    pause
    exit /b 1
)

.venv\Scripts\python.exe trading_app.py
pause
