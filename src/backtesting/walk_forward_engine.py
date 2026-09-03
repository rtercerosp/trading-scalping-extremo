import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models.rf_classifier import train_rf_model, evaluate_model
from src.features.feature_pipeline import FeaturePipeline
from utils.utils import Utils


def run_walk_forward_optimization(
    data: pd.DataFrame,
    feature_pipeline: FeaturePipeline,
    train_window: int = 120,  # Number of periods for training window
    step_size: int = 20,      # Number of periods to step forward
    min_train_samples: int = 200,
    pt_limit: float = 1.5,
    sl_limit: float = 1.0,
    time_limit: int = 15,
    target_col: str = 'Target'
) -> pd.DataFrame:
    """
    Ejecuta Walk-Forward Analysis (WFA) sobre datos temporales.

    Args:
        data: DataFrame con datos OHLCV y índice datetime
        feature_pipeline: Instancia de FeaturePipeline configurada
        train_window: Ventana de entrenamiento (número de periodos)
        step_size: Tamaño del paso hacia adelante (periodos de test)
        min_train_samples: Mínimo de muestras para entrenar
        pt_limit/sl_limit/time_limit: Parámetros Triple Barrera
        target_col: Nombre de la columna objetivo

    Returns:
        DataFrame con predicciones out-of-sample consolidadas
    """
    print(f"\n{'='*70}")
    print(f"WALK-FORWARD ANALYSIS")
    print(f"{'='*70}")
    print(f"Train window: {train_window} periodos | Step size: {step_size} periodos")
    print(f"Total data: {len(data)} filas ({data.index[0]} a {data.index[-1]})")

    # 1. Preparar features y labels completos una sola vez
    print(f"[{Utils.dateprint()}] Preparando features técnicos...")
    df_features = feature_pipeline.compute_technical_features(data)

    print(f"[{Utils.dateprint()}] Aplicando Triple Barrera...")
    df_labeled = feature_pipeline.apply_triple_barrier_labels(
        df_features, pt_limit, sl_limit, time_limit
    )

    X, y = feature_pipeline.prepare_ml_dataset(df_labeled, target_col=target_col)

    print(f"[{Utils.dateprint()}] Dataset completo: X={X.shape}, y={y.shape}")
    print(f"[{Utils.dateprint()}] Distribución target: {y.value_counts().sort_index().to_dict()}")

    # 2. Walk-Forward Loop
    n_samples = len(X)
    all_predictions = []
    all_actuals = []
    all_timestamps = []
    iteration = 0
    successful_iterations = 0

    # Start from first possible train window
    start_idx = train_window

    while start_idx + step_size <= n_samples:
        iteration += 1
        train_end = start_idx
        test_end = min(start_idx + step_size, n_samples)

        # Train indices: [train_end - train_window, train_end)
        train_start = max(0, train_end - train_window)

        X_train = X.iloc[train_start:train_end]
        y_train = y.iloc[train_start:train_end]
        X_test = X.iloc[train_end:test_end]
        y_test = y.iloc[train_end:test_end]

        # Validar tamaño mínimo
        if len(X_train) < min_train_samples:
            print(f"[{Utils.dateprint()}] Iter {iteration}: Train insuficiente ({len(X_train)} < {min_train_samples}), saltando...")
            start_idx += step_size
            continue

        # Verificar que hay datos de test
        if len(X_test) == 0:
            break

        print(f"\n[{Utils.dateprint()}] === ITERACIÓN {iteration} ===")
        print(f"  Train: [{train_start}:{train_end}] ({len(X_train)} muestras)")
        print(f"  Test:  [{train_end}:{test_end}] ({len(X_test)} muestras)")
        print(f"  Periodo test: {X_test.index[0]} a {X_test.index[-1]}")

        try:
            # Entrenar modelo
            model, scaler = train_rf_model(
                X_train, y_train,
                n_estimators=200,
                max_depth=8
            )

            # Predecir out-of-sample
            X_test_scaled = scaler.transform(X_test)
            y_pred = model.predict(X_test_scaled)

            # Almacenar predicciones
            all_predictions.extend(y_pred)
            all_actuals.extend(y_test.values)
            all_timestamps.extend(X_test.index)

            # Métricas de esta iteración
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
            acc = accuracy_score(y_test, y_pred)
            print(f"  Test Accuracy: {acc:.4f}")

            successful_iterations += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            # Fill with NaN for failed iteration
            all_predictions.extend([np.nan] * len(X_test))
            all_actuals.extend(y_test.values)
            all_timestamps.extend(X_test.index)

        # Avanzar ventana
        start_idx += step_size

    # 3. Consolidar resultados
    if successful_iterations == 0:
        print(f"\n[{Utils.dateprint()}] ERROR: Ninguna iteración exitosa")
        return pd.DataFrame()

    results_df = pd.DataFrame({
        'timestamp': all_timestamps,
        'actual': all_actuals,
        'predicted': all_predictions
    }, index=all_timestamps)

    # Eliminar filas donde la predicción falló
    results_df = results_df.dropna(subset=['predicted'])
    results_df['predicted'] = results_df['predicted'].astype(int)

    # 4. Métricas consolidadas
    print(f"\n{'='*70}")
    print(f"RESULTADOS CONSOLIDADOS WALK-FORWARD")
    print(f"{'='*70}")
    print(f"Iteraciones exitosas: {successful_iterations}/{iteration}")

    if len(results_df) > 0:
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report

        overall_acc = accuracy_score(results_df['actual'], results_df['predicted'])
        print(f"Overall Out-of-Sample Accuracy: {overall_acc:.4f}")

        # Por clase
        for cls in sorted(results_df['actual'].unique()):
            mask = results_df['actual'] == cls
            if mask.sum() > 0:
                cls_acc = accuracy_score(results_df.loc[mask, 'actual'], results_df.loc[mask, 'predicted'])
                print(f"  Class {cls} (n={mask.sum()}): Accuracy={cls_acc:.4f}")

        # Classification report completo
        print(f"\n--- Classification Report (Out-of-Sample) ---")
        print(classification_report(results_df['actual'], results_df['predicted']))

        # Performance por periodo (ventana móvil de accuracy)
        results_df['correct'] = (results_df['actual'] == results_df['predicted']).astype(int)
        window_acc = results_df['correct'].rolling(window=min(100, len(results_df)//10)).mean()
        print(f"\nRolling Accuracy (ultimos 100): {window_acc.iloc[-1]:.4f}" if len(window_acc) > 0 else "N/A")

    print(f"{'='*70}")

    return results_df


def run_anchored_walk_forward(
    data: pd.DataFrame,
    feature_pipeline: FeaturePipeline,
    initial_train_size: int = 500,
    step_size: int = 50,
    **kwargs
) -> pd.DataFrame:
    """
    Walk-Forward Anclado (Expanding Window): La ventana de entrenamiento crece,
    siempre empezando desde el primer dato.
    """
    print(f"\n{'='*70}")
    print(f"ANCHORED WALK-FORWARD (EXPANDING WINDOW)")
    print(f"{'='*70}")

    df_features = feature_pipeline.compute_technical_features(data)
    df_labeled = feature_pipeline.apply_triple_barrier_labels(df_features, **kwargs)
    X, y = feature_pipeline.prepare_ml_dataset(df_labeled)

    n = len(X)
    all_predictions = []
    all_actuals = []
    all_timestamps = []
    iteration = 0

    train_end = initial_train_size

    while train_end + step_size <= n:
        iteration += 1
        test_end = min(train_end + step_size, n)

        X_train = X.iloc[:train_end]  # Anchored: siempre desde 0
        y_train = y.iloc[:train_end]
        X_test = X.iloc[train_end:test_end]
        y_test = y.iloc[train_end:test_end]

        print(f"[{Utils.dateprint()}] Iter {iteration}: Train [0:{train_end}]={len(X_train)}, Test [{train_end}:{test_end}]={len(X_test)}")

        try:
            model, scaler = train_rf_model(X_train, y_train, n_estimators=200, max_depth=8)
            X_test_scaled = scaler.transform(X_test)
            y_pred = model.predict(X_test_scaled)

            all_predictions.extend(y_pred)
            all_actuals.extend(y_test.values)
            all_timestamps.extend(X_test.index)

            from sklearn.metrics import accuracy_score
            acc = accuracy_score(y_test, y_pred)
            print(f"  Test Acc: {acc:.4f}")

        except Exception as e:
            print(f"  ERROR: {e}")
            all_predictions.extend([np.nan] * len(X_test))
            all_actuals.extend(y_test.values)
            all_timestamps.extend(X_test.index)

        train_end += step_size

    results_df = pd.DataFrame({
        'timestamp': all_timestamps,
        'actual': all_actuals,
        'predicted': all_predictions
    }, index=all_timestamps).dropna(subset=['predicted'])

    if len(results_df) > 0:
        results_df['predicted'] = results_df['predicted'].astype(int)
        from sklearn.metrics import accuracy_score
        print(f"\nOverall Accuracy (Anchored): {accuracy_score(results_df['actual'], results_df['predicted']):.4f}")

    return results_df


if __name__ == '__main__':
    print("=" * 70)
    print("TASK-033: WALK-FORWARD ANALYSIS ENGINE")
    print("=" * 70)

    # Generar datos sintéticos con régimen cambiante
    from src.features.validate_labels import generate_synthetic_price_data

    np.random.seed(42)
    n_total = 3000
    data = generate_synthetic_price_data(n_samples=n_total)

    # Crear pipeline (sin connector MT5, usa sintético)
    pipeline = FeaturePipeline()

    print(f"\n[Config] Datos sintéticos: {n_total} barras")
    print(f"[Config] Train window: 200 | Step: 50")

    # Ejecutar WFA estándar (sliding window)
    print("\n>>> EJECUTANDO SLIDING WINDOW WFA...")
    wfa_results = run_walk_forward_optimization(
        data=data,
        feature_pipeline=pipeline,
        train_window=200,
        step_size=50,
        pt_limit=1.5,
        sl_limit=1.0,
        time_limit=15
    )

    # Ejecutar WFA anclado (expanding window)
    print("\n>>> EJECUTANDO ANCHORED WFA...")
    anchored_results = run_anchored_walk_forward(
        data=data,
        feature_pipeline=pipeline,
        initial_train_size=500,
        step_size=50,
        pt_limit=1.5,
        sl_limit=1.0,
        time_limit=15
    )

    print(f"\n[OK] TASK-033 Simulation Complete: Walk-Forward Analysis")
    print(f"  Sliding WFA: {len(wfa_results)} predicciones OOS")
    print(f"  Anchored WFA: {len(anchored_results)} predicciones OOS")