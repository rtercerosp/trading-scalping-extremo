# Task Registry - Institutional Algorithmic Trading System

**Versión:** 1.0
**Fecha:** 2026-09-03
**Metodología:** State-Driven Development (GEMINI.md)

---

## Tareas Completadas

| Task ID | Título | Fase | Estado | Commit | Archivos Principales |
|---------|--------|------|--------|--------|---------------------|
| TASK-015 | Catálogo DuckLake High-Performance | 3 | ✅ COMPLETADO | - | `ducklake_catalog.py`, `src/backtest/` |
| TASK-016 | Motor Cálculo Riesgo & Drawdown | 3 | ✅ COMPLETADO | - | `src/risk_manager/drawdown_engine.py` |
| TASK-017 | Feature Engineering + Triple Barrier Labeling | 4 | ✅ COMPLETADO* | - | `src/models/`, `src/backtest/`, `research/` |
| TASK-028 | Kelly Criterion Dynamic Capital Allocation | 4+ | ✅ COMPLETADO | `53a4b9b`, `d5568ce` | `position_sizer/position_sizers/kelly_criterion_sizer.py`, `trading_app.py`, `config.py`, `brain/trading_brain.py` |

> *TASK-017 documentado como completado en PROJECT_STATE.md pero requiere validación de implementación real de Triple Barrier Labeling.

---

## Tarea Actual (En Ejecución)

| Task ID | Título | Fase | Estado | Asignado | Inicio |
|---------|--------|------|--------|----------|--------|
| **TASK-029** | **Train/Test/Validation Split Implementation** | **4/5** | **🔴 BLOQUEADOR CRÍTICO** | - | **PENDIENTE** |

### Descripción TASK-029
Implementar separación formal de datos en conjuntos **Entrenamiento (Train)**, **Prueba (Test)** y **Validación (Validation)** para todos los modelos predictivos ML.

**Criterios de Aceptación:**
- [ ] Split temporal (no aleatorio) para series temporales financieras
- [ ] Mínimo 70% Train / 15% Test / 15% Validation O Walk-Forward expanding window
- [ ] Aplicable a: `ai/backtest_engine.py`, `src/models/`, `src/backtest/vectorbt_engine.py`
- [ ] Documentado en `DECISION_LOG.md` sección 3
- [ ] Tests unitarios que validen no data leakage

**Impacto:** Sin esta tarea, **cualquier modelo ML predictivo está invalidado** (overfitting garantizado). Auditoría 2026-08-17: 🔴 FALLA CRÍTICA.

---

## Backlog Priorizado (Próximas Tareas)

| Task ID | Título | Fase | Prioridad | Dependencias | Estimación |
|---------|--------|------|-----------|--------------|------------|
| TASK-030 | Validar Triple Barrier Labeling (TASK-017 real) | 4 | ALTA | TASK-029 | 2-3 días |
| TASK-031 | Feature Store con DuckLake | 4 | MEDIA | TASK-015, TASK-029 | 3-5 días |
| TASK-032 | Activar Kelly Criterion en Producción | 4 | MEDIA | TASK-029, TASK-028 | 1-2 días |
| TASK-033 | Walk-Forward Analysis Automatizado | 5 | ALTA | TASK-029 | 3-4 días |
| TASK-034 | Model Registry & Versioning (MLflow/DuckDB) | 5 | MEDIA | TASK-029, TASK-031 | 2-3 días |
| TASK-035 | Stress Testing & Monte Carlo Portfolio | 5 | ALTA | TASK-016 | 2-3 días |

---

## Reglas de Gestión de Tareas (SOP - GEMINI.md:18-24)

1. **Una tarea a la vez** - No paralelizar tareas en misma sesión
2. **Sincronización obligatoria** - Leer PROJECT_STATE.md + docs/TASKS.md antes de iniciar
3. **Ejecución modular** - Código en `src/` o `notebooks_colab/`, testeable
4. **Actualización de estado** - Escribir en PROJECT_STATE.md al completar
5. **Cierre de ciclo** - Commit Git con mensaje estándar → **CERRAR CHAT**

### Formato Commit Estándar
```bash
git add <archivos>
git commit -m "TASK-XXX: <Título breve>

- <Cambio 1>
- <Cambio 2>
- Validación: <resultado test/métrica>
"
```

---

## Estado de Archivos SSOT (Single Source of Truth)

| Archivo | Existe | Última Actualización | Notas |
|---------|--------|---------------------|-------|
| `PROJECT_STATE.md` | ✅ | 2026-09-03 | Actualizado TASK-028 |
| `DECISION_LOG.md` | ✅ | 2026-09-03 | **Creado hoy** |
| `docs/TASKS.md` | ✅ | 2026-09-03 | **Creado hoy** |
| `TRADING_JOURNAL.md` | ❌ | - | **PENDIENTE CREAR** |

---

## Notas Operativas

- **Branch actual:** `demo-v13-clean-slate` (2 commits ahead de origin)
- **Versión activa:** `V14_DIVERSIFIED_RISK_MANAGED` (config.STRATEGY_VERSION)
- **Modo investigación:** `RESEARCH_MODE = True` (config.py:15)
- **Kelly Sizer:** Disponible pero **desactivado** (`USE_KELLY_SIZER = False`)
- **Próximo hito:** Completar TASK-029 para desbloquear pipeline ML