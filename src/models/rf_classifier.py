import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
from typing import Tuple


def train_rf_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    n_estimators: int = 100,
    max_depth: int = 5
) -> Tuple[RandomForestClassifier, StandardScaler]:
    """
    Train a Random Forest classifier with standardized features.

    Args:
        X_train: Feature matrix for training
        y_train: Target labels for training
        n_estimators: Number of trees in the forest
        max_depth: Maximum depth of trees

    Returns:
        Tuple of (trained_model, fitted_scaler)
    """
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train_scaled, y_train)

    return model, scaler


def evaluate_model(
    model: RandomForestClassifier,
    scaler: StandardScaler,
    X_test: pd.DataFrame,
    y_test: pd.Series
) -> str:
    """Evaluate model on test set and return classification report."""
    X_test_scaled = scaler.transform(X_test)
    y_pred = model.predict(X_test_scaled)
    return classification_report(y_test, y_pred)


if __name__ == '__main__':
    np.random.seed(42)
    n_samples = 5000

    # Simulate financial features: returns, volatility, volume, technical indicators
    returns = np.random.randn(n_samples) * 0.01
    volatility = np.abs(np.random.randn(n_samples)) * 0.02 + 0.005
    volume = np.random.lognormal(10, 0.5, n_samples)
    rsi = np.random.uniform(20, 80, n_samples)
    macd = np.random.randn(n_samples) * 0.5
    ema_ratio = np.random.uniform(0.98, 1.02, n_samples)

    # Create target: 0=DOWN, 1=FLAT, 2=UP (ternary classification)
    # Based on forward returns with noise
    forward_returns = np.roll(returns, -1)  # Next period return
    forward_returns[-1] = 0

    # Thresholds for ternary classification
    up_threshold = 0.002
    down_threshold = -0.002

    y = np.where(forward_returns > up_threshold, 2,
           np.where(forward_returns < down_threshold, 0, 1))

    # Remove last sample (no forward return)
    X = pd.DataFrame({
        'returns': returns[:-1],
        'volatility': volatility[:-1],
        'volume': volume[:-1],
        'rsi': rsi[:-1],
        'macd': macd[:-1],
        'ema_ratio': ema_ratio[:-1]
    })
    y = pd.Series(y[:-1], name='target')

    # CHRONOLOGICAL SPLIT: 70% train, 15% test, 15% validation
    n = len(X)
    train_end = int(n * 0.70)
    test_end = int(n * 0.85)

    X_train = X.iloc[:train_end]
    y_train = y.iloc[:train_end]
    X_test = X.iloc[train_end:test_end]
    y_test = y.iloc[train_end:test_end]
    X_val = X.iloc[test_end:]
    y_val = y.iloc[test_end:]

    print(f"Data Split (Chronological):")
    print(f"  Train: {len(X_train)} samples ({len(X_train)/n:.0%})")
    print(f"  Test:  {len(X_test)} samples ({len(X_test)/n:.0%})")
    print(f"  Val:   {len(X_val)} samples ({len(X_val)/n:.0%})")
    print(f"  Target distribution (train): {y_train.value_counts().sort_index().to_dict()}")

    # Train model
    print("\nTraining Random Forest...")
    model, scaler = train_rf_model(X_train, y_train, n_estimators=200, max_depth=8)

    # Evaluate on test set
    print("\n--- TEST SET EVALUATION ---")
    report = evaluate_model(model, scaler, X_test, y_test)
    print(report)

    # Evaluate on validation set
    print("\n--- VALIDATION SET EVALUATION ---")
    val_report = evaluate_model(model, scaler, X_val, y_val)
    print(val_report)

    # Feature importance
    print("\n--- FEATURE IMPORTANCE ---")
    feature_importance = pd.DataFrame({
        'feature': X.columns,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    print(feature_importance.to_string(index=False))

    print("\n[OK] TASK-029 Simulation Complete: Random Forest with Chronological Split")