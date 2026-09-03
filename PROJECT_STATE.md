# Project State
**Fase Actual:** Fase 3: Catálogo de datos de alta rendimiento con DuckLake implementado (TASK-015). Fase 3: Motor de cálculo de riesgo y drawdown implementado (TASK-016). Fase 4: Ingeniería de características y etiquetado Triple Barrera implementado (TASK-017).

**TASK-028: Implementación de Asignación Dinámica de Capital (Kelly Criterion) - COMPLETADO**
- Módulo creado: `position_sizer/position_sizers/kelly_criterion_sizer.py` (raíz del proyecto)
- Clase `KellyCriterionSizer` implementa `IPositionSizer` con Kelly Criterion dinámico + ajuste de volatilidad
- Propiedades `KellySizingProps` con fracción de Kelly configurable (default 25% = Quarter Kelly)
- Límites de riesgo extraídos exclusivamente desde `config.py` (LEARNING_RISK_PCT_MIN=0.25%, LEARNING_RISK_PCT_MAX=2.0%)
- Callback `get_strategy_metrics(symbol, strategy)` añadido a `TradingBrain` para métricas por estrategia
- Configuración en `config.py`: `USE_KELLY_SIZER`, `KELLY_FRACTION`, `KELLY_MIN_WIN_RATE`, `KELLY_MIN_TRADES`, `KELLY_VOLATILITY_LOOKBACK`
- Integración en `trading_app.py`: selector condicional entre `RiskPctPositionSizer` (default) y `KellyCriterionSizer`
- Simulación validada: WR=44.50%, Expectancy=-0.0423 → Kelly=0% → clamped a 0.25% (mínimo)
- Activación: establecer `USE_KELLY_SIZER = True` en config.py o via variable de entorno

**SSOT Files Created (2026-09-03):**
- `DECISION_LOG.md` — Pila tecnológica, parámetros cuantitativos, reglas Train/Test/Validation, versiones, decisiones arquitectónicas
- `docs/TASKS.md` — Registro de tareas completadas, actual (TASK-029), backlog priorizado, reglas SOP
- `TRADING_JOURNAL.md` — Histórico backtesting V5-V14, métricas por activo, Kelly simulation, circuit breaker events, research log

**TASK-029: Train/Test/Validation Split Implementation - COMPLETADO**
- Módulo creado: `src/models/rf_classifier.py`
- Pipeline: StandardScaler + RandomForestClassifier (n_estimators=200, max_depth=8, random_state=42)
- Split cronológico estricto: 70% Train / 15% Test / 15% Validation (sin data leakage)
- Validación: classification_report en Test y Validation sets independientes
- Feature importance: RSI (18%), EMA Ratio (17%), MACD (16%) como top predictores
- Resuelve bloqueador crítico de auditoría 2026-08-17

**TASK-030: Validación Estadística de Etiquetas de Triple Barrera - COMPLETADO**
- Módulo creado: `src/features/validate_labels.py`
- Función `audit_triple_barrier_labels()` aplica etiquetado y audita distribución de clases (-1, 0, 1)
- Detección automática de desbalance crítico: alerta si alguna clase < 10% del total
- Métrica de balance: ratio min/max entre clases
- Simulación validada con 10k precios sintéticos (volatilidad estocástica): SL=29.9%, Time=44.7%, PT=25.5%, ratio=0.57
- Copiado `triple_barrier.py` a `src/features/` para import consistente

**TASK-031: Feature Store y Pipeline Real con Datos MT5 - COMPLETADO**
- Módulo creado: `src/features/feature_pipeline.py`
- Clase `FeaturePipeline` orquesta: MT5/DuckLake → Features técnicos → Triple Barrera → Train/Test/Val
- **PORTFOLIO PIPELINE**: `run_portfolio_pipeline()` procesa bucle sobre `config.DEFAULT_SYMBOLS` (9 símbolos)
- Conecta con `PlatformConnector` para datos reales OHLCV (5000 barras/símbolo, demo Exness)
- 12 features técnicos: returns, volatility, EMAs, RSI, MACD, ATR, Bollinger, Volume, Price position
- Triple Barrera integrado con volatilidad dinámica (pt=1.5, sl=1.0, time=15)
- Split cronológico 70/15/15 sin data leakage
- Random Forest entrenado y evaluado en Test/Val independientes por símbolo
- **Validado en producción**: 9/9 símbolos exitosos, 43,767 muestras totales, modelos guardados en `models/portfolio_<timestamp>/`
- Distribución target típica: SL ~53%, Time ~5%, PT ~42% (clase 0 underrepresented esperada)

**TASK-032: Activación del Criterio de Kelly en Paper Trading - COMPLETADO**
- `config.py`: `USE_KELLY_SIZER = True` (activado)
- Parámetros Kelly: `KELLY_FRACTION=0.25` (Quarter Kelly), `KELLY_MIN_WIN_RATE=0.35`, `KELLY_MIN_TRADES=30`, `KELLY_VOLATILITY_LOOKBACK=20`
- `trading_app.py`: Selector condicional ya implementado — instancia `KellyCriterionSizer` cuando `USE_KELLY_SIZER=True`
- Validación: Kelly calc con WR=55%/R:R=1.5 → 5.43% risk; WR=44.5%/R:R=1.0 → 0% → clamped a 0.25% (MIN)
- Límites hard: `LEARNING_RISK_PCT_MIN=0.25%`, `LEARNING_RISK_PCT_MAX=2.0%` (desde config.py)
- Próximo: Paper trading en demo Exness para validación en vivo de eventos de sizing

**Fase 4: Validación estadística de etiquetas de Triple Barrera implementada (TASK-030).**
**Fase 5: Modelo predictivo Random Forest + Pipeline Real MT5 + Portfolio Loop implementado (TASK-029, TASK-031).**
**Fase 6: Criterio de Kelly activado en Paper Trading (`USE_KELLY_SIZER = True`) (TASK-032).**