# Project State
**Fase Actual:** Fase 3: Catálogo de datos de alta rendimiento con DuckLake implementado (TASK-015). Fase 3: Motor de cálculo de riesgo y drawdown implementado (TASK-016). Fase 4: Ingeniería de características y etiquetado Triple Barrera implementado (TASK-017).

**TASK-028: Implementación de Asignación Dinámica de Capital (Kelly Criterion) - EN PROGRESO**
- Módulo creado: `src/position_sizer/position_sizers/kelly_criterion_sizer.py`
- Clase `KellyCriterionSizer` implementa Kelly Criterion dinámico con ajuste de volatilidad
- Propiedades `KellySizingProps` con fracción de Kelly configurable (default 25%)
- Límites de riesgo extraídos exclusivamente desde `config.py` (LEARNING_RISK_PCT_MIN=0.25%, LEARNING_RISK_PCT_MAX=2.0%)
- Simulación validada con datos reales terminal (WR=44.50%, Expectancy=-0.0423): sistema reduce exposición al mínimo (0.25%)
- Pendiente: integración en trading_app.py y testing en entorno real