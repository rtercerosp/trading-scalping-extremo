import pandas as pd
import numpy as np

def calculate_volatility(close_prices: pd.Series, span: int = 100) -> pd.Series:
    """
    Calcula la volatilidad diaria dinámica de los precios de cierre.

    Utiliza una media móvil exponencial (EWM) de la desviación estándar de los
    retornos porcentuales diarios para estimar la volatilidad.

    Args:
        close_prices (pd.Series): Serie de precios de cierre.
        span (int): El lapso para la media móvil exponencial.

    Returns:
        pd.Series: Serie de pandas con la volatilidad calculada para cada punto.
    """
    # Calcula los retornos diarios, excluyendo el primer NaN
    returns = close_prices.pct_change()
    
    # Calcula la volatilidad usando EWM. El min_periods asegura que tengamos suficientes datos.
    volatility = returns.ewm(span=span, min_periods=span).std()
    
    return volatility

def apply_triple_barrier(
    data: pd.DataFrame, 
    pt_limit: float = 1.0, 
    sl_limit: float = 1.0, 
    time_limit: int = 10
) -> pd.DataFrame:
    """
    Aplica el método de la triple barrera para etiquetar datos de series temporales.

    Genera una columna 'Target' con valores:
    -  1: Si el precio toca la barrera superior (profit-take).
    - -1: Si el precio toca la barrera inferior (stop-loss).
    -  0: Si el precio toca la barrera de tiempo (vertical).

    Las barreras superior e inferior son dinámicas y se basan en la volatilidad.

    Args:
        data (pd.DataFrame): DataFrame que debe contener la columna 'Close'.
        pt_limit (float): Multiplicador de volatilidad para la barrera de profit-take.
        sl_limit (float): Multiplicador de volatilidad para la barrera de stop-loss.
        time_limit (int): Número de periodos hacia adelante para la barrera de tiempo.

    Returns:
        pd.DataFrame: El DataFrame original con la columna 'Target' añadida.
    """
    df = data.copy()
    
    # 1. Calcular la volatilidad
    volatility = calculate_volatility(df['Close'])
    df['volatility'] = volatility

    targets = pd.Series(np.nan, index=df.index)
    close_prices_np = df['Close'].to_numpy()
    volatility_np = df['volatility'].to_numpy()
    num_rows = len(df)

    # 2. Iterar sobre cada punto para evaluar las trayectorias futuras
    for i in range(num_rows - time_limit):
        current_vol = volatility_np[i]
        if np.isnan(current_vol):
            continue

        upper_barrier = close_prices_np[i] * (1 + current_vol * pt_limit)
        lower_barrier = close_prices_np[i] * (1 - current_vol * sl_limit)
        
        for j in range(1, time_limit + 1):
            future_price = close_prices_np[i + j]
            if future_price >= upper_barrier:
                targets.iloc[i] = 1; break
            if future_price <= lower_barrier:
                targets.iloc[i] = -1; break
        
        if pd.isna(targets.iloc[i]):
            targets.iloc[i] = 0

    df['Target'] = targets
    return df