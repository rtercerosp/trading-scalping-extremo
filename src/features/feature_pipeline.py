import pandas as pd
import numpy as np
import duckdb
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from platform_connector.platform_connector import PlatformConnector
from src.features.triple_barrier import apply_triple_barrier, calculate_volatility
from src.models.rf_classifier import train_rf_model, evaluate_model
from utils.utils import Utils
import config


class FeaturePipeline:
    """
    Pipeline completo: Datos MT5/DuckDB -> Features Técnicos -> Triple Barrera -> Train/Test/Val
    """

    def __init__(
        self,
        connector: Optional[PlatformConnector] = None,
        duckdb_path: Optional[str] = None,
        parquet_glob: Optional[str] = None
    ):
        self.connector = connector
        self.duckdb_path = duckdb_path
        self.parquet_glob = parquet_glob
        self.ducklake_con = None

        if duckdb_path and parquet_glob:
            self._init_ducklake()

    def _init_ducklake(self):
        """Inicializa conexión a catálogo DuckLake."""
        import duckdb
        print(f"[{Utils.dateprint()}] Inicializando catálogo DuckLake: {self.duckdb_path}")
        self.ducklake_con = duckdb.connect(database=self.duckdb_path, read_only=False)
        self.ducklake_con.execute("CREATE SCHEMA IF NOT EXISTS market;")
        view_sql = f"""
        CREATE OR REPLACE VIEW market.ohlcv AS
        SELECT * FROM read_parquet('{self.parquet_glob}', union_by_name=True);
        """
        self.ducklake_con.execute(view_sql)
        print(f"[{Utils.dateprint()}] Vista market.ohlcv creada")

    def fetch_data_from_mt5(
        self,
        symbol: str,
        timeframe: str = "5min",
        num_bars: int = 5000
    ) -> pd.DataFrame:
        """Extrae datos históricos reales desde MetaTrader 5."""
        if self.connector is None:
            raise ValueError("Connector MT5 no proporcionado")

        print(f"[{Utils.dateprint()}] Descargando {num_bars} barras de {symbol} ({timeframe}) desde MT5...")
        bars = self.connector.get_latest_closed_bars(symbol, timeframe, num_bars)

        if bars.empty:
            raise ValueError(f"No se obtuvieron datos para {symbol}")

        # Renombrar columnas a estándar
        bars = bars.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'tickvol': 'Volume',
            'vol': 'RealVolume'
        })

        print(f"[{Utils.dateprint()}] Datos obtenidos: {len(bars)} filas, rango: {bars.index[0]} - {bars.index[-1]}")
        return bars

    def fetch_data_from_ducklake(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """Extrae datos desde catálogo DuckLake/Parquet."""
        if self.ducklake_con is None:
            raise ValueError("DuckLake no inicializado. Proporcione duckdb_path y parquet_glob.")

        query = "SELECT * FROM market.ohlcv"
        conditions = []

        if 'symbol' in self.ducklake_con.execute("DESCRIBE market.ohlcv").fetchdf()['column_name'].values:
            conditions.append(f"symbol = '{symbol}'")
        elif 'Symbol' in self.ducklake_con.execute("DESCRIBE market.ohlcv").fetchdf()['column_name'].values:
            conditions.append(f"Symbol = '{symbol}'")

        if start_date:
            conditions.append(f"index >= '{start_date}'")
        if end_date:
            conditions.append(f"index <= '{end_date}'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY index"

        print(f"[{Utils.dateprint()}] Consultando DuckLake para {symbol}...")
        df = self.ducklake_con.execute(query).fetchdf()

        if df.empty:
            raise ValueError(f"No hay datos en DuckLake para {symbol}")

        # Asegurar índice datetime
        if 'index' in df.columns:
            df['index'] = pd.to_datetime(df['index'])
            df.set_index('index', inplace=True)

        # Estandarizar nombres de columnas
        col_map = {
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
            'volume': 'Volume', 'tick_volume': 'Volume', 'spread': 'Spread'
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        print(f"[{Utils.dateprint()}] Datos DuckLake: {len(df)} filas")
        return df

    def compute_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula características técnicas estándar."""
        df = df.copy()

        # Retornos
        df['returns'] = df['Close'].pct_change()
        df['log_returns'] = np.log(df['Close'] / df['Close'].shift(1))

        # Volatilidad (EWM std de retornos)
        df['volatility'] = df['returns'].ewm(span=100, min_periods=20).std()

        # EMAs
        df['ema_9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['Close'].ewm(span=200, adjust=False).mean()

        # EMA ratios
        df['ema_ratio_9_21'] = df['ema_9'] / df['ema_21']
        df['ema_ratio_50_200'] = df['ema_50'] / df['ema_200']

        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        df['macd'] = df['ema_9'] - df['ema_21']
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # ATR
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.ewm(span=14, adjust=False).mean()
        df['atr_pct'] = df['atr'] / df['Close']

        # Bollinger Bands
        df['bb_mid'] = df['Close'].rolling(20).mean()
        df['bb_std'] = df['Close'].rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
        df['bb_pos'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # Volume features
        df['volume_sma'] = df['Volume'].rolling(20).mean()
        df['volume_ratio'] = df['Volume'] / df['volume_sma']

        # Price position
        df['hl_range'] = df['High'] - df['Low']
        df['close_position'] = (df['Close'] - df['Low']) / df['hl_range'].replace(0, np.nan)

        return df.dropna()

    def apply_triple_barrier_labels(
        self,
        df: pd.DataFrame,
        pt_limit: float = 1.5,
        sl_limit: float = 1.0,
        time_limit: int = 15
    ) -> pd.DataFrame:
        """Aplica etiquetado Triple Barrera usando volatilidad dinámica."""
        # Usar la función existente
        labeled = apply_triple_barrier(df.copy(), pt_limit, sl_limit, time_limit)
        return labeled

    def prepare_ml_dataset(
        self,
        df: pd.DataFrame,
        feature_cols: Optional[List[str]] = None,
        target_col: str = 'Target'
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepara dataset para ML: selecciona features, maneja NaN, retorna X, y."""
        if feature_cols is None:
            feature_cols = [
                'returns', 'volatility', 'ema_ratio_9_21', 'ema_ratio_50_200',
                'rsi', 'macd', 'macd_hist', 'atr_pct',
                'bb_width', 'bb_pos', 'volume_ratio', 'close_position'
            ]

        # Filtrar columnas disponibles
        available_cols = [c for c in feature_cols if c in df.columns]
        missing = set(feature_cols) - set(available_cols)
        if missing:
            print(f"[{Utils.dateprint()}] WARNING: Features faltantes: {missing}")

        X = df[available_cols].copy()
        y = df[target_col].copy()

        # Alinear y eliminar NaN
        valid_idx = X.dropna().index.intersection(y.dropna().index)
        X = X.loc[valid_idx]
        y = y.loc[valid_idx].astype(int)

        print(f"[{Utils.dateprint()}] Dataset ML: X={X.shape}, y={y.shape}")
        print(f"[{Utils.dateprint()}] Distribución target: {y.value_counts().sort_index().to_dict()}")

        return X, y

    def chronological_split(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        train_pct: float = 0.70,
        test_pct: float = 0.15
    ) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
        """Split cronológico estricto: Train/Test/Validation sin data leakage."""
        n = len(X)
        train_end = int(n * train_pct)
        test_end = int(n * (train_pct + test_pct))

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]
        X_test = X.iloc[train_end:test_end]
        y_test = y.iloc[train_end:test_end]
        X_val = X.iloc[test_end:]
        y_val = y.iloc[test_end:]

        print(f"[{Utils.dateprint()}] Split Cronológico:")
        print(f"  Train: {len(X_train)} ({len(X_train)/n:.1%})")
        print(f"  Test:  {len(X_test)} ({len(X_test)/n:.1%})")
        print(f"  Val:   {len(X_val)} ({len(X_val)/n:.1%})")

        return X_train, y_train, X_test, y_test, X_val, y_val

    def run_full_pipeline(
        self,
        symbol: str,
        timeframe: str = "5min",
        num_bars: int = 5000,
        pt_limit: float = 1.5,
        sl_limit: float = 1.0,
        time_limit: int = 15,
        use_mt5: bool = True
    ) -> Dict:
        """Ejecuta pipeline completo para un símbolo y retorna resultados."""
        print(f"\n{'='*60}")
        print(f"PIPELINE COMPLETO: {symbol} ({timeframe})")
        print(f"{'='*60}")

        # 1. Extraer datos
        if use_mt5 and self.connector:
            df = self.fetch_data_from_mt5(symbol, timeframe, num_bars)
        elif self.ducklake_con:
            df = self.fetch_data_from_ducklake(symbol)
        else:
            raise ValueError("No hay fuente de datos configurada (MT5 o DuckLake)")

        # 2. Features técnicos
        print(f"[{Utils.dateprint()}] Calculando features técnicos...")
        df = self.compute_technical_features(df)

        # 3. Triple Barrera
        print(f"[{Utils.dateprint()}] Aplicando Triple Barrera (pt={pt_limit}, sl={sl_limit}, time={time_limit})...")
        df = self.apply_triple_barrier_labels(df, pt_limit, sl_limit, time_limit)

        # 4. Preparar dataset ML
        X, y = self.prepare_ml_dataset(df)

        # 5. Split cronológico
        X_train, y_train, X_test, y_test, X_val, y_val = self.chronological_split(X, y)

        # 6. Entrenar modelo
        print(f"[{Utils.dateprint()}] Entrenando Random Forest...")
        model, scaler = train_rf_model(X_train, y_train, n_estimators=200, max_depth=8)

        # 7. Evaluar
        test_report = evaluate_model(model, scaler, X_test, y_test)
        val_report = evaluate_model(model, scaler, X_val, y_val)

        print(f"\n{'='*60}")
        print("RESULTADOS FINALES")
        print(f"{'='*60}")

        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'data_shape': df.shape,
            'X_shape': X.shape,
            'y_distribution': y.value_counts().sort_index().to_dict(),
            'train_shape': X_train.shape,
            'test_shape': X_test.shape,
            'val_shape': X_val.shape,
            'test_report': test_report,
            'val_report': val_report,
            'model': model,
            'scaler': scaler,
            'feature_names': X.columns.tolist()
        }

    def run_portfolio_pipeline(
        self,
        symbols: Optional[List[str]] = None,
        timeframe: str = "5min",
        num_bars: int = 5000,
        pt_limit: float = 1.5,
        sl_limit: float = 1.0,
        time_limit: int = 15,
        use_mt5: bool = True,
        save_results: bool = True
    ) -> Dict[str, Dict]:
        """
        Ejecuta pipeline para todo el portafolio de símbolos configurados.

        Args:
            symbols: Lista de símbolos. Si None, usa config.DEFAULT_SYMBOLS
            timeframe: Timeframe para datos
            num_bars: Número de barras por símbolo
            pt_limit/sl_limit/time_limit: Parámetros Triple Barrera
            use_mt5: Usar MT5 (True) o DuckLake (False)
            save_results: Si True, guarda modelos por símbolo

        Returns:
            Diccionario con resultados por símbolo
        """
        if symbols is None:
            symbols = config.DEFAULT_SYMBOLS
            print(f"[{Utils.dateprint()}] Usando símbolos por defecto de config.py: {symbols}")

        print(f"\n{'='*60}")
        print(f"PORTFOLIO PIPELINE: {len(symbols)} símbolos")
        print(f"{'='*60}")

        all_results = {}
        failed_symbols = []

        for i, symbol in enumerate(symbols, 1):
            print(f"\n[{Utils.dateprint()}] Procesando {i}/{len(symbols)}: {symbol}")
            try:
                result = self.run_full_pipeline(
                    symbol=symbol,
                    timeframe=timeframe,
                    num_bars=num_bars,
                    pt_limit=pt_limit,
                    sl_limit=sl_limit,
                    time_limit=time_limit,
                    use_mt5=use_mt5
                )
                all_results[symbol] = result
                print(f"[{Utils.dateprint()}] [OK] {symbol} completado: {result['X_shape'][0]} muestras, target={result['y_distribution']}")

            except Exception as e:
                print(f"[{Utils.dateprint()}] [FAIL] {symbol} FALLÓ: {e}")
                failed_symbols.append((symbol, str(e)))
                all_results[symbol] = {'error': str(e), 'symbol': symbol}

        # Resumen final
        print(f"\n{'='*60}")
        print("RESUMEN PORTAFOLIO")
        print(f"{'='*60}")
        print(f"Total símbolos: {len(symbols)}")
        print(f"Exitosos: {len(all_results) - len(failed_symbols)}")
        print(f"Fallidos: {len(failed_symbols)}")

        if failed_symbols:
            print("Símbolos fallidos:")
            for sym, err in failed_symbols:
                print(f"  - {sym}: {err}")

        # Estadísticas agregadas
        total_samples = sum(r.get('X_shape', (0,))[0] for r in all_results.values() if 'X_shape' in r)
        print(f"Total muestras procesadas: {total_samples}")

        if save_results:
            self._save_portfolio_results(all_results)

        return all_results

    def _save_portfolio_results(self, results: Dict[str, Dict]):
        """Guarda modelos y scalers por símbolo."""
        import joblib
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = Path(f"./models/portfolio_{timestamp}")
        save_dir.mkdir(parents=True, exist_ok=True)

        for symbol, result in results.items():
            if 'model' in result and 'scaler' in result:
                model_path = save_dir / f"{symbol}_model.pkl"
                scaler_path = save_dir / f"{symbol}_scaler.pkl"
                joblib.dump(result['model'], model_path)
                joblib.dump(result['scaler'], scaler_path)
                print(f"[{Utils.dateprint()}] Guardado: {model_path}")

        print(f"[{Utils.dateprint()}] Modelos guardados en: {save_dir}")


def create_connector_from_env(symbols: List[str]) -> PlatformConnector:
    """Crea connector desde variables de entorno (.env)."""
    print(f"[{Utils.dateprint()}] Conectando a MT5...")
    return PlatformConnector(symbol_list=symbols, skip_warning=True)


if __name__ == '__main__':
    print("=" * 60)
    print("TASK-031: FEATURE PIPELINE CON DATOS REALES MT5 - PORTFOLIO")
    print("=" * 60)

    # Configuración
    TIMEFRAME = "5min"
    NUM_BARS = 5000
    SYMBOLS = config.DEFAULT_SYMBOLS  # Usa lista institucional completa

    # Intentar usar MT5 (requiere .env configurado)
    try:
        connector = create_connector_from_env(SYMBOLS)
        pipeline = FeaturePipeline(connector=connector)
        use_mt5 = True
    except Exception as e:
        print(f"[{Utils.dateprint()}] MT5 no disponible: {e}")
        print(f"[{Utils.dateprint()}] Usando DuckLake con datos sintéticos para demo...")
        # Fallback: datos sintéticos guardados en Parquet
        from src.features.validate_labels import generate_synthetic_price_data
        df = generate_synthetic_price_data(n_samples=NUM_BARS)
        df.to_parquet("./temp_ducklake_data/demo_data.parquet")
        pipeline = FeaturePipeline(
            duckdb_path="./temp_ducklake_data/catalog.db",
            parquet_glob="./temp_ducklake_data/*.parquet"
        )
        use_mt5 = False

    # Ejecutar pipeline para TODO EL PORTAFOLIO
    try:
        all_results = pipeline.run_portfolio_pipeline(
            symbols=SYMBOLS,
            timeframe=TIMEFRAME,
            num_bars=NUM_BARS,
            pt_limit=1.5,
            sl_limit=1.0,
            time_limit=15,
            use_mt5=use_mt5,
            save_results=True
        )

        print(f"\n[OK] TASK-031 Portfolio Pipeline ejecutado exitosamente")
        print(f"  Símbolos procesados: {len(all_results)}")
        for sym, res in all_results.items():
            if 'X_shape' in res:
                print(f"    {sym}: {res['X_shape'][0]} muestras, target={res['y_distribution']}")

    except Exception as e:
        print(f"[{Utils.dateprint()}] ERROR en pipeline: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if pipeline.ducklake_con:
            pipeline.ducklake_con.close()