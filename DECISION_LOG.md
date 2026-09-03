# Decision Log - Institutional Algorithmic Trading System

**Versión:** 1.0
**Fecha de creación:** 2026-09-03
**Última actualización:** 2026-09-03

---

## 1. Pila Tecnológica (Tech Stack)

### Lenguajes y Runtime
- **Python:** 3.11+
- **Entorno:** Virtualenv (.venv) con dependencias en `requirements.txt`

### Librerías Cuantitativas Core
| Librería | Versión | Propósito |
|----------|---------|-----------|
| `pandas` | 2.x | Manipulación de series temporales, DataFrames OHLCV |
| `numpy` | 2.x | Cálculos numéricos, álgebra lineal, estadísticas |
| `scikit-learn` | 1.5+ | Modelos ML clásicos (LogisticRegression, SVM, Ensemble) |
| `xgboost` | 2.x | Gradient boosting para clasificación/regresión |
| `lightgbm` | 4.x | Gradient boosting optimizado |
| `vectorbt` | 0.28+ | Backtesting vectorizado de estrategias |
| `duckdb` | 1.1+ | Motor analítico OLAP, catálogo DuckLake |
| `MetaTrader5` | 5.x | Conectividad broker, ejecución órdenes, datos mercado |

### Infraestructura y Utilidades
| Librería | Propósito |
|----------|-----------|
| `pydantic` | Validación de configuración y propiedades (BaseModel) |
| `python-dotenv` | Gestión de variables de entorno (.env) |
| `python-telegram-bot` | Notificaciones Telegram |
| `pytest` | Testing unitario e integración |
| `pyyaml` | Configuración YAML si aplica |

### Arquitectura de Software
- **Patrón:** Event-Driven Architecture (cola de eventos `queue.Queue`)
- **Componentes desacoplados:** SignalGenerator, PositionSizer, RiskManager, OrderExecutor, Portfolio, TradingDirector, TradingBrain
- **Interfaces:** Protocolos (`IPositionSizer`, `IRiskManager`, etc.) en `*/interfaces/`
- **Propiedades:** Pydantic models en `*/properties/`
- **Configuración central:** `config.py` (Single Source of Truth para parámetros)

---

## 2. Parámetros Cuantitativos Institucionales

### Gestión de Riesgo (Risk Management)
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `RISK_MAX_LEVERAGE_FACTOR` | 4 | Apalancamiento máximo de cartera |
| `PORTFOLIO_MAX_NOTIONAL_PCT_PER_TRADE` | 0.50 | Máximo 50% equity por trade individual |
| `PORTFOLIO_MAX_TOTAL_POSITIONS` | 12 | Posiciones simultáneas máximas |
| `PORTFOLIO_MAX_POSITIONS_PER_SYMBOL` | 2 | Máximo por símbolo |
| `PORTFOLIO_MAX_POSITIONS_BY_CATEGORY` | crypto:4, gold:3, forex:4, index:4, commodity:2 | Límites por categoría de activo |

### Position Sizing
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `SIZER_DEFAULT_RISK_PCT` | 0.020 | 2% riesgo base por trade |
| `LEARNING_RISK_PCT_MIN` | 0.0025 | 0.25% suelo riesgo adaptativo |
| `LEARNING_RISK_PCT_MAX` | 0.020 | 2.0% techo riesgo adaptativo |

### Kelly Criterion (TASK-028)
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `USE_KELLY_SIZER` | False | Activar Kelly dinámico (default off) |
| `KELLY_FRACTION` | 0.25 | Quarter Kelly (25% Kelly óptimo) |
| `KELLY_MIN_WIN_RATE` | 0.35 | Win rate mínimo para calcular Kelly |
| `KELLY_MIN_TRADES` | 30 | Trades mínimos para validez estadística |
| `KELLY_VOLATILITY_LOOKBACK` | 20 | Períodos para estimación volatilidad |

### Circuit Breaker
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `ASSET_DRAWDOWN_WARNING_PCT` | -0.08 | Advertencia -8% drawdown |
| `ASSET_DRAWDOWN_BREAKER_PCT` | -0.15 | Breaker severo -15% |
| `ASSET_DRAWDOWN_EXCLUDE_PCT` | -0.20 | Exclusión crítica -20% |
| `ASSET_BREAKER_COOLDOWN_SECONDS` | 7200 | Cooldown base 2h |
| `ASSET_MAX_CONSECUTIVE_LOSSES` | 3 | Pérdidas consecutivas máximas |
| `ASSET_MIN_WIN_RATE_GLOBAL` | 0.40 | Win rate global mínimo |

### Consenso y Calidad de Señales (V14)
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `V13_CONSENSUS_THRESHOLD_DEFAULT` | 2 | Mínimo 2 estrategias confirmando |
| `V13_QUALITY_THRESHOLD_DEFAULT` | 70.0 | Score calidad mínimo 70/100 |

### Aprendizaje Adaptativo (LearningEngine)
| Parámetro | Valor |
|-----------|-------|
| `LEARNING_DEFAULT_SL_ATR_MULT` | 0.8 |
| `LEARNING_DEFAULT_TP_ATR_MULT` | 3.5 |
| `LEARNING_DEFAULT_RISK_PCT` | 0.015 |
| `LEARNING_STEP_RISK_INCREASE` | 0.0005 |
| `LEARNING_STEP_RISK_DECREASE` | 0.001 |
| `LEARNING_WIN_RATE_THRESHOLD_FOR_RISK_INCREASE` | 0.60 |

---

## 3. Reglas de Validación (Train/Test/Validation)

### Separación de Datos (CRÍTICO - Auditoría 2026-08-17)
- **Estado actual:** 🔴 **FALLA CRÍTICA** - No hay separación formal Train/Test/Validation
- **Requerido:** Implementar split temporal (ej. 70/15/15 o walk-forward) antes de cualquier modelo ML predictivo
- **Impacto:** Sin esto, imposible validar robustez y evitar overfitting

### Backtesting
- **Motor:** `ai/backtest_engine.py` + `src/backtest/vectorbt_engine.py`
- **Datos:** Históricos MT5 (5min timeframe principal)
- **Métricas:** Profit Factor, Win Rate, Expectancy, Sharpe, Sortino, Calmar, Max Drawdown, Risk of Ruin
- **Validación:** Out-of-sample + Walk-forward analysis (`research/advanced_metrics_engine.py`)

### Modelos ML
- **Objetivo:** Clasificación direccional (Long/Short) + Regresión (SL/TP sizing)
- **Features:** Técnicas (EMA, RSI, ATR, MACD, FVG, Order Blocks) + Macro (DXY, VIX, BTC.D, US10Y)
- **Target:** Triple Barrier Labeling (TASK-017 - documentado como implementado)

---

## 4. Versiones de Estrategia Registradas

| Versión | Estado | Descripción |
|---------|--------|-------------|
| `V5_ASSET_ISOLATED_GUARDED` | Legacy | Aislamiento por activo, gold guard mode |
| `V7_KNOWLEDGE_PRELOADED` | Legacy | Pre-carga backtest + reglas expertas |
| `V9_SCALPING_MAX_QUALITY` | Legacy | Quality scoring, circuit breaker, signal justification |
| `V10_ZERO_LOSS_SCALPING` | Legacy | Break-even 30%, reverse protection, compounding |
| `V11_CRYPTO_VOLATILITY` | Legacy | Parámetros agresivos crypto, SignalCryptoVolatilityBreakout |
| `V12_UNIVERSAL_AGGRESSIVE` | Legacy | Universal aggressive, SignalGoldMomentumReversal |
| `V14_DIVERSIFIED_RISK_MANAGED` | **ACTIVA** | Consenso 2, límites reducidos, circuit breaker endurecido, Kelly ready |

---

## 5. Símbolos Operativos

### Por Categoría
- **Crypto:** BTCUSD, ETHUSD (sufijo broker: `c` → BTCUSDc, ETHUSDc)
- **Gold:** XAUUSD
- **Forex:** EURUSD, USDJPY, GBPUSD
- **Index:** US500, USTEC, US30
- **Commodity:** UKOIL

### Timeframes
- **Entry:** 5min (configurable por activo)
- **Trend:** 15min
- **RSI:** 5min/15min según activo

---

## 6. Decisiones Arquitectónicas Clave

| Decisión | Fecha | Racional |
|----------|-------|----------|
| Event-driven con Queue | Inicio | Desacoplamiento, testabilidad, replay |
| Pydantic para props | 2026-07 | Validación runtime, type hints, serialización |
| Config central en config.py | 2026-07 | SSOT parámetros, auditoría, no hardcode |
| Kelly Criterion opcional | 2026-09-03 (TASK-028) | Reducir exposición en regímenes adversos, activable por config |
| Circuit breaker por activo | 2026-08 (V14) | Protección drawdown granular, cooldown adaptativo |
| Consenso multi-estrategia | 2026-08 (V14) | Filtrar ruido, requerir 2+ estrategias confirmando |

---

## 7. Próximas Decisiones Pendientes

1. **Train/Test/Validation Split** - Implementar separación temporal formal (bloqueador para ML predictivo)
2. **DECISION_LOG.md versioning** - Establecer proceso de actualización controlada
3. **Kelly activation criteria** - Definir umbrales para activar `USE_KELLY_SIZER=True` en producción
4. **Feature store** - Decidir si implementar feature store (DuckLake/Feast) para TASK-017+