import sys
import os
import pandas as pd
import numpy as np
import vectorbt as vbt

# --- Path Setup for Module Imports ---
# This allows the script to be run from anywhere and still find the 'src' modules.
# It assumes the script is in 'src/backtest/'.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from data_splitter import DataSplitter
except ImportError:
    print("Error: No se pudo importar DataSplitter. Asegúrate de que 'src/data_splitter.py' existe.")
    sys.exit(1)


def run_vectorized_backtest(data: pd.DataFrame, fast_ma: int = 10, slow_ma: int = 30):
    """
    Ejecuta un backtest vectorizado usando una estrategia de cruce de medias móviles
    sobre los conjuntos de datos de entrenamiento, prueba y validación.

    Args:
        data (pd.DataFrame): DataFrame con precios de cierre ('Close').
        fast_ma (int): Periodo para la media móvil rápida.
        slow_ma (int): Periodo para la media móvil lenta.
    """
    if 'Close' not in data.columns:
        raise ValueError("El DataFrame de entrada debe contener una columna 'Close'.")

    # 1. Dividir los datos usando DataSplitter
    print("1. Dividiendo los datos en conjuntos de entrenamiento, prueba y validación...")
    splitter = DataSplitter(data, train_ratio=0.7, test_ratio=0.15, validation_ratio=0.15)
    train_data, test_data, validation_data = splitter.split()
    print(f"  - Train: {len(train_data)} filas")
    print(f"  - Test: {len(test_data)} filas")
    print(f"  - Validation: {len(validation_data)} filas\n")

    # 2. Ejecutar backtest en cada conjunto de datos
    for split_name, split_data in [("Train", train_data), ("Test", test_data), ("Validation", validation_data)]:
        if split_data.empty:
            print(f"Saltando el conjunto '{split_name}' porque está vacío.")
            continue

        print(f"--- 2. Ejecutando Backtest en el conjunto: {split_name} ---")
        
        # Calcular medias móviles
        fast_ma_series = vbt.MA.run(split_data['Close'], window=fast_ma, short_name='fast')
        slow_ma_series = vbt.MA.run(split_data['Close'], window=slow_ma, short_name='slow')

        # Generar señales de cruce
        entries = fast_ma_series.ma_crossed_above(slow_ma_series)
        exits = fast_ma_series.ma_crossed_below(slow_ma_series)

        # Construir y ejecutar el portafolio
        portfolio = vbt.Portfolio.from_signals(
            split_data['Close'],
            entries=entries,
            exits=exits,
            init_cash=100000,
            freq='D' # Asumimos frecuencia diaria para el ejemplo
        )

        # 3. Calcular y mostrar métricas de rendimiento
        stats = portfolio.stats()
        print(f"Resultados para el conjunto '{split_name}':")
        print(f"  - Retorno Acumulado (Total Return): {stats['Total Return [%]']:.2f}%")
        print(f"  - Drawdown Máximo (Max Drawdown): {stats['Max Drawdown [%]']:.2f}%")
        print(f"  - Ratio de Sharpe (Sharpe Ratio): {stats['Sharpe Ratio']:.2f}")
        print("-" * (len(split_name) + 34) + "\n")

def create_sample_data(periods: int = 2000) -> pd.DataFrame:
    """Crea un DataFrame de serie temporal de ejemplo para las pruebas."""
    dates = pd.date_range(start='2020-01-01', periods=periods, freq='D')
    price = 100 + np.random.randn(periods).cumsum()
    return pd.DataFrame({'Close': price}, index=dates)

if __name__ == '__main__':
    print("--- Iniciando el Motor de Backtesting Vectorial (VectorBT) ---")
    sample_data = create_sample_data()
    run_vectorized_backtest(sample_data, fast_ma=20, slow_ma=50)
    print("--- Finalizado el proceso de backtesting. ---")