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

**Fase 5: Modelo predictivo Random Forest implementado con validación y preprocesamiento (TASK-029).**