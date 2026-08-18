# Informe de Versión V10_ZERO_LOSS_SCALPING
**Fecha:** 2026-08-05  
**Estado:** IMPLEMENTADO Y LISTO PARA VALIDACIÓN  
**Objetivo principal:** Cero pérdidas + trailing agresivo + compounding

---

## Resumen Ejecutivo

Se implementó la versión V10_ZERO_LOSS_SCALPING con foco en eliminar pérdidas mediante break-even automatizado al 50% del TP, reverse protection 30%, gap protection, pre-breakeven limitada al SL inicial, trailing agresivo post-breakeven, compounding bonus de volumen 2x, spread filter dinámico y entrenamiento IA orientado a maximizar ganancias y evitar pérdidas.

### Características principales

- **Break-even 50%**: Cuando la posición alcanza el 50% de la distancia proyectada hacia TP, el SL se mueve automáticamente a precio de entrada + buffer de broker/comisiones.
- **Reverse protection 30%**: Si el precio retrocede un 30% desde el nivel de trigger del break-even, la posición se cierra automáticamente.
- **Gap protection**: Se bloquea el movimiento a break-even si el gap entre velas supera el umbral configurado.
- **Pre-breakeven limitada**: Antes de alcanzar el trigger, el SL no puede mejorar más del 25% respecto al SL inicial.
- **Trailing agresivo**: Después del break-even, el trailing se activa antes y con offset más ajustado.
- **Compounding bonus volumen 2x**: Si el equity supera el mínimo configurado, el volumen de entrada se duplica.
- **Spread filter**: En V10, el spread máximo permitido se multiplica por 1.5x el `trade_stops_level`.
- **Entrenamiento IA**: En V10, el aprendizaje prioriza win rate (60%) sobre profit factor (30%) y volumen de trades (10%), y las salidas por break-even/reverse protection se entrenan como TP hits.

---

## Parámetros V10 en config.py

```python
V10_ZERO_LOSS_ENABLED: bool = True
V10_BREAK_EVEN_TRIGGER_PCT: float = 0.50
V10_BREAK_EVEN_BUFFER_POINTS: int = 2
V10_REVERSE_PROTECTION_PCT: float = 0.30
V10_GAP_PROTECTION_PCT: float = 0.003
V10_PRE_BREAK_EVEN_MAX_SL_IMPROVEMENT_PCT: float = 0.25
V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT: float = 0.003
V10_TRAILING_AGGRESSIVE_OFFSET_PCT: float = 0.0015
V10_COMPOUNDING_VOLUME_MULTIPLIER: float = 2.0
V10_COMPOUNDING_MIN_EQUITY: float = 5000.0
V10_SPREAD_MAX_POINTS_MULTIPLIER: float = 1.5
V10_MIN_BROKER_COVERAGE_POINTS: int = 2
V10_MAX_VOLUME_PER_CANDLE_RATIO: float = 0.05
```

---

## Cambios por archivo

### `config.py`
- `STRATEGY_VERSION = "V10_ZERO_LOSS_SCALPING"`.
- Agregada sección `V10_ZERO_LOSS_*` con todos los parámetros de la nueva versión.
- `EXTREME_SCALPING_PARAMS` y `LEARNING_ASSET_SPECIFIC_PARAMS` mantienen soporte para `XAUUSD`, `EURUSD`, `GBPUSD`, `USDJPY`, `ETHUSD`.

### `order_executor/break_even_manager.py`
- Reescrito para V10 con estados: `breakeven_triggered`, `reverse_protection_triggered`, `breakeven_trigger_price`.
- Break-even se dispara al 50% de la distancia TP desde entrada.
- Reverse protection cierra la posición si el precio retrocede 30% desde el trigger.
- Gap protection revisa gap entre velas antes de permitir break-even.
- Pre-breakeven: SL inicial se almacena y no se permite mejorar más del 25% antes del trigger.
- Trailing agresivo post-breakeven con offset ajustado por `V10_TRAILING_AGGRESSIVE_OFFSET_PCT`.
- Logging detallado de cada evento candidato.

### `order_executor/order_executor.py`
- Agregado spread filter dinámico para V10: rechaza órdenes si `spread > spread_max_points_multiplier * trade_stops_level * point`.

### `signal_generator/signal_generator.py`
- En V10, `quality_threshold = 70.0`.
- `_is_signal_viable` incluye gap protection para V10.
- `_apply_compounding_bonus`: duplica volumen si equity > `V10_COMPOUNDING_MIN_EQUITY`.

### `brain/trading_brain.py`
- Agregado `get_zero_loss_params(symbol)` para exponer parámetros V10 al BreakEvenManager.
- `learn_from_trade`: en V10, las salidas por break-even/reverse protection se entrenan como TP hits; las pérdidas como SL hits.
- `get_strategy_recommendation`: en V10, el scoring de estrategias prioriza win rate (60%) sobre profit factor (30%).

### `trading_app.py`
- Registrada versión `V10_ZERO_LOSS_SCALPING` como activa.
- Reporte de versión guardado con metadata de features V10.

---

## Entrenamiento IA V10

- **Win rate weight**: 60% (antes 40%)
- **Profit factor weight**: 30% (antes 30%)
- **Trades volume weight**: 10% (antes 30%)
- **Break-even / reverse protection** se registra como `tp_hit=True` para incentivar estrategias que cierran con ganancia mínima.
- **Pérdidas** siempre se registran como `sl_hit=True` para penalizar.

---

## Próximos pasos

1. Ejecutar `trading_app.py` en modo prueba (`--test-mode`) para validar break-even, reverse protection y gap protection.
2. Validar en logs que el break-even se active al 50% del TP y que reverse protection cierre al retroceder 30%.
3. Validar que el compounding bonus duplique volumen cuando equity > 5000.
4. Si todo OK, ejecutar en producción con supervisión.
