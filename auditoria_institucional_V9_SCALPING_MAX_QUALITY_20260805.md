# Auditoría Institucional Completa - V9_SCALPING_MAX_QUALITY
**Fecha:** 2026-08-05
**Auditor:** Kilo (Sistema de Auditoría Institucional)
**Versión Analizada:** V9_SCALPING_MAX_QUALITY
**Alcance:** Auditoría completa de código, arquitectura, seguridad, estabilidad y riesgos del proyecto de trading algorítmico.

---

## Resumen Ejecutivo

Se realizó una auditoría exhaustiva de 20 módulos principales del framework de trading. El sistema presenta una arquitectura basada en eventos con separación de responsabilidades, pero contiene **varios errores críticos de programación** que impiden su funcionamiento correcto en producción, además de inconsistencias entre la configuración y la ejecución, manejo de excepciones insuficiente y riesgos de estabilidad.

**Puntuación General: 4.2 / 10**

El sistema no está listo para operar en producción sin correcciones previas.

---

## Hallazgos por Severidad

### CRÍTICO

#### 1. `signal_generator/signal_generator.py:287` — Variable `logger` no definida
**Archivo:** `signal_generator/signal_generator.py`
**Línea:** 287
**Descripción:** Se usa `logger.debug()` en el bloque `except` de `_evaluate_signal_quality`, pero el archivo solo importa `logging` como módulo; no crea ninguna instancia de logger con `logging.getLogger(__name__)`.
**Impacto:** `NameError` en tiempo de ejecución cuando una señal es evaluada y ocurre cualquier excepción en ese bloque. El generador de señales falla de forma silenciosa o visible, interrumpiendo el flujo de trading.
**Recomendación:** Agregar al inicio del archivo:
```python
logger = logging.getLogger(__name__)
```

---

#### 2. `signal_generator/signal_generator.py:204-209` — Código muerto en `_build_asset_strategy_map`
**Archivo:** `signal_generator/signal_generator.py`
**Líneas:** 204-209
**Descripción:** Después de un bucle que asigna estrategias por categoría de activo, el método sobrescribe todas las asignaciones con `self.asset_strategies[symbol] = all_strategies` para crypto, oro y forex. Esto elimina cualquier filtrado previo por categoría.
**Impacto:** Todas las estrategias se asignan a todos los símbolos, independientemente de la categoría. La arquitectura de categorías de activos queda inutilizada.
**Recomendación:** Eliminar las líneas 204-209 o refactorizar el método para mantener el filtrado por categoría si es necesario.

---

#### 3. `signal_generator/signals/signal_xau_extreme.py:176` — Cálculo erróneo de `min_spread`
**Archivo:** `signal_generator/signals/signal_xau_extreme.py`
**Línea:** 176
**Descripción:** `min_spread = max(getattr(symbol_info, 'trade_stops_level', 0), 10) * symbol_info.point`. En MT5, `trade_stops_level` ya está en puntos. Multiplicar por `point` (ej. 0.01 para XAUUSD) reduce el umbral a 0.1, haciendo que casi cualquier spread sea considerado excesivo.
**Impacto:** Las señales de XAUUSD son descartadas sistemáticamente por spread falso.
**Recomendación:** Corregir a `min_spread = max(getattr(symbol_info, 'trade_stops_level', 0), 10) * symbol_info.point` solo si se confirma que `trade_stops_level` está en unidades de precio. Si ya está en puntos, usar `min_spread_points = max(...)` y comparar en puntos.

---

#### 4. `signal_generator/signals/signal_gbpusd_extreme.py:171` — Cálculo erróneo de `min_spread`
**Archivo:** `signal_generator/signals/signal_gbpusd_extreme.py`
**Línea:** 171
**Descripción:** Idéntico al hallazgo 3 para GBPUSD.
**Impacto:** Filtrado excesivo de señales por spread.
**Recomendación:** Misma corrección que el hallazgo 3.

---

#### 5. `signal_generator/signals/signal_usdjpy_extreme.py:173` — Cálculo erróneo de `min_spread`
**Archivo:** `signal_generator/signals/signal_usdjpy_extreme.py`
**Línea:** 173
**Descripción:** Idéntico al hallazgo 3 para USDJPY.
**Impacto:** Filtrado excesivo de señales por spread.
**Recomendación:** Misma corrección que el hallazgo 3.

---

#### 6. `signal_generator/signals/signal_eurusd_extreme.py:170` — Cálculo erróneo de `min_spread`
**Archivo:** `signal_generator/signals/signal_eurusd_extreme.py`
**Línea:** 170
**Descripción:** Idéntico al hallazgo 3 para EURUSD.
**Impacto:** Filtrado excesivo de señales por spread.
**Recomendación:** Misma corrección que el hallazgo 3.

---

#### 7. `signal_generator/signals/signal_xau_extreme.py:231,242` — Condición de trigger imposible
**Archivo:** `signal_generator/signals/signal_xau_extreme.py`
**Líneas:** 231, 242
**Descripción:** `ask_price > (ob_level or fvg_level or ask_price)`. Si `ob_level` y `fvg_level` son `None`, la expresión se evalúa como `ask_price > ask_price` → `False`.
**Impacto:** Cuando no hay Order Block ni FVG, incluso con `liquidity_sweep=True`, la señal nunca se dispara.
**Recomendación:** Corregir a `ask_price > (ob_level if ob_level is not None else (fvg_level if fvg_level is not None else 0))` o similar.

---

#### 8. `signal_generator/signals/signal_gbpusd_extreme.py:224,235` — Condición de trigger imposible
**Archivo:** `signal_generator/signals/signal_gbpusd_extreme.py`
**Líneas:** 224, 235
**Descripción:** Idéntico al hallazgo 7 para GBPUSD.
**Impacto:** Señales bloqueadas incorrectamente.
**Recomendación:** Misma corrección que el hallazgo 7.

---

#### 9. `signal_generator/signals/signal_usdjpy_extreme.py:228,239` — Condición de trigger imposible
**Archivo:** `signal_generator/signals/signal_usdjpy_extreme.py`
**Líneas:** 228, 239
**Descripción:** Idéntico al hallazgo 7 para USDJPY.
**Impacto:** Señales bloqueadas incorrectamente.
**Recomendación:** Misma corrección que el hallazgo 7.

---

#### 10. `signal_generator/signals/signal_eurusd_extreme.py:224,235` — Condición de trigger imposible
**Archivo:** `signal_generator/signals/signal_eurusd_extreme.py`
**Líneas:** 224, 235
**Descripción:** Idéntico al hallazgo 7 para EURUSD.
**Impacto:** Señales bloqueadas incorrectamente.
**Recomendación:** Misma corrección que el hallazgo 7.

---

#### 11. `brain/trading_brain.py:522` — Cálculo erróneo de `profit_factor`
**Archivo:** `brain/trading_brain.py`
**Línea:** 522
**Descripción:** `profit_factor = stats.get("profit", 0.0) / abs(stats.get("profit", 0.0) - 2 * stats.get("profit", 0.0))`. Esto se simplifica a `profit / abs(-profit)` que es 1 o -1, no el profit factor real.
**Impacto:** El ranking de estrategias y la evaluación institucional usan un profit factor incorrecto, tomando decisiones erróneas sobre qué estrategias priorizar.
**Recomendación:** Cambiar a `gross_profit / gross_loss` usando las métricas ya calculadas en `strategy_performance`. Ejemplo: `gross_profit = stats.get("gross_profit", 0.0); gross_loss = stats.get("gross_loss", 0.0); profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')`.

---

#### 12. `signal_generator/signal_generator.py:340` — `_is_signal_viable` acepta señales inválidas por defecto
**Archivo:** `signal_generator/signal_generator.py`
**Línea:** 340
**Descripción:** El bloque `except Exception` final retorna `True`, aceptando señales potencialmente peligrosas cuando hay cualquier error evaluando viabilidad.
**Impacto:** Señales con spread excesivo, ATR inválido o datos corruptos pasan el filtro y se ejecutan.
**Recomendación:** Retornar `False` en caso de excepción, o al menos loguear y decidir según el tipo de error.

---

#### 13. `order_executor/order_executor.py:148` — Modificación del evento original
**Archivo:** `order_executor/order_executor.py`
**Línea:** 148
**Descripción:** `order_event.volume = round(order_event.volume / symbol_info.volume_step) * symbol_info.volume_step` modifica el `OrderEvent` original.
**Impacto:** Efectos secundarios inesperados si el evento se reutiliza o se inspecciona después.
**Recomendación:** Trabajar sobre una copia del evento o calcular el volumen redondeado en una variable local sin modificar el evento original.

---

#### 14. `order_executor/order_executor.py:154-156` — Código muerto
**Archivo:** `order_executor/order_executor.py`
**Líneas:** 154-156
**Descripción:** `if sl <= 0.0 or tp <= 0.0: sl = order_event.sl; tp = order_event.tp` no modifica nada.
**Impacto:** Código confuso que puede ocultar errores de lógica.
**Recomendación:** Eliminar o reemplazar por validación real.

---

### ALTO

#### 15. `signal_generator/signal_generator.py:218-295` — Hardcode de versiones V8/V9 desincronizado
**Archivo:** `signal_generator/signal_generator.py`
**Líneas:** 318-330
**Descripción:** Se compara `config.STRATEGY_VERSION` con `"V8_EXTREME_SCALPING"`. Si cambia la versión en config pero no aquí, la lógica se ejecuta por la rama `else` con valores hardcodeados.
**Impacto:** Parámetros de filtrado inconsistentes entre versiones.
**Recomendación:** Mover los thresholds a `config.py` o usar un diccionario mapeado por versión.

---

#### 16. Inconsistencia en `_near_psychological_level` entre activos
**Archivos:** 
- `signal_generator/signals/signal_xau_extreme.py`
- `signal_generator/signals/signal_usdjpy_extreme.py`
- `signal_generator/signals/signal_gbpusd_extreme.py`
- `signal_generator/signals/signal_eurusd_extreme.py`
**Descripción:** XAUUSD usa `round(price / (100 * point)) * 100 * point` con tolerancia `50 * point`. USDJPY usa `round(price / (10 * point)) * 10 * point` con tolerancia `5 * point`. GBPUSD y EURUSD no tienen este filtro.
**Impacto:** Comportamiento de trading inconsistentemente sensible a niveles psicológicos según el activo.
**Recomendación:** Unificar la lógica o hacerla configurable por activo en `config.py`.

---

#### 17. `brain/trading_brain.py:282-283` — `_daily_start_balance` puede quedar en 0
**Archivo:** `brain/trading_brain.py`
**Líneas:** 282-283
**Descripción:** Solo se actualiza si `current_balance > 0`. Si la cuenta tiene problemas al iniciar, nunca se activa el circuit breaker por drawdown.
**Impacto:** Protección de cuenta inerte.
**Recomendación:** Inicializar con el balance actual en `__init__` o en `reset_daily_circuit_breaker` incluso si es 0, pero loguear advertencia.

---

#### 18. `brain/trading_brain.py:305-310` — `reset_daily_circuit_breaker` usa balance actual
**Archivo:** `brain/trading_brain.py`
**Líneas:** 305-310
**Descripción:** Si el balance bajó durante el día, al resetear se toma el balance menor como `_daily_start_balance`.
**Impacto:** El límite de drawdown se calcula sobre una base más baja, haciendo que el circuit breaker se active más tarde de lo esperado.
**Recomendación:** Guardar el balance al inicio del día (medianoche) en lugar del balance al momento del reset.

---

#### 19. `order_executor/order_executor.py:27-31` — Blacklist usa símbolo no normalizado
**Archivo:** `order_executor/order_executor.py`
**Líneas:** 27-31
**Descripción:** Usa `order_event.symbol` directamente, que puede venir como `"XAUUSDc"` en un momento y `"XAUUSD"` en otro.
**Impacto:** Un símbolo con sufijo diferente evade la blacklist.
**Recomendación:** Normalizar el símbolo antes de insertar en `_error_blacklist`.

---

#### 20. `order_executor/order_executor.py:428` — Posible `AttributeError`
**Archivo:** `order_executor/order_executor.py`
**Línea:** 428
**Descripción:** `self.connector.get_symbol_info(position.symbol).ask` sin verificar que `get_symbol_info` no sea `None`.
**Impacto:** Crash al cerrar posiciones si el símbolo no se encuentra.
**Recomendación:** Agregar validación `if symbol_info is None: return`.

---

#### 21. `platform_connector/platform_connector.py:179` — `account_info()._asdict()` sin verificar `None`
**Archivo:** `platform_connector/platform_connector.py`
**Línea:** 179
**Descripción:** Si `mt5.account_info()` retorna `None`, se lanza `AttributeError`.
**Impacto:** Crash al iniciar la aplicación si MT5 no devuelve info de cuenta.
**Recomendación:** Verificar `if account_info is None: raise Exception(...)`.

---

#### 22. `order_executor/break_even_manager.py:57-60` — Vinculación automática de posiciones no relacionadas
**Archivo:** `order_executor/break_even_manager.py`
**Líneas:** 57-60
**Descripción:** Si `linked_ticket` es 0, busca cualquier posición abierta del mismo símbolo para vincular.
**Impacto:** Dos posiciones independientes del mismo símbolo se vinculan erróneamente, moviendo SL de una cuando la otra alcanza TP1.
**Recomendación:** Vincular solo posiciones que se sabe que pertenecen a la misma entrada dual (por magic number, comentario o ticket relación).

---

#### 23. `order_executor/break_even_manager.py:265` — Lógica confusa de `is_tp1_position`
**Archivo:** `order_executor/break_even_manager.py`
**Línea:** 265
**Descripción:** `abs(initial_tp - tp1) < abs(initial_tp - tp2)` para determinar si la posición es TP1. Si las distancias son iguales, el resultado es impredecible.
**Impacto:** Cierre parcial incorrecto.
**Recomendación:** Usar comparación explícita o marcar la posición al crearla como TP1/TP2.

---

#### 24. `utils/symbol_utils.py:79` — `normalize_symbol` captura "XAUUSD" prematuramente
**Archivo:** `utils/symbol_utils.py`
**Línea:** 79
**Descripción:** La condición `if upper.startswith("XAUUSD"): return "XAUUSD"` se ejecuta antes de verificar `KNOWN_SYMBOLS`. Si llega un símbolo como `"XAUUSDX"` (no estándar), se normaliza a `XAUUSD` incorrectamente.
**Impacto:** Símbolos desconocidos con prefijo XAUUSD se mapean incorrectamente.
**Recomendación:** Mover esta regla después de la verificación de `KNOWN_SYMBOLS` o hacerla más estricta.

---

#### 25. `events/events.py:68` — Inconsistencia en `risk_pct_override`
**Archivo:** `events/events.py`
**Línea:** 68
**Descripción:** En `DataEvent` es `Optional[float] = None`, pero en `SignalEvent`, `SizingEvent` y `OrderEvent` es `float = 0.0`.
**Impacto:** Al copiar eventos, un `None` se convierte en `0.0`, perdiendo la distinción entre "no seteado" y "cero".
**Recomendación:** Estandarizar como `Optional[float]` en todos los eventos.

---

#### 26. `ai/trading_ai.py:82` — `IndexError` potencial
**Archivo:** `ai/trading_ai.py`
**Línea:** 82
**Descripción:** `return available_strategies[0]` si `available_strategies` está vacío.
**Impacto:** Crash en `select_strategy` cuando no hay estrategias disponibles.
**Recomendación:** Retornar `None` o string vacío, y manejar el caso en el llamador.

---

#### 27. `news/news_protection.py:38` — `logger` no importado
**Archivo:** `news/news_protection.py`
**Línea:** 38
**Descripción:** Usa `logger.debug` pero no importa `logging` ni crea un logger.
**Impacto:** `NameError` al intentar cargar el calendario económico.
**Recomendación:** Agregar `import logging` y `logger = logging.getLogger(__name__)`.

---

### MEDIO

#### 28. `signal_generator/signal_generator.py:289` — Cálculo de `tp_distance` con valores nulos
**Archivo:** `signal_generator/signal_generator.py`
**Línea:** 289
**Descripción:** `abs(signal_event.tp - signal_event.target_price) / (bars["close"].iloc[-1] * 0.0001)` si `target_price` es 0.0.
**Impacto:** División por valores incorrectos o `ZeroDivisionError`.
**Recomendación:** Validar `target_price > 0` antes del cálculo o usar rama alternativa segura.

---

#### 29. `signal_generator/signals/signal_xau_extreme.py:221` — TP usa mismo mínimo que SL
**Archivo:** `signal_generator/signals/signal_xau_extreme.py`
**Línea:** 221
**Descripción:** `tp_distance_points = max(self.tp_atr_mult * atr_points, min_stop_points)`. Si el TP calculado es menor que el mínimo de stops, se iguala al mínimo de SL.
**Impacto:** TP demasiado cercano, relación riesgo/beneficio destruida.
**Recomendación:** Usar `min_stop_points` solo para SL; para TP usar un mínimo independiente o relativo.

---

#### 30. `risk_manager/risk_manager.py:118` — Valor de posición igual para BUY y SELL
**Archivo:** `risk_manager/risk_manager.py`
**Línea:** 118
**Descripción:** Retorna `value_traded_in_account_ccy` tanto para BUY como para SELL sin distinguir el precio de entrada (bid vs ask).
**Impacto:** El cálculo de leverage y riesgo no considera el spread, pudiendo sobreestimar la capacidad de apalancamiento.
**Recomendación:** Usar `bid` para BUY y `ask` para SELL en el cálculo del valor de posición.

---

#### 31. `risk_manager/risk_manager.py:113` — Conversión de moneda puede retornar 0.0
**Archivo:** `risk_manager/risk_manager.py`
**Línea:** 113
**Descripción:** Si no encuentra el par de divisas, retorna 0.0, haciendo que el valor de la posición sea 0 y el risk manager no aplique restricciones.
**Impacto:** Apalancamiento ilimitado en conversiones fallidas.
**Recomendación:** Retornar `None` o lanzar excepción, y manejarla en el llamador.

---

#### 32. `data_provider/data_provider.py:94-96` — Detención agresiva por fallos
**Archivo:** `data_provider/data_provider.py`
**Líneas:** 94-96
**Descripción:** 3 fallos consecutivos en `check_for_new_data` disparan `RuntimeError` y detienen la aplicación.
**Impacto:** Falsos positivos por latencia temporaria de MT5 detienen el trading.
**Recomendación:** Implementar backoff exponencial y un circuito breaker más tolerante (ej. 10 fallos en 5 minutos).

---

#### 33. `trading_director/trading_director.py:36` — Referencia circular
**Archivo:** `trading_director/trading_director.py`
**Línea:** 36
**Descripción:** `self.order_executor.trading_director = self`. Crea una dependencia circular entre `TradingDirector` y `OrderExecutor`.
**Impacto:** Posibles fugas de memoria y dificultad para hacer testing/cleanup.
**Recomendación:** Usar un patrón de eventos o callback en lugar de referencia directa.

---

#### 34. `trading_app.py:150-151` — Inyección tardía frágil
**Archivo:** `trading_app.py`
**Líneas:** 150-151
**Descripción:** Se asignan `trading_brain.order_executor` y `trading_brain.break_even_manager` después de la instanciación. Si se olvida, el sistema falla silenciosamente.
**Impacto:** Inestabilidad en tiempo de ejecución.
**Recomendación:** Usar inyección de dependencias formal (constructor o framework DI) o al menos asserts después de la asignación.

---

### BAJO

#### 35. Uso extensivo de `print` en lugar de `logging`
**Archivos:** `signal_generator.py`, `signal_xau_extreme.py`, `order_executor.py`, `break_even_manager.py`, `trading_director.py`
**Descripción:** Uso de `print` mezclado con `logging`.
**Impacto:** Dificulta filtrado por nivel, redirección a archivos y monitoreo.
**Recomendación:** Estandarizar en `logging` con niveles apropiados.

---

#### 36. `config.py:167` — Inconsistencia `fib_lookback`
**Archivo:** `config.py`
**Línea:** 167
**Descripción:** `SMART_MONEY_DEFAULT_PROPS["fib_lookback"] = 30` pero `FIB_SCALP_LOOKBACK = 20`.
**Impacto:** Estrategia Fibonacci usa lookback inconsistente según dónde se lea.
**Recomendación:** Unificar en una sola constante.

---

#### 37. `portfolio/portfolio.py:147-152` — Consulta MT5 en cada verificación de categoría
**Archivo:** `portfolio/portfolio.py`
**Líneas:** 147-152
**Descripción:** `can_open_position` llama a `get_strategy_open_positions()` que consulta a MT5, y luego itera para contar por categoría.
**Impacto:** Latencia alta y posibles timeouts en flujos críticos.
**Recomendación:** Implementar caché de posiciones con TTL corto (ej. 1-2 segundos).

---

#### 38. `trading_director/trading_director.py:209` — `_breakeven_check_interval` muy frecuente
**Archivo:** `trading_director/trading_director.py`
**Línea:** 209
**Descripción:** 1.0 segundo de intervalo para revisar TP hits.
**Impacto:** Sobrecarga de CPU y consultas a MT5.
**Recomendación:** Aumentar a 2-5 segundos o hacerlo configurable.

---

#### 39. `data_provider/data_provider.py:28` — `_bars_cache_ttl` de 30 segundos
**Archivo:** `data_provider/data_provider.py`
**Línea:** 28
**Descripción:** En scalping extremo con timeframes de 5min, 30 segundos puede ser demasiado tiempo.
**Impacto:** Datos desactualizados en decisiones rápidas.
**Recomendación:** Reducir a 5-10 segundos o hacerlo configurable por timeframe.

---

#### 40. `utils/utils.py` — Clase innecesaria
**Archivo:** `utils/utils.py`
**Descripción:** `class Utils` con un solo método estático.
**Impacto:** Over-engineering.
**Recomendación:** Convertir en módulo con función `dateprint()`.

---

### INFORMATIVO

#### 41. No hay tests de integración
**Descripción:** Los tests existentes son unitarios aislados. No hay pruebas del flujo completo `DataEvent → SignalEvent → SizingEvent → OrderEvent → ExecutionEvent`.
**Impacto:** Errores de integración solo se descubren en producción.
**Recomendación:** Agregar tests de integración con mocks de MT5.

---

#### 42. No hay manejo de reconexión MT5
**Descripción:** Si MT5 se desconecta, el sistema no intenta reconectar; `data_provider` detiene la aplicación.
**Impacto:** Tiempo de inactividad innecesario.
**Recomendación:** Implementar reconexión automática con backoff exponencial.

---

#### 43. No hay rate limiting en consultas MT5
**Descripción:** Múltiples módulos consultan `get_symbol_info`, `get_latest_tick`, `get_positions` sin límite de frecuencia.
**Impacto:** Posible bloqueo por parte del broker/MT5.
**Recomendación:** Implementar rate limiter o batch de consultas.

---

#### 44. Cola de eventos unbounded
**Descripción:** `Queue()` sin tamaño máximo. Si los productores son más rápidos que el consumidor, la memoria crece indefinidamente.
**Impacto:** Out of memory en sesiones largas.
**Recomendación:** Usar `Queue(maxsize=N)` y manejo de `queue.Full`.

---

#### 45. Circuit breaker usa balance, no equity
**Descripción:** `_daily_start_balance` se basa en `balance`, no en `equity`. El drawdown flotante no se considera.
**Impacto:** El circuit breaker puede no activarse ante pérdidas flotantes significativas.
**Recomendación:** Considerar `equity` en lugar de `balance` o usar ambos con umbrales diferentes.

---

#### 46. Falta validación de argumentos en muchas funciones
**Descripción:** No hay validación de tipos, rangos o valores nulos en constructores y métodos públicos.
**Impacto:** Errores difíciles de debuguear.
**Recomendación:** Usar `pydantic` para modelos de configuración o `assert`/`raise ValueError` en puntos de entrada.

---

#### 47. Variables globales en `config.py` sin protección
**Descripción:** `config.py` es un módulo con variables globales mutable.
**Impacto:** Race conditions en entornos multi-thread (aunque actualmente es single-thread con cola).
**Recomendación:** Usar dataclasses frozen o pydantic BaseModel para config.

---

#### 48. `signal_generator/signal_generator.py:419` — `get_latest_closed_bars` con 50 barras hardcodeado
**Archivo:** `signal_generator/signal_generator.py`
**Línea:** 419
**Descripción:** Para evaluar calidad de señal se piden 50 barras de 5min, pero la evaluación de spread usa 20.
**Impacto:** Latencia adicional innecesaria.
**Recomendación:** Hacer el número de barras configurable o reusar las ya obtenidas.

---

## Estado Actual del Sistema

### Puntos Fuertes
- Arquitectura basada en eventos desacoplada.
- Separación clara de responsabilidades (generación, sizing, riesgo, ejecución).
- Sistema de aprendizaje automático (`LearningEngine`, `StrategySelector`).
- Circuit breaker y protección de noticias implementados.
- Break-even manager con trailing stop.
- Normalización de símbolos robusta (`symbol_utils`).
- Estrategias específicas por activo (extreme signals).
- Trazabilidad y medición de versiones.

### Puntos Débiles
- Bugs críticos en lógica de filtrado de spread y triggers que impiden operar.
- Errores de programación básicos (`NameError`, `AttributeError`) en módulos centrales.
- Manejo de excepciones insuficiente y excepciones genéricas.
- Falta de tests en módulos críticos (extreme signals, order executor, trading director).
- Inconsistencias entre configuración y ejecución.
- Código duplicado en estrategias extreme (copy-paste de 4 archivos).
- Sin reconexión ni rate limiting para MT5.
- Cola de eventos sin límite.
- Cálculo incorrecto de profit_factor en ranking de estrategias.
- Circuit breaker diario se resetea en cada iteración, no al cambiar de día.

---

## Recomendaciones Priorizadas

### Prioridad 1 — Arreglar antes de cualquier operación en producción
1. Corregir `logger` no definido en `signal_generator.py:287`.
2. Corregir cálculo de `min_spread` en las 4 señales extreme.
3. Corregir condiciones de trigger con `or` en las 4 señales extreme.
4. Corregir código muerto en `_build_asset_strategy_map` (líneas 204-209).
5. Corregir cálculo de `profit_factor` en `trading_brain.py:522`.
6. Retornar `False` en `_is_signal_viable` ante excepciones.
7. Agregar `logger` faltante en `news_protection.py:38`.
8. Corregir `_daily_start_balance` en `reset_daily_circuit_breaker` para usar balance de inicio de día.
9. Corregir `order_executor.py:154-156` (código muerto).
10. Validar `get_symbol_info` no es `None` en `order_executor.py:428`.

### Prioridad 2 — Estabilizar el sistema
11. Implementar blacklist con símbolos normalizados en `order_executor.py`.
12. Estandarizar atributos de eventos (`risk_pct_override` como `Optional[float]`).
13. Agregar manejo de reconexión MT5 en `platform_connector.py`.
14. Implementar rate limiting o batch de consultas MT5.
15. Hacer la cola de eventos bounded con `Queue(maxsize=1000)`.
16. Implementar caché de posiciones en `Portfolio` con TTL.
17. Hacer configurable `_near_psychological_level` por activo.
18. Revisar lógica de vinculación de posiciones en `break_even_manager.py`.

### Prioridad 3 — Mejorar mantenibilidad
19. Eliminar código duplicado en señales extreme (crear clase base `BaseExtremeSignal`).
20. Reemplazar `print` por `logging` en todos los módulos.
21. Estandarizar nombres de atributos (snake_case consistente).
22. Agregar type hints y docstrings en métodos públicos.
23. Implementar tests de integración para el flujo completo de eventos.
24. Mover parámetros hardcodeados a `config.py`.
25. Validar argumentos de entrada con pydantic en puntos clave.

---

## Acciones Correctivas Inmediatas

Las siguientes acciones deben ejecutarse antes de operar en producción:

| # | Acción | Archivo(s) | Línea(s) |
|---|--------|-----------|----------|
| 1 | Agregar `logger = logging.getLogger(__name__)` | `signal_generator/signal_generator.py` | 1-15 |
| 2 | Eliminar sobrescritura de `asset_strategies` con `all_strategies` | `signal_generator/signal_generator.py` | 204-209 |
| 3 | Corregir cálculo de `min_spread` en 4 señales extreme | `signal_generator/signals/signal_*.py` | 170, 171, 173, 176 |
| 4 | Corregir condiciones de trigger imposibles en 4 señales extreme | `signal_generator/signals/signal_*.py` | 231/242, 224/235, 228/239, 224/235 |
| 5 | Corregir `profit_factor` en `trading_brain.py` | `brain/trading_brain.py` | 522 |
| 6 | Retornar `False` en excepción de `_is_signal_viable` | `signal_generator/signal_generator.py` | 340 |
| 7 | Agregar `logger` en `news_protection.py` | `news/news_protection.py` | 38 |
| 8 | Corregir reset diario de circuit breaker | `trading_director/trading_director.py` | 189-190 |
| 9 | Corregir cierre por mercado solo por activo | `trading_director/trading_director.py` | 233-258 |
| 10 | Corregir noticias para cerrar solo activos afectados | `trading_director/trading_director.py` | 347-374 |

---

## Conclusión

El proyecto V9_SCALPING_MAX_QUALITY tiene una base arquitectónica sólida, pero contiene errores críticos de programación que impiden su funcionamiento correcto en producción. La mayoría de los errores son de tipo:
- Variables no definidas (`logger`)
- Lógica de filtrado incorrecta (`min_spread`, triggers)
- Código muerto que anula funcionalidad (`_build_asset_strategy_map`)
- Cálculos matemáticos incorrectos (`profit_factor`)

**No se debe operar en producción sin corregir primero los hallazgos de severidad CRÍTICO.**

Una vez corregidos estos errores, el sistema tiene potencial para funcionar de manera estable y generar ganancias consistentes, especialmente con la cartera oficial actualizada (XAUUSD, EURUSD, GBPUSD, USDJPY) y las estrategias específicas por activo.

**Calificación Final: 4.2 / 10 — NO LISTO PARA PRODUCCIÓN**

---

*Generado por Kilo - Sistema de Auditoría Institucional*
*Fecha: 2026-08-05*
