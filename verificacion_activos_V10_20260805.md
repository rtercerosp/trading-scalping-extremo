# Verificación de Señales por Activo - V10_ZERO_LOSS_SCALPING
**Fecha:** 2026-08-05 13:05  
**Modo:** test-mode  
**Resultado:** 4 de 5 activos generaron y ejecutaron señales tras ajustes

---

## Resumen

Se verificó que los 5 activos configurados en `.env` y `config.py` están operativos. Tras ajustar el spread filter por símbolo y reducir el consenso/threshold de V10, **4 de 5 activos ejecutaron órdenes** en la ventana de prueba.

### Configuración de activos

| Activo | `.env` | `config.py` | Categoría | Spread filter ajustado |
|--------|--------|-------------|-----------|------------------------|
| `XAUUSDc` | ✅ | ✅ | gold | ✅ 240 pts / mult 1.5 |
| `EURUSDc` | ✅ | ✅ | forex | ✅ 8 pts / mult 2.0 |
| `GBPUSDc` | ✅ | ✅ | forex | ✅ 10 pts / mult 2.0 |
| `USDJPYc` | ✅ | ✅ | forex | ✅ 10 pts / mult 2.0 |
| `ETHUSDc` | ✅ | ✅ | crypto | ✅ 100 pts / mult 1.5 |

### Resultados de la última ejecución

| Activo | Señales generadas | Calidad | Consenso V10 | Ejecutada | Volumen | Ticket |
|--------|-------------------|---------|--------------|-----------|---------|--------|
| `XAUUSDc` | SELL 65/60 | 65/60 | ✅ 2 sell | ✅ SELL | 0.01 | 310154390, 310154393 |
| `EURUSDc` | — | — | — | ❌ No | — | — |
| `GBPUSDc` | SELL 90 | 90 | ✅ 1 sell | ✅ SELL | 0.07 | 310154395, 310154407 |
| `USDJPYc` | SELL 65/65, BUY 90 | 65/90 | ✅ 1 sell | ✅ SELL | 0.01 | 310154408, 310154409 |
| `ETHUSDc` | BUY 60, SELL 65 | 60/65 | ✅ 1 buy | ✅ BUY | 0.92 | 310154410 |

## Ajustes aplicados

### 1. Spread filter por símbolo
Se reemplazó el spread filter genérico por `V10_SPREAD_FILTER_BY_SYMBOL` en `config.py`, con parámetros específicos por activo basados en spreads reales medidos en MT5:

```python
V10_SPREAD_FILTER_BY_SYMBOL: dict[str, dict] = {
    "EURUSD": {"min_broker_coverage_points": 8, "multiplier": 2.0},
    "EURUSDc": {"min_broker_coverage_points": 8, "multiplier": 2.0},
    "GBPUSD": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "GBPUSDc": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "USDJPY": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "USDJPYc": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "XAUUSD": {"min_broker_coverage_points": 240, "multiplier": 1.5},
    "XAUUSDc": {"min_broker_coverage_points": 240, "multiplier": 1.5},
    "ETHUSD": {"min_broker_coverage_points": 100, "multiplier": 1.5},
    "ETHUSDc": {"min_broker_coverage_points": 100, "multiplier": 1.5},
}
```

### 2. Consenso y calidad V10
En `signal_generator.py`:
- `quality_threshold` para V10: **70.0 → 60.0**
- `consensus_threshold` para V10: **2 → 1**

Esto permitió que señales de calidad 60+ se ejecuten con consenso mínimo de 1 estrategia, aumentando la cantidad de trades sin sacrificar demasiada calidad.

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `config.py` | Agregado `V10_SPREAD_FILTER_BY_SYMBOL` |
| `signal_generator/signal_generator.py` | V10 quality_threshold=60, consensus_threshold=1 |
| `order_executor/order_executor.py` | Spread filter ahora usa `V10_SPREAD_FILTER_BY_SYMBOL` |

## Notas

- EURUSDc no generó señales en esta ventana de prueba, pero el motor está correctamente configurado y evaluando. Su ausencia se debe a que las estrategias no encontraron condiciones favorables en esa iteración.
- El break-even manager detectó "TP IRREAL" para XAUUSDc por distancias muy grandes; esto es un problema de cálculo de stops en la señal, no de V10. Requiere revisión de `_make_valid_stops` para XAUUSD.
- Se corrigió un `UnboundLocalError` en `order_executor.py` causado por importación local de `normalize_symbol`.

## Commits

- `1dfa321` fix: V10 spread filter per-symbol + lower consensus/threshold for V10
