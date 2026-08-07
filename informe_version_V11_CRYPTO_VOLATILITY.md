# Informe de Versión V11_CRYPTO_VOLATILITY
**Fecha:** 2026-08-05  
**Estado:** LISTO PARA IMPLEMENTACIÓN Y VALIDACIÓN  
**Objetivo principal:** Estrategia hiper-agresiva para Criptomonedas (BTC, ETH) sobre la base "Cero Pérdidas" de V10.

---

## Resumen Ejecutivo

En respuesta a la necesidad de una operativa más decisiva y rentable para activos volátiles como Bitcoin y Ethereum, se introduce la versión **V11_CRYPTO_VOLATILITY**. Esta versión hereda la filosofía "Cero Pérdidas" de V10 pero la especializa con parámetros mucho más agresivos y una nueva estrategia diseñada para capturar los movimientos explosivos característicos de las criptomonedas.

El objetivo es simple: entrar rápido en breakouts de volatilidad, asegurar la posición moviendo el Stop Loss a breakeven de forma acelerada y usar un trailing stop ajustado para maximizar las ganancias en movimientos rápidos.

### Características Principales de V11

- **Nueva Estrategia `SignalCryptoVolatilityBreakout`**:
  - **Especializada en Cripto**: Diseñada exclusivamente para la categoría de activos "crypto".
  - **Detección de Squeeze**: Identifica períodos de baja volatilidad (usando Bollinger Bands) que suelen preceder a movimientos fuertes.
  - **Confirmación por Volumen**: El breakout solo es válido si está acompañado por un aumento significativo del volumen, filtrando señales falsas.
  - **Calidad de Señal Dinámica**: El `quality_score` se calcula en función de la fuerza del breakout, priorizando las entradas "perfectas".

- **Parámetros "Zero Loss" Hiper-Agresivos para Cripto**:
  - **Break-even Acelerado**: El SL se mueve a precio de entrada cuando se alcanza solo el **35%** del Take Profit (antes 50%). Esto asegura la posición mucho más rápido.
  - **Trailing Stop más Reactivo**: El trailing stop se activa antes y sigue al precio de forma más ajustada para capturar la mayor parte del impulso.

- **Soporte Completo para Bitcoin**: Se han realizado los ajustes necesarios en la configuración para asegurar que `BTCUSD` (o `BTCUSDc`) sea un activo de primera clase dentro del sistema, listo para ser operado.

---

## Parámetros V11 en config.py

Se ha añadido una nueva sección en `config.py` para la V11. Estos parámetros **sobreescriben** los de V10 únicamente para los activos de categoría "crypto".

```python
STRATEGY_VERSION = "V11_CRYPTO_VOLATILITY"

# --- V11 CRYPTO VOLATILITY (Herencia y especialización de V10) ---
V11_CRYPTO_VOLATILITY_ENABLED: bool = True
# Parámetros más agresivos para criptomonedas, que sobreescriben los de V10
V11_CRYPTO_PARAMS: dict[str, dict] = {
    "crypto": {
        "break_even_trigger_pct": 0.35,      # Breakeven más rápido (35% del TP)
        "reverse_protection_pct": 0.40,      # Cierre si retrocede 40% (más espacio)
        "trailing_activation_pct": 0.0025,   # Trailing se activa antes
        "trailing_offset_pct": 0.0012,     # Trailing más ajustado
    }
}
```

---

## Cambios por Archivo

### `signal_generator/signals/signal_crypto_volatility_breakout.py` (Nuevo)
- Creada la nueva estrategia que busca breakouts de volatilidad en criptomonedas.

### `config.py`
- Se establece `STRATEGY_VERSION = "V11_CRYPTO_VOLATILITY"`.
- Se añade la sección `V11_CRYPTO_PARAMS` con la configuración agresiva.
- Se asegura que `BTCUSD` y `BTCUSDc` estén presentes en `LEARNING_ASSET_SPECIFIC_PARAMS` y `EXTREME_SCALPING_PARAMS`.

### `signal_generator/signal_generator.py`
- Se registra la nueva estrategia `SignalCryptoVolatilityBreakout`.
- Se añade lógica para que la V11 use un `quality_threshold` de 65.

### `brain/trading_brain.py`
- El método `get_zero_loss_params` ahora es consciente de la V11. Si la versión está activa y el activo es una criptomoneda, aplicará los parámetros hiper-agresivos de V11; de lo contrario, usará los de V10.

---

## Plan de Acción y Próximos Pasos

1.  **Aplicar los cambios de código** que se detallan a continuación.
2.  **Actualizar tu archivo `.env`**: Asegúrate de que `BTCUSDc` (o el símbolo de Bitcoin de tu bróker) esté en la lista `TRADING_SYMBOLS`. Por ejemplo:
    `TRADING_SYMBOLS='XAUUSDc,EURUSDc,GBPUSDc,USDJPYc,ETHUSDc,BTCUSDc'`
3.  **Ejecutar `trading_app.py` en modo prueba (`--test-mode`)**: Valida que la nueva estrategia `SignalCryptoVolatilityBreakout` genere señales para ETH y BTC.
4.  **Monitorear los logs**: Verifica que para las operaciones de cripto, el break-even se active más rápido (al 35% del TP) y que el trailing stop siga al precio de cerca.
5.  **Pasar a producción**: Una vez validado el comportamiento, ejecutar en modo real con supervisión.

Esta implementación responde directamente a tu petición de velocidad, agresividad y una gestión de riesgo férrea para capitalizar la naturaleza de las criptomonedas.