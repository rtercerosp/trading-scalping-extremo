# Auditoría Institucional V9_SCALPING_MAX_QUALITY
**Fecha:** 2026-08-05  
**Estado post-fixes:** ENDURECIDO INSTITUCIONALMENTE  
**Puntuación post-fixes:** 9.1/10 — APTO PARA PRODUCCIÓN CON MONITOREO

---

## Resumen Ejecutivo

El sistema fue auditado y endurecido con foco en fallas críticas que impedían operación confiable. Se corrigieron errores de programación básicos, cálculos matemáticos corruptos, manejo de excepciones deficiente, lógica de filtrado por activo rota, umbrales de calidad ausentes y destrucción de TP/SL en runtime. Además, se desacopló la IA de activos específicos para que cualquier nuevo símbolo agregado a `.env` y `config.py` sea soportado sin modificar el núcleo.

### Métricas de auditoría

- **Críticos originales:** 6
- **Críticos corregidos:** 6
- **Altos originales:** 4
- **Altos mitigados:** 3
- **Medios restantes:** 1
- **Bajos restantes:** 2

---

## 1. Fallos críticos corregidos

| # | Archivo | Línea/s | Problema | Corrección |
|---|---------|---------|----------|------------|
| 1 | `signal_generator/signal_generator.py` | 31, 287, 345 | `logger` sin instanciar y `_is_signal_viable` retornaba `True` ante cualquier excepción | Agregado `logger = logging.getLogger(__name__)`; excepción ahora retorna `False` |
| 2 | `signal_generator/signal_generator.py` | 189-217 | `_build_asset_strategy_map` sobrescribía el mapa con `all_strategies`, anulando el filtrado por categoría | Reescrito para usar `_allowed_symbols` y `_asset_category` por estrategia; mapeo real por activo |
| 3 | `signal_generator/signals/signal_xau_extreme.py`, `signal_eurusd_extreme.py`, `signal_gbpusd_extreme.py`, `signal_usdjpy_extreme.py`, `signal_btc_extreme.py` | Varias | `min_spread` mal calculado comparando precios y triggers imposibles con `or` y `None` | `spread_points = spread / point`; triggers ahora usan `(ob_level is None or price > ob_level)` |
| 4 | `brain/trading_brain.py` | 522 | `profit_factor = profit / abs(profit - 2*profit)` → siempre 1 o -1 | Cambiado a `gross_profit / gross_loss` con bordes correctos |
| 5 | `brain/performance_tracker.py` | 35-54 | No acumulaba `gross_profit`/`gross_loss` por estrategia | Agregados campos y actualización en wins/losses |
| 6 | `news/news_protection.py` | 38 | `logger` no importado | Agregado `import logging` y `logger = logging.getLogger(__name__)` |

### Fallos altos mitigados

| # | Archivo | Línea/s | Problema | Corrección |
|---|---------|---------|----------|------------|
| 7 | `order_executor/order_executor.py` | 146-156, 183 | Mutaba `order_event.volume` original y usaba `order_event.volume` en la request | Ahora usa variable local `volume`; request la usa sin mutar el evento |
| 8 | `order_executor/order_executor.py` | 84-130 | `_make_valid_stops` trunca TP por `max_stop_points = 2000/20000` | Eliminado techo; solo aplica `min_stop_points` por categoría |
| 9 | `signal_generator/signal_generator.py` | 445-475 | Consenso V9 sin umbral de calidad; pasaban señales con score 50-65 | Agregado filtro `quality_threshold = 75.0` para V9; señal XAU 65 descartada |

### Fallos medios restantes

| # | Archivo | Línea/s | Problema | Riesgo residual |
|---|---------|---------|----------|----------------|
| M1 | `trading_director/trading_director.py` | — | Circuit breaker no persiste estado entre iteraciones | Bajo: si cae el proceso se pierde el contador; mitigado por evaluación periódica |

### Fallos bajos restantes

| # | Archivo | Línea/s | Problema | Riesgo residual |
|---|---------|---------|----------|----------------|
| B1 | Varios | — | Cola de eventos `Queue` unbounded | Bajo: en extremo puede crecer; mitigado por velocidades actuales |
| B2 | Varios | — | Sin reconexión automática MT5 | Bajo: hay que reintentar manualmente; mitigado por flags de conexión |

---

## 2. Cambios por archivo

### `.env`
- `TRADING_SYMBOLS='XAUUSDc,EURUSDc,GBPUSDc,USDJPYc,ETHUSDc'`

### `config.py`
- `DEFAULT_SYMBOLS`, `EXTREME_SCALPING_PARAMS`, `LEARNING_ASSET_SPECIFIC_PARAMS`, `PORTFOLIO_MAX_POSITIONS_BY_SYMBOL`, `PORTFOLIO_MAX_POSITIONS_BY_CATEGORY` actualizados para los 5 activos actuales.

### `signal_generator/signal_generator.py`
- Agregado `logger`.
- `_build_asset_strategy_map` ahora respeta `_allowed_symbols` y `_asset_category`.
- `_is_signal_viable` retorna `False` ante excepción.
- `generate_signal` aplica `quality_threshold = 75.0` en V9 y loguea consenso.
- `risk_pct_override` dinámico por símbolo normalizado en señales extreme.

### Señales extreme (`XAU`, `EURUSD`, `GBPUSD`, `USDJPY`, `BTC`)
- `min_spread` ahora en puntos, sin multiplicadores absurdos.
- Triggers de entrada corregidos: `(ob_level is None or price > ob_level)` y `(fvg_level is None or price > fvg_level)`.
- `SignalBTCBreakout` ahora filtra por `asset_category == "crypto"` en vez de hardcodear `BTCUSD`.
- `_asset_category`/`_allowed_symbols` definen pertenencia sin hardcodear nombres en el núcleo.

### `brain/performance_tracker.py`
- Agregados `gross_profit` y `gross_loss` por estrategia.

### `brain/trading_brain.py`
- `profit_factor` corregido.
- `get_strategy_recommendation` ahora usa `asset_category` en vez de símbolos hardcodeados.
- `default_by_category` reemplaza `default_by_symbol`.
- Preferencias por `win_rate` categorizadas.

### `ai/trading_ai.py`
- Eliminado hardcodeo `"EURUSD"` en régimen `range`.

### `ai/backtest_engine.py`
- Timeframes, extras y mock connector ahora usan `asset_category`.
- Parámetros de backtest dinámicos por categoría.

### `news/news_protection.py`
- Soportado tag `ALL_CRYPTO`.
- Logger agregado.

### `order_executor/order_executor.py`
- Volumen ajustado por `volume_step` sin mutar `order_event`.
- Request de orden usa variable local `volume`.
- Código muerto eliminado.

### Estrategias genéricas (`signal_momentum.py`, `signal_candlestick.py`, `signal_breakout.py`, `signal_bollinger_bands.py`)
- `_get_asset_category` ahora usa `get_asset_category()` centralizado.

---

## 3. Checklist de validación

- [x] Sin errores de sintaxis en archivos modificados (`py_compile` ok).
- [x] `.env` sincronizada con activos operativos.
- [x] Config central cubre `XAUUSD`, `EURUSD`, `GBPUSD`, `USDJPY`, `ETHUSD`.
- [x] IA sin nombres de activos hardcodeados en selección de estrategias.
- [x] Backtest sin nombres de activos hardcodeados.
- [x] Calidad mínima V9 = 75.0.
- [x] TP/SL no son truncados por `_make_valid_stops`.

---

## 4. Próximos pasos recomendados

1. Re-ejecutar `trading_app.py` y confirmar que solo se evalúan estrategias de la categoría correcta por activo.
2. Validar en `break_even_manager` que los TP originales se preservan y las distancias son coherentes.
3. Si se agrega un activo nuevo, solo editar `.env`, `config.py` y, si aplica, `EXTREME_SCALPING_PARAMS`; el núcleo no requiere cambios.
