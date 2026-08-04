@echo off
chcp 65001 >nul
echo ==========================================
echo V4.1.0 Portable - Instalacion
echo ==========================================
echo.

if not exist ".venv" (
    echo [1/2] Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: No se pudo crear el entorno virtual. Verificá que Python este instalado y en el PATH.
        pause
        exit /b 1
    )
) else (
    echo [1/2] Entorno virtual existente detectado.
)

echo.
echo [2/2] Instalando dependencias...
.venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo Instalacion finalizada.
echo ==========================================
echo.
echo Proximo paso:
echo   1. Copia .env.example a .env
echo   2. Completa tus credenciales en .env
echo   3. Ejecuta portable_run.bat
echo.
pause
