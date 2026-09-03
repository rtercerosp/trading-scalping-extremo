import pandas as pd
import numpy as np
from src.features.triple_barrier import apply_triple_barrier


def audit_triple_barrier_labels(
    data: pd.DataFrame,
    pt_limit: float = 1.5,
    sl_limit: float = 1.0,
    time_limit: int = 15
) -> dict:
    """
    Audita la distribución de etiquetas generadas por el método Triple Barrera.

    Args:
        data: DataFrame con columna 'Close' (precios de cierre)
        pt_limit: Multiplicador de volatilidad para profit-take
        sl_limit: Multiplicador de volatilidad para stop-loss
        time_limit: Periodos hacia adelante para barrera de tiempo

    Returns:
        Diccionario con conteos, porcentajes y métricas de balance
    """
    labeled = apply_triple_barrier(data.copy(), pt_limit, sl_limit, time_limit)
    targets = labeled['Target'].dropna().astype(int)

    total = len(targets)
    counts = targets.value_counts().sort_index()
    percentages = (counts / total * 100).round(2)

    result = {
        'total_samples': total,
        'counts': counts.to_dict(),
        'percentages': percentages.to_dict(),
        'class_balance_ratio': (counts.min() / counts.max()).round(4) if len(counts) > 1 else 0.0,
        'imbalance_warnings': []
    }

    print("=" * 60)
    print("TRIPLE BARRIER LABEL AUDIT REPORT")
    print("=" * 60)
    print(f"Parameters: pt_limit={pt_limit}, sl_limit={sl_limit}, time_limit={time_limit}")
    print(f"Total labeled samples: {total}")
    print()
    print("CLASS DISTRIBUTION:")
    for cls in [-1, 0, 1]:
        cnt = counts.get(cls, 0)
        pct = percentages.get(cls, 0.0)
        label_name = {-1: 'STOP-LOSS (-1)', 0: 'TIME-BARRIER (0)', 1: 'PROFIT-TAKE (1)'}[cls]
        print(f"  {label_name}: {cnt:>6} ({pct:>5.2f}%)")
        if pct < 10.0:
            result['imbalance_warnings'].append(
                f"CRITICAL: Class {cls} ({label_name}) is {pct:.2f}% (< 10%)"
            )

    print()
    print(f"CLASS BALANCE RATIO (min/max): {result['class_balance_ratio']:.4f}")
    print()

    if result['imbalance_warnings']:
        print("WARNING:")
        for w in result['imbalance_warnings']:
            print(f"  - {w}")
    else:
        print("[OK] No critical class imbalance detected (all classes >= 10%)")

    print("=" * 60)

    return result


def generate_synthetic_price_data(
    n_samples: int = 5000,
    start_price: float = 100.0,
    drift: float = 0.0001,
    base_vol: float = 0.015,
    vol_of_vol: float = 0.3,
    seed: int = 42
) -> pd.DataFrame:
    """
    Genera datos sintéticos de precios OHLCV con volatilidad estocástica (Heston-like).
    """
    np.random.seed(seed)

    returns = np.zeros(n_samples)
    volatility = np.zeros(n_samples)
    volatility[0] = base_vol

    for i in range(1, n_samples):
        # Stochastic volatility (CIR-like process)
        vol_innovation = np.random.randn() * vol_of_vol * np.sqrt(volatility[i-1])
        volatility[i] = max(0.001, volatility[i-1] + 0.1 * (base_vol - volatility[i-1]) + vol_innovation)

        # Returns with stochastic volatility
        returns[i] = drift + np.random.randn() * volatility[i]

    # Generate OHLC from close prices
    close_prices = start_price * np.exp(np.cumsum(returns))

    # Generate realistic OHLC
    # High/Low based on intraday volatility
    intraday_vol = np.abs(np.random.randn(n_samples)) * volatility * 0.5 + 0.0005
    high_prices = close_prices * (1 + intraday_vol)
    low_prices = close_prices * (1 - intraday_vol)

    # Open = previous close + gap
    open_prices = np.roll(close_prices, 1)
    open_prices[0] = start_price
    # Add small gap
    gap = np.random.randn(n_samples) * volatility * 0.1
    open_prices = open_prices * (1 + gap)

    # Ensure OHLC consistency
    high_prices = np.maximum(high_prices, np.maximum(open_prices, close_prices))
    low_prices = np.minimum(low_prices, np.minimum(open_prices, close_prices))

    # Volume
    volume = np.random.lognormal(10, 0.5, n_samples)

    df = pd.DataFrame({
        'Open': open_prices,
        'High': high_prices,
        'Low': low_prices,
        'Close': close_prices,
        'Volume': volume
    })

    return df


if __name__ == '__main__':
    print("Generating synthetic price data with stochastic volatility...")
    data = generate_synthetic_price_data(n_samples=10000)

    print("Running Triple Barrier Label Audit...")
    result = audit_triple_barrier_labels(
        data,
        pt_limit=1.5,
        sl_limit=1.0,
        time_limit=15
    )

    print("\n[OK] TASK-030 Simulation Complete: Triple Barrier Label Validation")
    print(f"Result dict keys: {list(result.keys())}")