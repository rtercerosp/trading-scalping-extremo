# Informe de Auditoría y Correcciones - 2026-08-02

## Resumen Ejecutivo

Se realizó una verificación exhaustiva de los hallazgos de auditoría reportados. De 5 hallazgos, 2 resultaron falsos positivos y 3 fueron confirmados y corregidos.

**Fecha**: 2026-08-02  
**Versión Activa**: V7_KNOWLEDGE_PRELOADED  
**Estado**: Corregido

---

## Verificación de Hallazgos

| # | Hallazgo Reportado | Resultado Verificación | Acción |
|---|-------------------|----------------------|--------|
| 1 | Pydantic faltante en `requirements.txt` | **Falso positivo** | Pydantic está presente en línea 4 de `requirements.txt` e instalado (v2.13.4) |
| 2 | Error crítico de pydantic | **Falso positivo** | No existe fallo de pydantic en ejecución |
| 3 | Información sensible en logs | **Confirmado** | Corregido |
| 4 | `strategy_scores.json` con datos viejos | **Confirmado** | Corregido |
| 5 | P&L del backtest defectuoso | **Confirmado** | Corregido |

---

## Correcciones Aplicadas

### 1. Fuga de información sensible en `discover_symbols.py`

**Archivo**: `discover_symbols.py` (líneas 55-60)  
**Problema**: El script imprimía login y server en texto plano por consola.  
**Cambio**: Se enmascararon las credenciales con `********`.

```python
print("ℹ️  INTENTANDO CONECTAR CON LOS SIGUIENTES DATOS:")
print(f"    - Path:   {path_to_use}")
print("    - Login:  ********")
print("    - Server: ********")
```

**Versiones afectadas**: Todas (script raíz compartido).  
**Impacto**: Las credenciales de MT5 ya no se exponen en consola.

---

### 2. Simulación de P&L incorrecta en `ai/backtest_engine.py`

**Archivo**: `ai/backtest_engine.py` (métodos `_simulate_trade` y `_calculate_profit`)  
**Problema**: El simulador retornaba diferencias de precio brutas (`entry_price - exit_price`) sin convertir a ganancia/pérdida monetaria. Esto generaba profits falsos masivos (ej: `-514,166.79` para BTCUSDc con 700 trades).

**Cambios**:
- Se agregó `_calculate_profit(entry_price, exit_price, is_buy, symbol_info)` que convierte diferencia de precio a P&L monetario usando `trade_tick_value`, `trade_tick_size` y volumen.
- Se pasó `symbol_info` desde `connector.symbol_info_cache` a `_simulate_trade`.
- Se agregaron atributos faltantes en `MockInfo` (`trade_tick_size`, `trade_tick_value`, `trade_contract_size`).
- Se corrigió indentación corrupta en el bloque `try/except` del bucle de estrategias.

**Cálculo correcto**:
```python
price_diff = (exit_price - entry_price) if is_buy else (entry_price - exit_price)
return (price_diff / tick_size) * tick_value * volume
```

**Versiones afectadas**: V7_KNOWLEDGE_PRELOADED (usa `run_preload.py` → `BacktestEngine`).  
**Impacto**: Los scores de `strategy_scores.json` ahora reflejan P&L monetario real, no diferencias de precio.

---

### 3. Reseteo de `strategy_scores.json` con datos viejos

**Archivo**: `ai/strategy_scores.json`  
**Problema**: Contenía entradas `UNKNOWN` con datos históricos corruptos (ej: XAUUSDc con 152,470 trades, profit -4.12M). También contenía scores del backtest defectuoso recién ejecutado.

**Cambio**: Se reseteó el archivo a estado limpio con solo las 10 estrategias conocidas por símbolo (BTCUSDc, XAUUSDc, EURUSDc, ETHUSDc), todas con métricas en cero.

**Versiones afectadas**: V7_KNOWLEDGE_PRELOADED, V4_AI_ADAPTIVE.  
**Impacto**: La pre-carga ahora parte de un estado limpio. Los datos viejos no contaminan los scores.

---

## Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `discover_symbols.py` | Enmascarado login/server en logs |
| `ai/backtest_engine.py` | Corregido P&L de backtest + indentación |
| `ai/strategy_scores.json` | Reseteado a estado limpio |

---

## Verificación

- `python -m py_compile backtest_engine.py discover_symbols.py`: ✅ Sin errores
- `strategy_scores.json`: ✅ Limpio, sin entradas UNKNOWN
- `requirements.txt`: ✅ Pydantic presente (línea 4)

---

## Acciones Recomendadas

1. **Ejecutar pre-carga nuevamente**: `python run_preload.py` para generar scores limpios con el P&L corregido.
2. **Verificar en DEMO**: Confirmar que los nuevos scores del backtest son razonables antes de usar en producción.
3. **Rotar credenciales**: Si `discover_symbols.py` se ejecutó en entornos con logs persistidos, rotar credenciales de MT5 por precaución.

---

## Notas

- Los hallazgos 1 y 2 del informe original (pydantic faltante y error crítico) son falsos positivos.
- El problema central del sistema era el simulador de P&L de `backtest_engine.py`, que invalidaba toda la pre-carga de conocimiento de V7.
- La corrección del P&L es un **cambio breaking** para los scores existentes: todos los valores anteriores son inválidos y deben regenerarse.
