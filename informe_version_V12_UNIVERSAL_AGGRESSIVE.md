# Informe de Versión V12_UNIVERSAL_AGGRESSIVE
**Fecha:** 2026-08-06
**Estado:** LISTO PARA IMPLEMENTACIÓN Y VALIDACIÓN
**Objetivo principal:** Extender la estrategia hiper-agresiva "Cero Pérdidas" a Oro (XAUUSD) y Forex, e introducir una nueva estrategia de reversión para el oro.

---

## Resumen Ejecutivo

La versión **V12_UNIVERSAL_AGGRESSIVE** capitaliza el éxito de la V11 y expande su filosofía a todos los activos principales. Hereda la base "Cero Pérdidas" de V10 y la especialización para cripto de V11, introduciendo ahora parámetros hiper-agresivos para las categorías 'gold' y 'forex'.

El objetivo es universalizar la toma de ganancias rápidas y la protección acelerada del capital. Además, se añade una nueva estrategia, `SignalGoldMomentumReversal`, diseñada específicamente para la volatilidad del oro.

### Características Principales de V12

- **Nueva Estrategia `SignalGoldMomentumReversal`**:
  - **Especializada en Oro**: Diseñada para la categoría de activos "gold".
  - **Detección de Extremos**: Utiliza RSI y la distancia a una EMA lenta para identificar momentos en que el precio está sobreextendido.
  - **Confirmación por Reversión**: Busca patrones de velas de reversión (como envolventes) para confirmar el cambio de dirección antes de entrar.
  - **Calidad de Señal Dinámica**: El `quality_score` se basa en la fuerza de la señal de RSI y la calidad del patrón de velas.

- **Parámetros "Zero Loss" Agresivos para Oro y Forex**:
  - **Break-even Acelerado para Oro**: El SL se mueve a precio de entrada cuando se alcanza el **30%** del Take Profit.
  - **Break-even Rápido para Forex**: El SL se mueve a precio de entrada al alcanzar el **40%** del Take Profit.
  - **Trailing Stops más Reactivos**: Se activan antes y siguen al precio de forma más ajustada para asegurar ganancias en movimientos rápidos en todas las categorías.

- **Arquitectura de Versiones Jerárquica**:
  - El sistema ahora aplica la configuración de forma jerárquica: V12 (oro/forex) -> V11 (crypto) -> V10 (base). Esto asegura que cada categoría de activo reciba los parámetros más optimizados disponibles.

---

## Parámetros V12 en config.py

Se ha añadido una nueva sección en `config.py` para la V12. Estos parámetros **sobreescriben** los de V10 para 'gold' y 'forex'.

```python
STRATEGY_VERSION = "V12_UNIVERSAL_AGGRESSIVE"

# --- V11 CRYPTO VOLATILITY (Heredado por V12) ---
V11_CRYPTO_VOLATILITY_ENABLED: bool = True
V11_CRYPTO_PARAMS: dict[str, dict] = {
    "crypto": {
        "break_even_trigger_pct": 0.35,
        "reverse_protection_pct": 0.40,
        "trailing_activation_pct": 0.0025,
        "trailing_offset_pct": 0.0012,
    }
}

# --- V12 UNIVERSAL AGGRESSIVE ---
V12_UNIVERSAL_AGGRESSIVE_ENABLED: bool = True
V12_AGGRESSIVE_PARAMS: dict[str, dict] = {
    "gold": {
        "break_even_trigger_pct": 0.30,      # Breakeven ultra-rápido (30% del TP)
        "reverse_protection_pct": 0.35,
        "trailing_activation_pct": 0.0020,   # Trailing se activa antes
        "trailing_offset_pct": 0.0010,     # Trailing muy ajustado
    },
    "forex": {
        "break_even_trigger_pct": 0.40,      # Breakeven rápido (40% del TP)
        "reverse_protection_pct": 0.45,
        "trailing_activation_pct": 0.0015,
        "trailing_offset_pct": 0.0008,
    }
}
```

---

## Cambios por Archivo

### `signal_generator/signals/signal_gold_momentum_reversal.py` (Nuevo)
- Creada la nueva estrategia que busca reversiones en picos de momentum para el oro.

### `config.py`
- Se establece `STRATEGY_VERSION = "V12_UNIVERSAL_AGGRESSIVE"`.
- Se añade la sección `V11_CRYPTO_PARAMS` (previamente conceptual) y `V12_AGGRESSIVE_PARAMS`.

### `signal_generator/signal_generator.py`
- Se registran las nuevas estrategias `SignalCryptoVolatilityBreakout` y `SignalGoldMomentumReversal`.
- Se actualiza la lógica de consenso para que V12 y V11 usen un `quality_threshold` de 65.

### `brain/trading_brain.py`
- El método `get_zero_loss_params` se reescribe para ser consciente de V12, V11 y V10, aplicando los parámetros correctos según la versión y la categoría del activo.

### `trading_app.py`
- Se registran las versiones V11 y V12, estableciendo V12 como la activa.

---

## Plan de Acción

1.  **Aplicar todos los cambios de código** detallados a continuación.
2.  **Ejecutar `trading_app.py` en modo prueba (`--test-mode`)**: Validar que la nueva estrategia `SignalGoldMomentumReversal` genere señales para XAUUSD y que los parámetros de break-even agresivos se apliquen a todas las categorías.
3.  **Monitorear los logs**: Verificar que para el oro, el break-even se active al 30% del TP, para forex al 40%, y para cripto al 35%.
4.  **Pasar a producción**: Una vez validado el comportamiento, ejecutar en modo real con supervisión.