# V4.1.0 Portable - Scalping Extremo V4 Portable

Version portable lista para copiar a cualquier equipo Windows.

## Instalacion

1. Copia toda esta carpeta a una ruta corta, por ejemplo:
   - `C:\MT5\`
   - `D:\Trading\`
   - `X:\`

2. Abre una terminal en esa carpeta y ejecuta:

   portable_install.bat

   Eso creara el entorno virtual `.venv` e instalara las dependencias.

## Configuracion

1. Copiá `.env.example` a `.env`.
2. Editá `.env` con tus datos reales:
   - `MT5_PATH`: ruta al `terminal64.exe` de MT5.
   - `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`: credenciales de tu cuenta.
   - `TRADING_SYMBOLS`: lista de activos, por ejemplo `XAUUSD+,NAS100,BTCUSD,EURUSD`.
   - `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` (opcional).

## Ejecucion

Doble clic en:

  portable_run.bat

O desde terminal:

  .venv\Scripts\python.exe trading_app.py

## Caracteristicas de esta version

- NAS100 y XAUUSD+ sin cambios.
- BTCUSD limitado a 0.5 lotes maximo.
- EURUSD protegida solo en ventana real de noticias.
- Rutas relativas: funciona desde cualquier carpeta sin paths largos.
- Sin dependencias externas al proyecto: solo Python y MT5 instalados en el equipo destino.

## Notas

- Si usas MT5 portable, ponele `MT5_PORTABLE=True` en `.env`.
- No compartas el archivo `.env` con terceros.
- Para volver a la version anterior, usá la carpeta `versions\v4.0.0_scalping_agresivo`.
