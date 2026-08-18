# Informe de Cambios - Sistema de Trading V14

**Fecha:** 2026-08-10
**Versión anterior:** V13_DEMO_CLEAN_SLATE
**Versión nueva:** V14_DIVERSIFIED_RISK_MANAGED
**Motivo:** Mejorar rentabilidad y eficiencia de cartera tras evaluación crítica (Score 17.03/100, WR 42.88%, PF 1.04)

---

## 1. Resumen Ejecutivo

Se realizaron cambios estructurales en gestión de riesgo, consenso de señales, límites de cartera, circuit breaker y ejecución de órdenes. El objetivo es reducir drawdowns, evitar sobreconcentración y elevar la calidad de las entradas sin sacrificar completamente la actividad de trading.

---

## 2. Cambios por Componente

### 2.1 Configuración General (`config.py`)

- **Cambio de versión:** `STRATEGY_VERSION = "V14_DIVERSIFIED_RISK_MANAGED"`
- **Portfolio más concentrado:**
  - `PORTFOLIO_MAX_TOTAL_POSITIONS`: 30 → 12
  - `PORTFOLIO_MAX_POSITIONS_PER_SYMBOL`: 5 → 2
  - `PORTFOLIO_MAX_POSITIONS_BY_CATEGORY`: reducidos a la mitad aprox.
  - **Nuevo parámetro:** `PORTFOLIO_MAX_NOTIONAL_PCT_PER_TRADE = 0.25` (25% del equity por trade)
- **Riesgo base reducido:**
  - `RISK_MAX_LEVERAGE_FACTOR`: 6 → 4
  - `SIZER_DEFAULT_RISK_PCT`: 0.025 → 0.015
- **Consenso y calidad más estrictos en V13/V14:**
  - `V13_QUALITY_THRESHOLD_DEFAULT`: 65 → 70
  - `V13_CONSENSUS_THRESHOLD_DEFAULT`: 1 → 2 (todos los símbolos)
  - Se eliminaron excepciones de consenso=1; ahora todos requieren al menos 2 estrategias coincidiendo
- **Circuit breaker por activo endurecido:**
  - Warning drawdown: -12% → -8%
  - Breaker severo: -25% → -15%
  - Exclusión crítica: -30% → -20%
  - Cooldown base: 1h → 2h
  - Cooldown adaptativo: hasta 8h para drawdown <= -30%
- **Filtros adicionales:**
  - `ASSET_MAX_CONSECUTIVE_LOSSES`: 5 → 3
  - `ASSET_MIN_TRADES_FOR_BREAKER`: 10 → 8
  - `ASSET_MIN_WIN_RATE_GLOBAL`: 0.35 → 0.40
- **Boost más conservador:**
  - Top N: 1 → 2 activos
  - Posiciones multiplicador: 1.5 → 1.2 (#1), 1.1 (#2)
  - Riesgo multiplicador: 1.3 → 1.15 (#1), 1.05 (#2)
  - Cooldown boost: 2min → 3min
  - Profit mínimo para boost: 12 → 15
- **Parámetros ATR/SL/TP reducidos en `EXTREME_SCALPING_PARAMS`** para disminuir pérdida media por trade.

### 2.2 Portfolio (`portfolio/portfolio.py`)

- **Nuevo parámetro en constructor:** `max_notional_pct_per_trade` y `connector` para cálculo de exposición.
- **Nuevos métodos auxiliares:**
  - `_get_position_notional_acc_ccy(position)`: calcula notional en moneda de cuenta con conversión si es necesario.
  - `_get_total_open_notional_acc_ccy()`: suma notional de todas las posiciones abiertas.
- **`can_open_position` ampliado:** ahora recibe `new_position_notional` y valida que la suma de notional abierto + nuevo no supere `equity * PORTFOLIO_MAX_NOTIONAL_PCT_PER_TRADE`.
- **Protección contra errores:** try/except en consultas de conversión de moneda.

### 2.3 Position Sizer (`position_sizer/position_sizers/risk_pct_position_sizer.py`)

- **Límite de notional por trade:** se cambiò `equity * 0.5 / notional_value` por `equity * config.PORTFOLIO_MAX_NOTIONAL_PCT_PER_TRADE / notional_value`.
- **Mensaje actualizado:** ahora indica limitación por "notional por trade" en lugar de "equity".

### 2.4 Trading Director (`trading_director/trading_director.py`)

- **Nuevo método:** `_estimate_signal_notional_acc_ccy(event)` estima el notional de la nueva posición antes de sizing, usando el mismo método de cálculo que el sizer.
- **Integración con Portfolio:** `self.portfolio.can_open_position(...)` ahora recibe `new_position_notional=self._estimate_signal_notional_acc_ccy(event)` para aplicar el límite del 25% del equity.

### 2.5 Trading Brain (`brain/trading_brain.py`)

- **Circuit breaker global endurecido:**
  - `_max_consecutive_losses`: 3 → 2
  - `_daily_loss_pct_limit`: 0.02 → 0.01 (1%)
- **Drawdown por activo con cooldown adaptativo:**
  - Para `current_drawdown <= -0.30`: cooldown 8h
  - Para `current_drawdown <= -0.25`: cooldown 4h
  - Base para `<= -0.20`: 2h
- **Filtro por profit factor:** si `total_trades >= 20` y `profit_factor < 0.80`, se excluye el activo.
- **Boost más moderado:**
  - `boosted_risk` cap reducido de 0.025 a 0.018
  - Boost solo aplica si no hay ya un `risk_override` activo
  - Ranking interno: #1 obtiene multiplicadores completos, #2 obtiene 1.1x posiciones y 1.05x riesgo
- **`get_asset_boost_info` actualizado:** devuelve multiplicadores diferenciados por ranking.

### 2.6 Signal Generator (`signal_generator/signal_generator.py`)

- **Consenso endurecido para V13/V14:** todos los símbolos requieren `consensus_threshold = 2`.
- No se modificó la lógica interna de generación, pero al elevar umbrales de calidad y consenso, se reduce la emisión de señales finales.

### 2.7 Order Executor (`order_executor/order_executor.py`)

- **R/R mínimo ajustado por categoría:**
  - `forex`: 1.5 → 1.2
  - `index`: 1.8 → 1.3
  - `commodity`: 1.8 → 1.4
  - `gold`: 2.0 → 1.5
  - `crypto`: 2.0 → 1.5
- **Corrección de SL > TP:** usa `min_tp_multiplier` dinámico según categoría en lugar de 1.5 fijo.

---

## 3. Archivos Modificados

| Archivo | Líneas afectadas (aprox.) | Tipo de cambio |
|---|---|---|
| `config.py` | 28-212, 46-149, 174-192, 194-214 | Mejora de parámetros |
| `portfolio/portfolio.py` | 1-211 | Nueva lógica de notional |
| `position_sizer/position_sizers/risk_pct_position_sizer.py` | 116-123 | Límite de notional |
| `trading_director/trading_director.py` | 307-338 | Estimación de notional y paso a `can_open_position` |
| `brain/trading_brain.py` | 69-80, 335-439, 497-509 | Circuit breaker, boost, profit factor |
| `signal_generator/signal_generator.py` | 571-575 | Consenso V13/V14 |
| `order_executor/order_executor.py` | 131-155 | R/R mínimo por categoría |
| `trading_app.py` | 104-110 | Paso de `max_notional_pct_per_trade` y `connector` a Portfolio |

---

## 4. Impacto Esperado

- **Menor drawdown:** límites más estrictos de exposición y circuit breaker más sensible deberían reducir el Max Drawdown actual (~172 USD).
- **Mayor calidad de entradas:** consenso de 2 estrategias y umbral 70 deberían aumentar el Win Rate objetivo por encima de 50%.
- **Diversificación:** límites por categoría y notional por trade evitan concentración en pocos activos.
- **Gestión de cartera más eficiente:** top 2 activos con boost moderado en lugar de sobreconcentrar en 1 solo.
- **Profit Factor:** se espera subir de 1.00 a >1.30 con menos trades pero más seleccionados.

---

## 5. Riesgos y Consideraciones

- **Menor cantidad de trades:** al exigir consenso=2, habrá menos señales ejecutadas. Se recomienda monitorear durante 1-2 semanas.
- **Drawdown más agresivo:** exclusiones a -15% y -20% pueden reducir drawdown pero también pueden excluir activos en recuperación temporal.
- **Notional limitado:** en cuentas pequeñas (<500 USD) el límite del 25% puede impedir operar algunos símbolos por volumen mínimo; ajustar si es necesario.
- **Boost moderado:** se redujo para evitar amplificar drawdowns en el activo "ganador". Si el sistema funciona bien, se puede aumentar gradualmente.

---

## 6. Próximos Pasos Recomendados

1. Ejecutar el bot en demo y recolectar métricas durante mínimo 50-100 trades por activo.
2. Revisar el reporte institucional periódico para ver si el Score sube por encima de 50.
3. Ajustar `V13_CONSENSUS_THRESHOLD_DEFAULT` y `V13_QUALITY_THRESHOLD_DEFAULT` según performance real.
4. Evaluar si los cooldowns de circuit breaker son muy cortos o muy largos tras observar recuperaciones reales.
5. Considerar reintroducir excepciones de consenso=1 para categorías con muy pocas estrategias viables (por ejemplo, índices), solo si la calidad lo justifica.

---

*Informe generado automáticamente como parte de la actualización a V14.*
