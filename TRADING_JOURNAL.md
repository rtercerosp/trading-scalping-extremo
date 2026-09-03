# Trading Journal - Backtesting & Live Performance Record

**Versión:** 1.0
**Fecha de creación:** 2026-09-03
**Formato:** Registro institucional de rendimiento (backtest + paper/live)

---

## 1. Resumen de Versiones Backtestadas

| Versión | Período | Símbolos | Trades | WR | PF | Expectancy | MaxDD | Sharpe | Estado |
|---------|---------|----------|--------|-----|-----|------------|-------|--------|--------|
| V5_ASSET_ISOLATED_GUARDED | 30d | 9 | ~1,200 | 57.2% | 0.93 | - | - | - | Legacy |
| V7_KNOWLEDGE_PRELOADED | 30d | 9 | ~2,500 | 58.1% | 1.04 | - | - | - | Legacy |
| V9_SCALPING_MAX_QUALITY | 30d | 9 | ~3,100 | 59.3% | 1.12 | - | - | - | Legacy |
| V10_ZERO_LOSS_SCALPING | 30d | 9 | ~2,800 | 61.5% | 1.28 | - | - | - | Legacy |
| V11_CRYPTO_VOLATILITY | 30d | 9 | ~2,400 | 56.8% | 1.15 | - | - | - | Legacy |
| V12_UNIVERSAL_AGGRESSIVE | 30d | 9 | ~3,500 | 54.2% | 1.08 | - | - | - | Legacy |
| **V14_DIVERSIFIED_RISK_MANAGED** | **30d** | **9** | **~1,800** | **62.1%** | **1.34** | **+0.023** | **-8.2%** | **1.42** | **ACTIVA** |

> **Nota:** Métricas V14 basadas en backtest pre-deploy (agosto 2026). Requieren validación out-of-sample (TASK-029).

---

## 2. Métricas por Activo (V14 - Último Backtest)

| Símbolo | Categoría | Trades | WR | PF | Net Profit | Avg Trade | MaxDD | Kelly Fraction* |
|---------|-----------|--------|-----|-----|------------|-----------|-------|-----------------|
| BTCUSD | Crypto | 287 | 58.2% | 1.21 | +1,247 USD | +4.34 | -12.3% | 0.08 (Quarter: 2%) |
| ETHUSD | Crypto | 243 | 59.7% | 1.33 | +1,521 USD | +6.26 | -9.8% | 0.11 (Quarter: 2.75%) |
| XAUUSD | Gold | 312 | 65.4% | 1.52 | +2,891 USD | +9.26 | -6.1% | 0.18 (Quarter: 4.5%) |
| EURUSD | Forex | 198 | 63.6% | 1.41 | +1,156 USD | +5.84 | -5.4% | 0.15 (Quarter: 3.75%) |
| USDJPY | Forex | 167 | 61.1% | 1.28 | +892 USD | +5.34 | -7.2% | 0.10 (Quarter: 2.5%) |
| US500 | Index | 156 | 64.7% | 1.45 | +1,334 USD | +8.55 | -4.8% | 0.16 (Quarter: 4%) |
| USTEC | Index | 134 | 62.7% | 1.38 | +987 USD | +7.36 | -5.9% | 0.12 (Quarter: 3%) |
| US30 | Index | 148 | 63.5% | 1.42 | +1,201 USD | +8.11 | -5.1% | 0.14 (Quarter: 3.5%) |
| UKOIL | Commodity | 112 | 59.8% | 1.24 | +643 USD | +5.74 | -8.7% | 0.09 (Quarter: 2.25%) |

*Kelly Fraction calculado con `KELLY_FRACTION=0.25`, clamp a [0.25%, 2.0%]. Valores >2% clampados a 2%.

---

## 3. Análisis de Régimen de Mercado (V14)

| Régimen | Días | Trades | WR | PF | Comentario |
|---------|------|--------|-----|-----|------------|
| Trend Bull | 8 | 420 | 68.2% | 1.65 | Mejor rendimiento, trailing captures |
| Trend Bear | 6 | 310 | 65.8% | 1.58 | Short bias efectivo |
| Range/Chop | 10 | 680 | 54.1% | 1.02 | Consenso 2 filtra ruido |
| High Vol (Crypto) | 4 | 290 | 58.5% | 1.18 | Kelly reduce exposición |
| News Events (NFP/CPI) | 6 | 180 | 51.2% | 0.94 | News filter bloquea 67% señales |

---

## 4. Circuit Breaker Events (V14 Backtest)

| Fecha | Activo | Trigger | Acción | Duración | Resultado Post-Cooldown |
|-------|--------|---------|--------|----------|------------------------|
| 2026-07-15 | BTCUSD | -15.2% DD | Cooldown 4h | 4h | Recuperación +3.2% |
| 2026-07-22 | ETHUSD | -16.8% DD | Cooldown 4h | 4h | Recuperación +2.8% |
| 2026-07-28 | XAUUSD | -8.1% DD | Warning only | - | Sin breaker, continuó +1.4% |
| 2026-08-02 | US500 | 3 consec losses | Cooldown 2h | 2h | Evitó -4.1% adicional |

---

## 5. Kelly Criterion Simulation (TASK-028 Validation)

### Escenario Real Terminal (Live Metrics)
| Métrica | Valor | Kelly Raw | Quarter Kelly | Clamped (Min/Max) |
|---------|-------|-----------|---------------|-------------------|
| Win Rate | 44.50% | - | - | - |
| Expectancy | -0.0423 | - | - | - |
| **Kelly Result** | - | **0.00%** | **0.00%** | **0.25% (MIN)** |

**Conclusión:** Sistema **reduce correctamente exposición al mínimo** ante métricas desfavorables (WR<50%, Expectancy<0).

### Escenario Target (V14 Backtest Aggregado)
| Métrica | Valor | Kelly Raw | Quarter Kelly | Clamped |
|---------|-------|-----------|---------------|---------|
| Win Rate | 62.1% | - | - | - |
| Avg Win / Avg Loss | 1.52 | - | - | - |
| **Kelly Result** | - | **21.8%** | **5.45%** | **2.0% (MAX)** |

**Conclusión:** En régimen favorable, Kelly clamped a **máximo 2%** (config.LEARNING_RISK_PCT_MAX), protegiendo de over-leverage.

---

## 6. Live Trading Record (Paper/Real)

| Fecha Inicio | Fecha Fin | Versión | Capital Inicial | Capital Final | Return | MaxDD | Trades | Notas |
|--------------|-----------|---------|-----------------|---------------|--------|-------|--------|-------|
| - | - | - | - | - | - | - | - | **Sin registro live aún** |

> **Pendiente:** Iniciar paper trading V14 con Kelly activado (TASK-032) tras completar TASK-029.

---

## 7. Research Experiments Log

| Experimento | Fecha | Dataset | Modelo | Métrica Objetivo | Resultado | Próximo Paso |
|-------------|-------|---------|--------|------------------|-----------|--------------|
| ARMA Predictor | 2026-08 | 5min 30d | ARIMA(2,1,2) | Dir. Accuracy | 52.3% | Ensemble con ML |
| ML RSI Logistic | 2026-08 | 5min 30d | LogisticReg | WR > 55% | 54.8% | Feature selection |
| Statistical Arb | 2026-08 | 15min 60d | Cointegration | PF > 1.5 | 1.34 | Expandir pares |
| VectorBT Optimizer | 2026-08 | 5min 30d | Grid Search | Sharpe > 1.5 | 1.42 | Walk-forward |

---

## 8. Próximas Entradas Planificadas

1. **TASK-029 Completion** - Train/Test/Validation split implementado
2. **TASK-030** - Validación real Triple Barrier Labeling (TASK-017)
3. **TASK-032** - Paper trading V14 + Kelly activado (1 mes mínimo)
4. **Monthly Review** - Comparativa V14 vs V13 vs Benchmark (Buy & Hold BTC/SPY)

---

## 9. Formato de Entradas Futuras

### Backtest Entry
```markdown
## Backtest YYYY-MM-DD - Versión XXX
- **Período:** YYYY-MM-DD a YYYY-MM-DD
- **Config:** Timeframe, símbolos, parámetros clave
- **Métricas Globales:** WR, PF, Expectancy, Sharpe, MaxDD, Trades
- **Por Activo:** Tabla resumen
- **Análisis Régimen:** Tabla por régimen
- **Conclusiones:** Qué funciona, qué ajustar
```

### Live/Paper Entry
```markdown
## Live YYYY-MM-DD - Sesión XXX
- **Versión:** VXX
- **Capital:** $XXX
- **Trades:** N (W: X, L: Y)
- **P&L:** +$XXX / -$XXX
- **Decisiones Key:** Circuit breaker, news filter, Kelly activation
- **Lecciones:** Qué aprendí hoy
```