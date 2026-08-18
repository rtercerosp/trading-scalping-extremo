import pandas as pd
import numpy as np

def calculate_portfolio_drawdown(portfolio_returns: pd.Series) -> pd.Series:
    """
    Calcula el drawdown de una cartera a partir de una serie de retornos.

    El drawdown es la medida de la caída desde un pico hasta un valle en el valor
    de una cartera. Se calcula como el porcentaje de caída desde el máximo histórico
    (running max).

    Args:
        portfolio_returns (pd.Series): Una serie de pandas que contiene los retornos
                                       diarios o periódicos de la cartera (ej. 0.01 para 1%).

    Returns:
        pd.Series: Una serie de pandas que contiene el valor del drawdown en cada punto
                   en el tiempo. Los valores son negativos o cero.
    """
    # 1. Calcular el rendimiento acumulado (cumulative wealth index)
    # Se asume un capital inicial de 1. El producto acumulado de (1 + retornos)
    # nos da el crecimiento del capital.
    cumulative_returns = (1 + portfolio_returns).cumprod()

    # 2. Calcular el máximo histórico en ejecución (running maximum)
    # Esto nos da el valor pico más alto alcanzado hasta la fecha en cada punto.
    running_max = cumulative_returns.cummax()

    # 3. Calcular el drawdown
    # La fórmula es (valor_actual / pico_anterior) - 1.
    # Esto da como resultado un número negativo que representa el porcentaje de caída.
    drawdown = (cumulative_returns / running_max) - 1

    return drawdown

if __name__ == '__main__':
    # --- Bloque de Simulación ---
    print("--- Simulación del Motor de Cálculo de Drawdown ---")

    # 1. Generar una serie de retornos sintéticos
    # Creamos una serie de tiempo con algunos altibajos para probar el cálculo.
    np.random.seed(42) # Para reproducibilidad
    periods = 252 # Aproximadamente un año de trading
    returns_data = np.random.randn(periods) / 100 # Retornos diarios con volatilidad
    # Introducir algunas caídas y recuperaciones más pronunciadas
    returns_data[50:60] = -0.02
    returns_data[150:165] = -0.025
    returns_data[200:220] = 0.015

    portfolio_returns_series = pd.Series(
        returns_data,
        index=pd.date_range(start='2023-01-01', periods=periods, freq='D'),
        name="Portfolio Returns"
    )

    print(f"\nSe generaron {len(portfolio_returns_series)} retornos sintéticos.")

    # 2. Ejecutar la función de cálculo de drawdown
    drawdown_series = calculate_portfolio_drawdown(portfolio_returns_series)

    # 3. Mostrar el drawdown máximo y otros resultados
    max_drawdown = drawdown_series.min()
    max_drawdown_date = drawdown_series.idxmin()

    print("\n--- Resultados del Análisis ---")
    print(f"Drawdown Máximo: {max_drawdown:.2%}")
    print(f"Fecha del Drawdown Máximo: {max_drawdown_date.strftime('%Y-%m-%d')}")

    print("\n--- Simulación Finalizada ---")