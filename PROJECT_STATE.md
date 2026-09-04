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

**TASK-033: Implementación de Walk-Forward Analysis Automatizado - COMPLETADO**
- Módulo creado: `src/backtesting/walk_forward_engine.py`
- Función `run_walk_forward_optimization()`: Sliding window WFA con ventana fija (train_window=200, step=50)
- Función `run_anchored_walk_forward()`: Anchored/Expanding window WFA (initial_train=500, step=50)
- Integración completa: FeaturePipeline → Technical Features → Triple Barrier → RF → OOS predictions
- Validación en datos sintéticos (3000 barras OHLCV):
  - **Sliding WFA**: 53 iteraciones, 2650 predicciones OOS, Accuracy global 45.66%
  - **Anchored WFA**: 47 iteraciones, 2350 predicciones OOS, Accuracy global 47.53%
- Classification report OOS por clase: SL (-1): 51% acc, Time (0): 48% acc, PT (1): 34% acc
- Rolling accuracy tracking (ventana 100) para detectar decay de modelo
- Prepara re-entrenamiento automático mensual/trimestral en producción

**TASK-034: Implementación de Model Registry con DuckDB - COMPLETADO**
- Módulo creado: `src/models/model_registry.py`
- Clase `ModelRegistry` con backend DuckDB (`data/ducklake.db`) + artefactos joblib en `models/registry/`
- Tabla `model_registry` con índices: model_id (PK), symbol, training_date, oos_accuracy, artifact_path
- `register_model()`: Guarda modelo (joblib) + metadata (UUID, símbolo, accuracy, hiperparámetros, métricas)
- `get_best_model(symbol)`: SQL `ORDER BY oos_accuracy DESC LIMIT 1` → carga modelo + metadata
- `get_latest_model(symbol)`: Recupera modelo más reciente por fecha
- `list_models(symbol, limit)`: Lista paginada de modelos
- `delete_model(model_id)`: Elimina registro BD + artefacto disco
- Validación: Modelo RF sintético registrado (Acc=97%), recuperado y verificado (predicciones idénticas)
- Integración lista para: selección automática del mejor modelo por símbolo en producción

**Fase 4: Validación estadística de etiquetas de Triple Barrera implementada (TASK-030).**
**Fase 5: Modelo predictivo Random Forest + Pipeline Real MT5 + Portfolio Loop implementado (TASK-029, TASK-031).**
**Fase 6: Criterio de Kelly activado en Paper Trading (`USE_KELLY_SIZER = True`) (TASK-032).**
**Fase 7: Motor de Walk-Forward Analysis + Model Registry (DuckDB) implementado (TASK-033, TASK-034).**
**Fase 7: Motor de estrés Monte Carlo y cálculo de riesgo de cola (VaR/CVaR) implementado (TASK-035).**
**Fase 8: Dashboard de monitoreo en tiempo real implementado con Streamlit (TASK-036).**
**Fase 9: Orquestador MLOps de re-entrenamiento continuo implementado (TASK-037).**

**Fase 10: Integración de telemetría real, SR dinámico, bandas de Bollinger y VaR proactivo implementada (TASK-038).**
**Fase 11: Inyección de dependencias completada. Sistema ensamblado para producción (TASK-039).**