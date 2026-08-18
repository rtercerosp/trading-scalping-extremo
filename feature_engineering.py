import pandas as pd
import numpy as np

# Importar el módulo de triple barrera (archivo en la raíz del proyecto)
from triple_barrier import apply_triple_barrier

def build_features_and_targets(data: pd.DataFrame) -> pd.DataFrame:
    """
    Pipeline consolidado para ingeniería de características y etiquetado.

    Esta función toma datos brutos de precios, calcula un conjunto de
    características (predictores) y genera la variable objetivo ('Target')
    utilizando el método de la triple barrera.

    Args:
        data (pd.DataFrame): DataFrame que debe contener al menos una columna 'Close'.

    Returns:
        pd.DataFrame: Un DataFrame que contiene las características y el objetivo,
                      listo para ser utilizado en un modelo de machine learning.
                      Los valores NaN generados por los cálculos son eliminados.
    """
    df = data.copy()

    # --- 1. Ingeniería de Características (Predictores) ---
    df['log_return'] = np.log(df['Close']).diff()
    df['ma_fast'] = df['Close'].rolling(window=10).mean()
    df['ma_slow'] = df['Close'].rolling(window=20).mean()
    df['ma_ratio'] = df['ma_fast'] / df['ma_slow']
    df['momentum'] = df['Close'].pct_change(periods=5)

    # --- 2. Etiquetado de la Variable Objetivo ---
    df = apply_triple_barrier(df, pt_limit=1.5, sl_limit=1.0, time_limit=15)

    # --- 3. Limpieza Final ---
    feature_columns = [
        'log_return', 'ma_fast', 'ma_slow', 'ma_ratio', 'momentum', 'Target'
    ]
    
    final_columns = [col for col in feature_columns if col in df.columns]
    df_final = df[final_columns]
    
    df_final.dropna(inplace=True)

    df_final['Target'] = df_final['Target'].astype(int)

    return df_final

if __name__ == '__main__':
    # --- Bloque de Simulación para probar el pipeline ---
    print("--- Simulación del Pipeline de Ingeniería de Características ---")

    # Generar datos de precios de ejemplo
    periods = 500
    price = 100 + np.random.randn(periods).cumsum()
    sample_data = pd.DataFrame({
        'Close': price
    }, index=pd.date_range(start='2023-01-01', periods=periods, freq='D'))

    print(f"Datos de entrada: {sample_data.shape[0]} filas.")

    # Ejecutar el pipeline
    featured_data = build_features_and_targets(sample_data)

    print("\n--- Resultados del Pipeline ---")
    print(f"Datos procesados: {featured_data.shape[0]} filas.")
    print("Columnas generadas:", featured_data.columns.tolist())
    
    print("\nDistribución del Objetivo ('Target'):")
    print(featured_data['Target'].value_counts(normalize=True).to_string())
    
    print("\nPrimeras 5 filas del DataFrame final:")
    print(featured_data.head())

    print("\n--- Simulación Finalizada ---")