import os
from queue import Queue
import logging
from dotenv import load_dotenv, find_dotenv

import config
from utils.utils import Utils
from data_provider.data_provider import DataProvider
from notifications.notifications import NotificationService, TelegramNotificationProperties
from order_executor.break_even_manager import BreakEvenManager
from order_executor.order_executor import OrderExecutor
from platform_connector.platform_connector import PlatformConnector
from portfolio.portfolio import Portfolio
from position_sizer.position_sizer import PositionSizer
from position_sizer.properties.position_sizer_properties import RiskPctSizingProps
from risk_manager.properties.risk_manager_properties import MaxLeverageFactorRiskProps
from risk_manager.risk_manager import RiskManager
from signal_generator.properties.signal_generator_properties import SmartMoneySignalProps
from signal_generator.signal_generator import SignalGenerator
from trading_director.trading_director import TradingDirector
from brain.trading_brain import TradingBrain
from news.news_protection import NewsProtection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    env_file_path: str | None = find_dotenv()
    if env_file_path:
        logging.info(f"Cargando configuración desde: {env_file_path}")
        load_dotenv(env_file_path)
    else:
        logging.warning("No se encontró ningún archivo .env. Se usarán variables de entorno del sistema si existen.")
        load_dotenv()

    symbols_str: str | None = os.getenv("TRADING_SYMBOLS")
    if not symbols_str:
        logging.warning(f"No se han definido los símbolos a operar en .env. Usando la lista por defecto de config.py: {config.DEFAULT_SYMBOLS}")
        symbols: list[str] = config.DEFAULT_SYMBOLS
    else:
        symbols: list[str] = [s.strip() for s in symbols_str.split(',') if s.strip()]

    telegram_token: str | None = os.getenv("TELEGRAM_TOKEN")
    telegram_chat_id: str | None = os.getenv("TELEGRAM_CHAT_ID")

    strategy_props = SmartMoneySignalProps(
        entry_timeframe=config.ENTRY_TIMEFRAME,
        trend_timeframe=config.TREND_TIMEFRAME,
        **config.SMART_MONEY_DEFAULT_PROPS,
        sl_atr_mult=config.LEARNING_DEFAULT_SL_ATR_MULT,
        tp_atr_mult=config.LEARNING_DEFAULT_TP_ATR_MULT,
        min_liquidity_gap_points=0.0,
        use_fibonacci=True,
        use_fvg=True,
        use_macd=True,
    )

    events_queue = Queue()

    import sys
    max_iterations = None
    skip_warning = False
    if "--test-mode" in sys.argv:
        max_iterations = 50
        skip_warning = True
        print("EJECUTANDO EN MODO PRUEBA (50 iteraciones, skip warning)")

    connector: PlatformConnector = PlatformConnector(symbol_list=symbols, skip_warning=skip_warning)

    news_protection: NewsProtection = NewsProtection(
        events_queue=events_queue,
        connector=connector,
    )

    if not telegram_token or not telegram_chat_id:
        logging.warning("TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no están definidos. Las notificaciones de Telegram no funcionarán.")
        notifications: NotificationService = NotificationService(properties=None)
    else:
        notifications: NotificationService = NotificationService(
            properties=TelegramNotificationProperties(
                token=telegram_token,
                chat_id=telegram_chat_id,
            )
        )

    def _request_stop() -> None:
        try:
            connector.close()
        except Exception as e:
            logging.error(f"Error al cerrar conexión MT5: {e}")
        logging.info("Deteniendo aplicación por pérdida de conexión MT5.")
        import sys
        sys.exit(1)

    data_provider: DataProvider = DataProvider(
        events_queue=events_queue,
        symbol_list=symbols,
        timeframe=config.ENTRY_TIMEFRAME,
        connector=connector,
        notification_service=notifications,
        stop_callback=_request_stop,
    )

    portfolio: Portfolio = Portfolio(
        magic_number=config.MAGIC_NUMBER,
        max_total_positions=config.PORTFOLIO_MAX_TOTAL_POSITIONS,
        max_positions_per_symbol=config.PORTFOLIO_MAX_POSITIONS_PER_SYMBOL,
        max_positions_by_symbol=config.PORTFOLIO_MAX_POSITIONS_BY_SYMBOL,
        max_positions_by_category=config.PORTFOLIO_MAX_POSITIONS_BY_CATEGORY,
    )

    # --- FASE 2: INSTANCIACIÓN DEL CEREBRO Y MÓDULOS DE IA ---
    # El TradingBrain es central y otros módulos dependen de él.

    trading_brain: TradingBrain = TradingBrain(
        events_queue=events_queue,
        data_provider=data_provider,
        portfolio=portfolio,
        order_executor=None,  # Se inyectará después para evitar dependencia circular
        connector=connector,
        news_protection=news_protection,
    )

    order_executor: OrderExecutor = OrderExecutor(
        events_queue=events_queue,
        portfolio=portfolio,
        notification_service=notifications,
        connector=connector,
        data_provider=data_provider,
    )

    break_even_manager: BreakEvenManager = BreakEvenManager(
        data_provider=data_provider,
        order_executor=order_executor,
        notification_service=notifications,
        connector=connector,
        trading_brain=trading_brain,
    )

    signal_generator: SignalGenerator = SignalGenerator(
        events_queue=events_queue,
        data_provider=data_provider,
        portfolio=portfolio,
        order_executor=order_executor,
        signal_properties=strategy_props,
        connector=connector,
        trading_brain=trading_brain,
    )

    # Inyección tardía para romper la dependencia circular
    trading_brain.order_executor = order_executor
    trading_brain.break_even_manager = break_even_manager

    def _get_adaptive_risk_pct(symbol: str) -> float | None:
        if trading_brain is None:
            return None
        params = trading_brain.get_adaptive_params(symbol)
        risk = params.get("risk_pct") if isinstance(params, dict) else None
        return float(risk) if risk is not None else None

    position_sizer: PositionSizer = PositionSizer(
        events_queue=events_queue,
        data_provider=data_provider,
        sizing_properties=RiskPctSizingProps(risk_pct=config.SIZER_DEFAULT_RISK_PCT),
        connector=connector,
        get_risk_pct_callback=_get_adaptive_risk_pct,
        portfolio=portfolio,
        max_leverage_factor=config.RISK_MAX_LEVERAGE_FACTOR,
    )

    risk_manager: RiskManager = RiskManager(
        events_queue=events_queue,
        data_provider=data_provider,
        portfolio=portfolio,
        risk_properties=MaxLeverageFactorRiskProps(max_leverage_factor=config.RISK_MAX_LEVERAGE_FACTOR),
        notification_service=notifications,
        connector=connector,
    )

    logging.info(f"Running strategy version: {config.STRATEGY_VERSION}")

    if trading_brain:
        trading_brain.register_current_version(
            "V5_ASSET_ISOLATED_GUARDED",
            "Scalping Extremo V5 Asset Isolated Guarded",
            {
                "timeframe": "5min",
                "trend_timeframe": "15min",
                "risk_pct": 0.01,
                "max_leverage_factor": 3,
                "sl_atr_mult": 1.2,
                "tp_atr_mult": 2.0,
                "max_total_positions": 8,
                "max_positions_per_symbol": 2,
                "max_positions_by_category": {"crypto": 4, "forex": 6},
                "strategy": "Asset_Isolated_Guarded_Category_Based",
                "ai_enabled": True,
                "ai_features": ["market_regime_detection", "strategy_selection", "per_asset_learning", "gold_guard_mode", "full_toolset_loading", "expert_rules_loading", "backtest_preloaded_scores", "news_aware_trading"],
            },
            "Version V5 con guardias por activo y aislamiento de riesgo. Incluye modo gold guard, reglas expertas y pre-carga de backtest.",
            set_active=False,
        )
        trading_brain.register_current_version(
            "V7_KNOWLEDGE_PRELOADED",
            "Scalping Extremo V7 Knowledge Preloaded",
            {
                "timeframe": "5min",
                "trend_timeframe": "15min",
                "risk_pct": 0.01,
                "max_leverage_factor": 3,
                "sl_atr_mult": 1.2,
                "tp_atr_mult": 2.0,
                "max_total_positions": 20,
                "max_positions_per_symbol": 5,
                "max_positions_by_category": {"crypto": 8, "gold": 8, "forex": 8},
                "strategy": "Knowledge_Preloaded_Extreme_Scalping",
                "ai_enabled": True,
                "ai_features": ["market_regime_detection", "strategy_selection", "per_asset_learning", "fibonacci_scalping", "adaptive_trailing", "news_aware_trading"],
            },
            "Version V7 mejorada con modo scalping extremo. Agregada estrategia Fibonacci Scalp, trailing stop adaptativo por activo, exclusion de activos con bajo rendimiento, y limites de portfolio ampliados.",
            set_active=False,
        )
        trading_brain.register_current_version(
            "V8_EXTREME_SCALPING",
            "Scalping Extremo V8 Fibonacci Max",
            {
                "timeframe": "5min",
                "trend_timeframe": "15min",
                "risk_pct": 0.015,
                "max_leverage_factor": 4,
                "sl_atr_mult": 0.8,
                "tp_atr_mult": 3.5,
                "max_total_positions": 25,
                "max_positions_per_symbol": 6,
                "max_positions_by_category": {"crypto": 10, "gold": 10, "forex": 10},
                "strategy": "Extreme_Fibonacci_Scalping_Max_Power",
                "ai_enabled": True,
                "ai_features": ["market_regime_detection", "strategy_selection", "per_asset_learning", "fibonacci_scalping", "adaptive_trailing", "news_aware_trading", "aggressive_tp", "early_trailing"],
            },
            "Version V8 maxima potencia. Modo scalping extremo con Fibonacci, TP multiples, trailing stop ultra-early (0.15%), riesgo aumentado para activos ganadores, exclusion automatica de perdedores. (Inactiva tras V9)",
            set_active=False,
        )
        # Register V9_SCALPING_MAX_QUALITY
        trading_brain.register_current_version(
            "V9_SCALPING_MAX_QUALITY",
            "Scalping Extremo V9 Max Quality",
            {
                "timeframe": config.ENTRY_TIMEFRAME,
                "trend_timeframe": config.TREND_TIMEFRAME,
                "risk_pct": config.SIZER_DEFAULT_RISK_PCT,
                "max_leverage_factor": config.RISK_MAX_LEVERAGE_FACTOR,
                "sl_atr_mult": config.LEARNING_DEFAULT_SL_ATR_MULT,
                "tp_atr_mult": config.LEARNING_DEFAULT_TP_ATR_MULT,
                "max_total_positions": config.PORTFOLIO_MAX_TOTAL_POSITIONS,
                "max_positions_per_symbol": config.PORTFOLIO_MAX_POSITIONS_PER_SYMBOL,
                "max_positions_by_category": config.PORTFOLIO_MAX_POSITIONS_BY_CATEGORY,
                "strategy": "V9_SCALPING_MAX_QUALITY",
                "ai_enabled": True,
                "ai_features": [
                    "market_regime_detection", "strategy_selection", "per_asset_learning", "fibonacci_scalping",
                    "adaptive_trailing", "news_aware_trading", "aggressive_tp", "early_trailing",
                    "signal_quality_scoring", "signal_justification", "circuit_breaker", "dynamic_risk_filtering",
                ],
                "circuit_breaker_daily_loss_pct_limit": 0.02, # Valor hardcodeado en TradingBrain
                "circuit_breaker_max_consecutive_losses": 3, # Valor hardcodeado en TradingBrain
            },
            "Versión V9 con refactorización completa para máxima calidad de trade, explicabilidad y protección de cuenta. Incluye score de calidad de señal, justificación legible, circuit breaker, filtro de riesgo dinámico y mejoras de código.",
            set_active=False,
        )
        trading_brain.register_current_version(
            "V10_ZERO_LOSS_SCALPING",
            "Scalping Extremo V10 Zero Loss",
            {
                "timeframe": config.ENTRY_TIMEFRAME,
                "trend_timeframe": config.TREND_TIMEFRAME,
                "risk_pct": config.SIZER_DEFAULT_RISK_PCT,
                "max_leverage_factor": config.RISK_MAX_LEVERAGE_FACTOR,
                "sl_atr_mult": config.LEARNING_DEFAULT_SL_ATR_MULT,
                "tp_atr_mult": config.LEARNING_DEFAULT_TP_ATR_MULT,
                "max_total_positions": config.PORTFOLIO_MAX_TOTAL_POSITIONS,
                "max_positions_per_symbol": config.PORTFOLIO_MAX_POSITIONS_PER_SYMBOL,
                "max_positions_by_category": config.PORTFOLIO_MAX_POSITIONS_BY_CATEGORY,
                "strategy": "V10_ZERO_LOSS_SCALPING",
                "ai_enabled": True,
                "ai_features": [
                    "market_regime_detection", "strategy_selection", "per_asset_learning", "fibonacci_scalping",
                    "adaptive_trailing", "news_aware_trading", "aggressive_tp", "early_trailing",
                    "zero_loss_breakeven", "reverse_protection", "gap_protection", "compounding_bonus",
                    "spread_filter", "maximize_profit_objective", "broker_cost_coverage",
                ],
                "circuit_breaker_daily_loss_pct_limit": 0.02,
                "circuit_breaker_max_consecutive_losses": 3,
                "zero_loss_breakeven_trigger_pct": getattr(config, "V10_BREAK_EVEN_TRIGGER_PCT", 0.30),
                "zero_loss_breakeven_min_trigger_points": getattr(config, "V10_BREAK_EVEN_MIN_TRIGGER_POINTS", {}),
                "zero_loss_breakeven_max_trigger_points": getattr(config, "V10_BREAK_EVEN_MAX_TRIGGER_POINTS", {}),
                "reverse_protection_pct": getattr(config, "V10_REVERSE_PROTECTION_PCT", 0.25),
                "gap_protection_pct": getattr(config, "V10_GAP_PROTECTION_PCT", 0.003),
                "pre_breakeven_max_sl_improvement_pct": getattr(config, "V10_PRE_BREAK_EVEN_MAX_SL_IMPROVEMENT_PCT", 0.15),
                "trailing_aggressive_activation_pct": getattr(config, "V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT", 0.003),
                "trailing_aggressive_offset_points": getattr(config, "V10_TRAILING_AGGRESSIVE_OFFSET_POINTS", {}),
                "compounding_volume_multiplier": getattr(config, "V10_COMPOUNDING_VOLUME_MULTIPLIER", 2.0),
                "spread_max_points_multiplier": getattr(config, "V10_SPREAD_MAX_POINTS_MULTIPLIER", 1.5),
            },
            "Version V10 Zero Loss. Break-even al 30% del TP (mínimo en puntos por símbolo < TP distance), SL = entry + costos broker, micro-profit lock, reverse protection 25%, trailing agresivo por puntos, compounding bonus 2x, spread filter por símbolo ajustado.",
            set_active=False,
        )
        # Register V11_CRYPTO_VOLATILITY
        trading_brain.register_current_version(
            "V11_CRYPTO_VOLATILITY",
            "Scalping Extremo V11 Crypto Volatility",
            {
                "strategy": "V11_CRYPTO_VOLATILITY",
                "description": "Hereda V10 y aplica parámetros hiper-agresivos y una nueva estrategia de breakout para criptomonedas.",
                "crypto_params": getattr(config, "V11_CRYPTO_PARAMS", {}),
                "new_strategy": "SignalCryptoVolatilityBreakout",
            },
            "Versión V11 que especializa V10 para criptomonedas con parámetros de break-even y trailing stop más agresivos, y una nueva estrategia de breakout de volatilidad.",
            set_active=False,
        )
        # Register V12_UNIVERSAL_AGGRESSIVE
        trading_brain.register_current_version(
            "V12_UNIVERSAL_AGGRESSIVE",
            "Scalping Extremo V12 Universal Aggressive",
            {
                "strategy": "V12_UNIVERSAL_AGGRESSIVE",
                "description": "Extiende la filosofía agresiva de V11 a Oro y Forex, con parámetros de gestión de riesgo a medida y una nueva estrategia para Oro.",
                "crypto_params": getattr(config, "V11_CRYPTO_PARAMS", {}),
                "aggressive_params": getattr(config, "V12_AGGRESSIVE_PARAMS", {}),
                "new_strategies": ["SignalCryptoVolatilityBreakout", "SignalGoldMomentumReversal"],
            },
            "Versión V12 que universaliza la operativa agresiva. Hereda V11 para cripto y aplica nuevos parámetros para oro y forex. Introduce SignalGoldMomentumReversal.",
            set_active=False,
        )
        # Register V13_DEMO_CLEAN_SLATE
        trading_brain.register_current_version(
            "V13_DEMO_CLEAN_SLATE",
            "Scalping Extremo V13 Demo Clean Slate",
            {
                "strategy": "V13_DEMO_CLEAN_SLATE",
                "description": "Nuevo proyecto demo con activos ampliados: oro, forex, índices y cripto. Base limpia, cerebro IA desde cero, máxima capacidad de análisis y ejecución.",
                "crypto_params": getattr(config, "V11_CRYPTO_PARAMS", {}),
                "aggressive_params": getattr(config, "V12_AGGRESSIVE_PARAMS", {}),
                "new_assets": ["XAUUSD", "EURUSD", "USDJPY", "US500", "USTEC", "BTCUSD", "US30", "ETHUSD", "UKOIL"],
                "new_strategies": ["SignalCryptoVolatilityBreakout", "SignalGoldMomentumReversal"],
            },
            "Versión V13 limpia para demo. Incluye todos los activos: oro, forex, índices US500/USTEC/US30, cripto BTC/ETH y UKOIL. Base sólida PRO para IA y ejecución.",
            set_active=True,
        )

    trading_director: TradingDirector = TradingDirector(
        events_queue=events_queue,
        data_provider=data_provider,
        signal_generator=signal_generator,
        position_sizer=position_sizer,
        break_even_manager=break_even_manager,
        risk_manager=risk_manager,
        order_executor=order_executor,
        notification_service=notifications,
        news_protection=news_protection,
        trading_brain=trading_brain,
        portfolio=portfolio,
        connector=connector,
    )

    if trading_brain:
        trading_brain.save_version_report(
            "V7_KNOWLEDGE_PRELOADED",
            "Scalping Extremo V7 Knowledge Preloaded",
            {
                "timeframe": "5min",
                "trend_timeframe": "15min",
                "risk_pct": 0.01,
                "max_leverage_factor": 3,
                "sl_atr_mult": 1.2,
                "tp_atr_mult": 2.0,
                "max_total_positions": 20,
                "max_positions_per_symbol": 2,
                "max_positions_by_category": {"crypto": 8, "gold": 8, "forex": 8},
                "strategy": "Knowledge_Preloaded_Extreme_Scalping",
                "ai_enabled": True,
                "fibonacci_scalping": True,
                "adaptive_trailing": True,
            },
            "Version previa a optimizacion. Score=20.63, Grade=F, WR=57.2%, PF=0.93",
        )
        trading_brain.save_version_report(
            "V8_EXTREME_SCALPING",
            "Scalping Extremo V8 Fibonacci Max",
            {
                "timeframe": "5min",
                "trend_timeframe": "15min",
                "risk_pct": 0.015,
                "max_leverage_factor": 4,
                "sl_atr_mult": 0.8,
                "tp_atr_mult": 3.5,
                "max_total_positions": 25,
                "max_positions_per_symbol": 6,
                "max_positions_by_category": {"crypto": 10, "gold": 10, "forex": 10},
                "strategy": "Extreme_Fibonacci_Scalping_Max_Power",
                "ai_enabled": True,
                "fibonacci_scalping": True,
                "adaptive_trailing": True,
                "aggressive_tp": True,
                "early_trailing": True,
            },
            "Version optimizada con modo scalping extremo. Incluye estrategia Fibonacci, TP agresivos, trailing ultra-early, exclusion de perdedores. (Informe de V8)",
        )
        trading_brain.save_version_report(
            "V10_ZERO_LOSS_SCALPING",
            "Scalping Extremo V10 Zero Loss",
            {
                "timeframe": config.ENTRY_TIMEFRAME,
                "trend_timeframe": config.TREND_TIMEFRAME,
                "risk_pct": config.SIZER_DEFAULT_RISK_PCT,
                "max_leverage_factor": config.RISK_MAX_LEVERAGE_FACTOR,
                "sl_atr_mult": config.LEARNING_DEFAULT_SL_ATR_MULT,
                "tp_atr_mult": config.LEARNING_DEFAULT_TP_ATR_MULT,
                "max_total_positions": config.PORTFOLIO_MAX_TOTAL_POSITIONS,
                "max_positions_per_symbol": config.PORTFOLIO_MAX_POSITIONS_PER_SYMBOL,
                "max_positions_by_category": config.PORTFOLIO_MAX_POSITIONS_BY_CATEGORY,
                "strategy": "V10_ZERO_LOSS_SCALPING",
                "ai_enabled": True,
                "ai_features": [
                    "market_regime_detection", "strategy_selection", "per_asset_learning", "fibonacci_scalping",
                    "adaptive_trailing", "news_aware_trading", "aggressive_tp", "early_trailing",
                    "zero_loss_breakeven", "reverse_protection", "gap_protection", "compounding_bonus",
                    "spread_filter", "maximize_profit_objective", "broker_cost_coverage",
                ],
                "circuit_breaker_daily_loss_pct_limit": 0.02,
                "circuit_breaker_max_consecutive_losses": 3,
                "zero_loss_breakeven_trigger_pct": getattr(config, "V10_BREAK_EVEN_TRIGGER_PCT", 0.30),
                "zero_loss_breakeven_min_trigger_points": getattr(config, "V10_BREAK_EVEN_MIN_TRIGGER_POINTS", {}),
                "zero_loss_breakeven_max_trigger_points": getattr(config, "V10_BREAK_EVEN_MAX_TRIGGER_POINTS", {}),
                "reverse_protection_pct": getattr(config, "V10_REVERSE_PROTECTION_PCT", 0.25),
                "gap_protection_pct": getattr(config, "V10_GAP_PROTECTION_PCT", 0.003),
                "pre_breakeven_max_sl_improvement_pct": getattr(config, "V10_PRE_BREAK_EVEN_MAX_SL_IMPROVEMENT_PCT", 0.15),
                "trailing_aggressive_activation_pct": getattr(config, "V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT", 0.003),
                "trailing_aggressive_offset_points": getattr(config, "V10_TRAILING_AGGRESSIVE_OFFSET_POINTS", {}),
                "compounding_volume_multiplier": getattr(config, "V10_COMPOUNDING_VOLUME_MULTIPLIER", 2.0),
                "spread_max_points_multiplier": getattr(config, "V10_SPREAD_MAX_POINTS_MULTIPLIER", 1.5),
            },
            "Version V10 Zero Loss. Break-even al 30% del TP (mínimo en puntos por símbolo < TP distance), SL = entry + costos broker, micro-profit lock, reverse protection 25%, trailing agresivo por puntos, compounding bonus 2x, spread filter por símbolo ajustado.",
        )
        trading_brain.save_version_report(
            "V13_DEMO_CLEAN_SLATE",
            "Scalping Extremo V13 Demo Clean Slate",
            {
                "timeframe": config.ENTRY_TIMEFRAME,
                "trend_timeframe": config.TREND_TIMEFRAME,
                "risk_pct": config.SIZER_DEFAULT_RISK_PCT,
                "max_leverage_factor": config.RISK_MAX_LEVERAGE_FACTOR,
                "sl_atr_mult": config.LEARNING_DEFAULT_SL_ATR_MULT,
                "tp_atr_mult": config.LEARNING_DEFAULT_TP_ATR_MULT,
                "max_total_positions": config.PORTFOLIO_MAX_TOTAL_POSITIONS,
                "max_positions_per_symbol": config.PORTFOLIO_MAX_POSITIONS_PER_SYMBOL,
                "max_positions_by_category": config.PORTFOLIO_MAX_POSITIONS_BY_CATEGORY,
                "strategy": "V13_DEMO_CLEAN_SLATE",
                "ai_enabled": True,
                "new_assets": ["XAUUSD", "EURUSD", "USDJPY", "US500", "USTEC", "BTCUSD", "US30", "ETHUSD", "UKOIL"],
            },
            "Version V13 limpia para demo. Incluye todos los activos: oro, forex, índices US500/USTEC/US30, cripto BTC/ETH y UKOIL. Base sólida PRO para IA y ejecución.",
        )

        try:
            trading_brain.resume_open_positions(magic_number=config.MAGIC_NUMBER)
        except Exception as e:
            print(f"{Utils.dateprint()} - BRAIN: Error al reanudar posiciones abiertas: {e}")

        trading_brain.reset_daily_circuit_breaker()
        logging.info("CIRCUIT BREAKER: Reset diario aplicado. Límite diario: %.2f%%", trading_brain._daily_loss_pct_limit * 100)

    try:
        trading_director.execute(max_iterations=max_iterations)
    except RuntimeError as e:
        logging.error(f"La aplicación se detuvo por error crítico: {e}")
        try:
            notifications.send_notification(
                title="🚨 TRADING DETENIDO",
                message=f"La aplicación se detuvo: {str(e)}"
            )
        except Exception as notification_error:
            logging.error("Error enviando notificación de cierre: %s", notification_error, exc_info=True)
        try:
            connector.close()
        except Exception as close_error:
            logging.error("Error cerrando connector MT5: %s", close_error, exc_info=True)
        import sys
        sys.exit(1)
