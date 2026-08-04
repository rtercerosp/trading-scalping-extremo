# Changelog V4.1.0 Portable

## V7.0.2 - 2026-08-02 - Multi-Strategy Consensus & Hardened Execution

- Corregido BreakEvenManager: signos invertidos en SL de breakeven (BUY/SELL) y buffer dinamico basado en `trade_stops_level * point` del broker.
- Corregido BreakEvenManager: validacion de precio actual antes de `modify_position_sl` para evitar retcode 10016 ("Invalid stops").
- Corregido RiskPctPositionSizer: si `volume_min > max_allowed_volume`, retorna 0.0 y salta la orden en lugar de crear loop imposible.
- Corregido SignalMACrossover: media lenta usaba todas las barras (`mean()`) en lugar de las ultimas `slow_period`.
- Corregido SignalMACrossover: separadas unidades de SL/TP (puntos vs precio) para evitar valores negativos.
- Corregido SignalSmartMoneyEURUSD: eliminado codigo duplicado de ask/bid y recalculos de SL/TP que sobrescribian valores correctos (version principal, V2 y V3).
- Corregido TradingBrain._compute_adaptive_params: agregada rama especifica para XAUUSD con parametros calibrados (sl_atr_mult=0.8, tp_atr_mult=3.5, risk_pct=0.008).
- Corregido LearningEngine: defaults XAUUSD y limites ampliados (tp_atr_mult max 5.0, sl_atr_mult min 0.5).
- Agregado sistema de cuarentena en StrategySelector: estrategias con PF<0.80 y trades>=15 entran en cuarentena por 50 minutos.
- Agregada carga de backtest_results.json en TradingAI._load_backtest_scores() para activar cuarentena desde el arranque.
- Agregado filtro de noticias inteligente para todos los activos: TradingBrain.should_block_for_news() decide segun impacto y rendimiento historico.
- Agregados eventos macro ampliados en NewsProtection: US CPI, Fed, NFP, ECB, UK CPI, Japan GDP, EU GDP, US Retail Sales, US PPI.
- Modificado TradingDirector: filtro de noticias ya no bloquea ciegamente; consulta a la IA y registra decisiones.
- Eliminado limite duro MAX_VOLUME_BY_SYMBOL=0.02 en RiskPctPositionSizer para ETH/BTC/SOL; ahora usa volume_max del broker o limites del Portfolio.
- Modificado TradingBrain.get_strategy_recommendation(): excluye estrategias en cuarentena en todos los fallbacks.
- Modificado SignalGenerator._is_signal_viable(): umbrales spread/volatilidad diferenciados por categoria (crypto/oro mas permisivos).
- Modificado PositionSizer y trading_app.py: inyectan Portfolio al RiskPctPositionSizer para limites dinamicos por activo.
- Modificado Portfolio: max_total_positions=12, max_positions_per_symbol=3, max_positions_by_symbol incluye XAUUSD/EURUSD/BTCUSD/ETHUSD, categorias rebalanceadas crypto=3, gold=3, forex=3.
- Modificado SignalGenerator._is_signal_viable(): umbrales spread/volatilidad diferenciados por categoria de activo (oro mas permisivo: tp_threshold=2.0, atr_threshold=3.0).
- Modificado SignalRSI.generate_signal(): SL/TP minimos diferenciados por categoria (crypto: 300/600 pts, gold: 150/300 pts) para evitar volumenes desproporcionados.
- Modificado SignalTrendPullback._compute_tp_levels(): multiplicadores de TP para gold ajustados a tp1_mult=1.0, tp2_mult=2.0.
- Modificado SignalMomentum._compute_tp_levels(): multiplicadores de TP para gold ajustados a tp1_mult=1.0, tp2_mult=2.0.
- Modificado MaxLeverageFactorRiskManager._compute_adjusted_volume(): agregado limite de 50% del equity por posicion individual para evitar volumenes extremos.
- Modificado MaxLeverageFactorRiskManager._compute_adjusted_volume(): corregido signo negativo en posiciones SELL (ahora ambas direcciones suman valor absoluto en el calculo de leverage).
- Modificado RiskManager._compute_value_of_position_in_account_currency(): retorna valor positivo para SELL para que el leverage factor refleje la exposicion total real.
- Modificado TradingDirector._handle_signal_event(): agrega guard de portfolio (can_open_position) antes de llamar al position sizer.
- Modificado OrderExecutor.execute_order(): agrega segunda verificación de portfolio antes de enviar la orden a MT5, previniendo oversubscription en eventos simultaneos.
- Modificado TradingBrain.get_strategy_recommendation(): prioriza SignalSmartMoneyEURUSD dentro de las estrategias recomendadas para oro.
- Actualizado trading_method_versions.json: V7/V6/V5/V4 con categoria crypto=3, gold=3, forex=3.
- Modificado SignalBreakout, SignalMomentum, SignalTrendPullback: eliminada rama hardcodeada BTCUSD que ignoraba adaptive_params; ahora usan sl_atr_mult/tp_atr_mult del brain para todos los activos.
- Modificado TradingBrain._compute_adaptive_params(): BTCUSD con risk_pct reducido a 0.001 (WR<20%) y 0.002 (WR<40%); EURUSD con risk_pct=0.003 cuando WR<45%.
- Modificado SignalGenerator.generate_signal(): implementado consenso multi-estrategia; requiere al menos 2 estrategias confirmando la misma direccion antes de emitir una señal.
- Modificado SignalMACrossover: EMAs por defecto cambiadas a 50/200 para filtrar ruido de corto plazo.
- Modificado SignalTrendPullback: EMAs por defecto cambiadas a 50/200 y setup_ema_period a 50 para alinearse con la tendencia principal.
- Modificado SignalMACrossover: ahora combina EMA 50/200 (tendencia macro) con EMA 9/21 (trigger corto), manteniendo ambas herramientas sin descartar las EMAs pequeñas.
- Agregada estrategia SignalCandlestickPatterns: detecta patrones de velas (hammer, engulfing, pin bar, three soldiers/crows, doji) combinados con EMA 50/200 + EMA 9/21 y RSI para refuerzo de entrada.
- Modificado SignalGenerator: registra SignalCandlestickPatterns en el conjunto de estrategias para todos los activos.
- Modificado TradingDirector: agregado límite de drawdown diario del 5% del balance inicial. Si se alcanza, cierra todas las posiciones y detiene el trading por el resto del día.
- Modificado TradingDirector: agregado límite de pérdida máxima por operación del 1.5% del balance inicial. Si la señal supera este límite, se descarta.
- Modificado TradingDirector: agregado anti-duplicados. No se abre una nueva posición si ya existe una posición opuesta (BUY/SELL) en el mismo símbolo.
- Modificado BreakEvenManager: reemplazado break-even estático por trailing stop dinámico. Cuando TP1 se alcanza, el SL se mueve a break-even + buffer. Si el precio avanza >=0.3%, el SL se arrastra manteniendo un offset del 0.15%, permitiendo ganancias mayores.
- Modificado BreakEvenManager: agregada guarda para no intentar cerrar/modificar posiciones que ya no existen (retcode 10036).

## V7.0.1 - 2026-08-02 - Critical Fixes Knowledge Preloaded

- Corregido P&L de backtest en `ai/backtest_engine.py`: ahora convierte diferencias de precio a ganancia monetaria usando `trade_tick_value` y `trade_tick_size`. Los scores anteriores eran invalidos.
- Corregida fuga de credenciales en `discover_symbols.py`: login y server ahora se enmascaran en logs.
- Reseteado `ai/strategy_scores.json`: eliminadas entradas UNKNOWN con datos viejos (152K+ trades corruptos).
- Corregida indentacion corrupta en bloque `try/except` de backtest_engine.py.

## V7.0.0 - 2026-08-02 - Knowledge Preloaded

- Version interna renombrada a `V7_KNOWLEDGE_PRELOADED`.
- Pre-carga de conocimiento via backtesting historico (`ai/backtest_engine.py`) y reglas expertas (`ai/expert_rules.json`).
- Motor de backtesting ejecuta 10 estrategias sobre datos reales de MT5 para generar scores iniciales por estrategia/activo.
- Reglas expertas de correlacion inter-mercado (DXY, VIX, BTC.D, US10Y) y eventos macro (NFP, CPI, Fed, ECB).
- Script `run_preload.py` para orquestar la pre-carga antes del trading en vivo.
- Acceso a `ai/expert_rules.json` y `ai/backtest_results.json` desde TradingBrain.
- IA inicia con conocimiento previo en lugar de cero, reduciendo trades ciegos.

## V5.0.0 - 2026-08-02 - Asset Isolated Guarded

- Version interna renombrada a `V5_ASSET_ISOLATED_GUARDED`.
- Normalizacion central de simbolos con sufijos de broker.
- IA y cerebro ahora registran estrategia real por trade y aprendizaje por activo normalizado.
- Oro preservado fuera del ajuste adaptativo agresivo para no contaminar su estrategia ganadora.
- Correccion del reprocesamiento de deals cerrados mediante `closed_deal_ticket`.
- Nuevo informe operativo en `versions/V5_ASSET_ISOLATED_GUARDED/reports/`.

## V4.1.0 - 2026-07-31 - Portable

- Version empaquetable para copiar a cualquier equipo Windows.
- BTCUSD limitado a 0.5 lotes maximo.
- EURUSD: news filter saneado, solo bloquea en ventana real de noticias.
- NAS100 y XAUUSD+ sin cambios.
- Rutas relativas para evitar problemas de paths largos en Windows.
- Scripts portable_install.bat y portable_run.bat incluidos.
- Sin secrets: usar .env.example como base.

## V4.0.0 - Scalping Extremo V4

- Timeframe 1min.
- Sin limites practicos de cartera.
- Criptos 24/7; forex/metales cierren fin de semana y 17:00-18:00 BOL.
- Evaluacion institucional cada 5 minutos.
- Reporte cada 10 minutos.
