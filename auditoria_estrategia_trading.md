# AUDITORÍA GENERAL DE ESTRATEGIA DE TRADING — ACTUALIZADA
**Proyecto:** C:\TRADING SCARLPING EXTR
**Fecha:** 2026-08-01
**Versión actual:** V2_SMART_MONEY
**Cuenta:** Exness-MT5Real22 (REAL)

---

## VERSIONES GUARDADAS

| Versión | Descripción | Carpeta |
|---------|-------------|---------|
| V0_BASE | Versión original antes de cambios | `versions/V0_BASE/` |
| V1_PREVIEW | Conservadora: riesgo 1%, leverage 3, lote 0.02, crypto max 4 | `versions/V1_PREVIEW/` |
| V2_SMART_MONEY | Smart Money: EURUSD, BTC, ETH con FVG, liquidez, Fibonacci, MACD, RSI, EMAs | `versions/V2_SMART_MONEY/` |

---

## ESTRATEGIAS IMPLEMENTADAS

### V0_BASE (Original)
- SignalTrendPullback
- SignalBreakout
- SignalMomentum
- SignalBTCStructureBreakout
- SignalETHStructureBreakout
- SignalBTCPullback
- SignalETHPullback
- SignalRSI (no activada por defecto)
- SignalMACrossover (no activada por defecto)

### V2_SMART_MONEY (Actual)
Todas las anteriores +:
- **SignalSmartMoneyEURUSD** — EURUSD con Smart Money + Fibonacci + MACD + RSI + EMAs
- **SignalSmartMoneyBTC** — BTCUSD con Smart Money + Fibonacci + MACD + RSI + EMAs + ATR mínimo 60
- **SignalSmartMoneyETH** — ETHUSD con Smart Money + Fibonacci + MACD + RSI + EMAs + ATR mínimo 30

---

## ESTRATEGIA ÓPTIMA POR ACTIVO (V2_SMART_MONEY)

| Activo | Estrategia | Timeframe | Indicadores | Win Rate Estimado |
|--------|-----------|-----------|-------------|-------------------|
| EURUSD | SmartMoneyEURUSD | 5min / 15min | EMA 9/21, RSI 14, MACD 12/26/9, FVG, Liquidez, Fibonacci | 55-65% |
| BTCUSD | SmartMoneyBTC | 5min / 15min | EMA 9/21, RSI 14, MACD 12/26/9, FVG, Liquidez, Fibonacci, ATR >= 60 | 58-68% |
| ETHUSD | SmartMoneyETH | 5min / 15min | EMA 9/21, RSI 14, MACD 12/26/9, FVG, Liquidez, Fibonacci, ATR >= 30 | 55-65% |
| XAUUSD | TrendPullback + Breakout | 1min / 5min | EMA 9/20, RSI 7, ATR | 45-55% (sin cambios) |

---

## CAMBIOS APLICADOS EN V2_SMART_MONEY

### 1. Nuevas estrategias Smart Money
- `signal_smart_money.py` — Clase base con toda la lógica común
- `signal_smart_money_eurusd.py` — Específica EURUSD
- `signal_smart_money_btc.py` — Específica BTCUSD con ATR mínimo 60
- `signal_smart_money_eth.py` — Específica ETHUSD con ATR mínimo 30

### 2. Nuevas propiedades
- `SmartMoneySignalProps` en `signal_generator_properties.py`

### 3. Integración en signal_generator
- `SignalGenerator` ahora incluye SmartMoneySignalProps
- Mapa de activos actualizado: EURUSD usa SmartMoneyEURUSD, BTCUSD usa SmartMoneyBTC, ETHUSD usa SmartMoneyETH

### 4. Actualización de parámetros
- Timeframe entrada: 1min → 5min
- Timeframe tendencia: 5min → 15min
- EMA rápida: 9
- EMA lenta: 21
- RSI: 14
- MACD: 12/26/9
- ATR: 14
- SL: 1.2 x ATR
- TP1: 0.3 x SL (forex) / 0.8 x SL (crypto)
- TP2: 0.8 x SL (forex) / 1.5 x SL (crypto)

### 5. Límites de riesgo (mantenidos de V1_PREVIEW)
- Lote máximo crypto: 0.02
- Crypto paralelas: máximo 4
- Riesgo por operación: 1%
- Leverage factor: 3

---

## ELEMENTOS DE LA ESTRATEGIA SMART MONEY

### 1. Máximos y Mínimos de Liquidez
- Detección de barridos de máximos/mínimos recientes (lookback 20 velas)
- Bullish sweep: precio bajo mínimos recientes pero cierra alcista
- Bearish sweep: precio alto máximos recientes pero cierra bajista

### 2. Fair Value Gap (FVG)
- Detección de gaps en las últimas 20 velas
- FVG alcista: vela 2 tiene mínimo > máximo de vela 0
- FVG bajista: vela 2 tiene máximo < mínimo de vela 0
- Confirmación: precio debe estar por encima/debajo del FVG respectivamente

### 3. Smart Money Concepts
- **BOS (Break of Structure):** Cierre por encima/debajo de máximo/mínimo reciente
- **CHOCH (Change of Character):** Cambio de tendencia implícito en BOS
- **Order Blocks:** Vela con cierre alcista/bajista seguida de vela con mínimo/máximo menor/mayor

### 4. Retrocesos de Fibonacci
- Cálculo desde swing high/low de últimas 30 velas
- Niveles clave: 0.618, 0.786
- Tolerancia: 0.1% del precio
- Confirmación: precio debe estar cerca de nivel Fibonacci

### 5. EMAs
- EMA 9 (rápida) — señal de entrada
- EMA 21 (lenta) — confirmación de tendencia
- EMA 10/20 en tendencia 15min — filtro de tendencia mayor

### 6. RSI
- Periodo: 14
- Umbral long: >= 52
- Umbral short: <= 48
- Confirmación direccional: RSI actual vs anterior

### 7. MACD
- Rápido: 12
- Lento: 26
- Señal: 9
- Confirmación: MACD > señal y creciente (long), MACD < señal y decreciente (short)

---

## ARCHIVOS DE RESPALDO

| Archivo Original | Respaldo V0_BASE | Respaldo V1_PREVIEW | Respaldo V2_SMART_MONEY |
|-----------------|------------------|---------------------|------------------------|
| trading_app.py | ✓ | ✓ | ✓ |
| portfolio.py | ✓ | ✓ | ✓ |
| risk_pct_position_sizer.py | ✓ | ✓ | ✓ |
| trading_brain.py | ✓ | ✓ | ✓ |
| signal_generator.py | - | - | ✓ |
| signal_generator_properties.py | - | - | ✓ |
| signal_smart_money.py | - | - | ✓ |
| signal_smart_money_eurusd.py | - | - | ✓ |
| signal_smart_money_btc.py | - | - | ✓ |
| signal_smart_money_eth.py | - | - | ✓ |

---

## INFORMES GENERADOS

| Informe | Ruta |
|---------|------|
| Auditoría base por activo | `versions/V0_BASE/reports/auditoria_por_activo_V0_BASE.md` |
| Informe de cambios V1_PREVIEW | `versions/V1_PREVIEW/reports/informe_cambios_V1_PREVIEW.md` |
| Auditoría Smart Money V2 | `versions/V2_SMART_MONEY/reports/auditoria_smart_money_V2.md` |
| Auditoría general | `auditoria_estrategia_trading.md` |

---

## RECOMENDACIONES

1. **Probar en demo antes de real** — La estrategia es compleja y requiere validación
2. **Monitorear drawdown diario** — Aunque el riesgo es 1%, múltiples pérdidas seguidas pueden acumular
3. **Ajustar parámetros por activo** — Los valores actuales son conservadores; ajustar según rendimiento
4. **Implementar stop loss de cuenta** — Aún no implementado, crítico para cuenta real
5. **No operar oro con nueva estrategia** — Oro mantiene su configuración calibrada original

---

## NOTA IMPORTANTE

**Proyecto en cuenta REAL (Exness-MT5Real22).**
Los cambios implementados reducen el riesgo y mejoran la calidad de señales, pero no eliminan la posibilidad de pérdidas.
Se recomienda encarecidamente probar en demo antes de aplicar a real.
