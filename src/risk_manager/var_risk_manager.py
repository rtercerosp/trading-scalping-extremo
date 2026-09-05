import numpy as np
import pandas as pd
from typing import Optional, Dict, List
from dataclasses import dataclass
from scipy import stats
from queue import Queue

from events.events import SizingEvent, OrderEvent
from data_provider.data_provider import DataProvider
from platform_connector.platform_connector import PlatformConnector
from portfolio.portfolio import Portfolio
from notifications.notifications import NotificationService
from risk_manager.interfaces.risk_manager_interface import IRiskManager
from risk_manager.properties.risk_manager_properties import BaseRiskProps
from utils.utils import Utils
from .coinglass_oracle import CoinGlassOracle, create_coinglass_oracle_from_config, TrafficLight


@dataclass
class VaRResult:
    """Value at Risk calculation result."""
    var_95: float          # 95% VaR (1-day)
    var_99: float          # 99% VaR (1-day)
    cvar_95: float         # 95% Conditional VaR (Expected Shortfall)
    cvar_99: float         # 99% Conditional VaR (Expected Shortfall)
    portfolio_value: float  # Current portfolio value
    var_pct_95: float      # 95% VaR as percentage of portfolio
    var_pct_99: float      # 99% VaR as percentage of portfolio
    correlated_exposure: float  # Total correlated exposure
    threshold_breached: bool     # Whether safety threshold exceeded
    timestamp: str         # Calculation timestamp


@dataclass
class CorrelationMatrix:
    """Asset correlation matrix with metadata."""
    matrix: pd.DataFrame
    symbols: List[str]
    last_updated: str
    lookback_periods: int


class VaRRiskManager(IRiskManager):
    """
    Value at Risk (VaR) Risk Manager for portfolio-level risk control.
    
    Calculates portfolio VaR using historical simulation and parametric methods.
    If correlated exposure exceeds safety threshold, forces reduction of risk_pct
    in PositionSizer as proactive barrier before circuit breaker activation.
    
    Features:
    - Historical Simulation VaR (non-parametric)
    - Parametric VaR (assuming normal/fat-tailed distributions)
    - Cornish-Fisher expansion for skewness/kurtosis adjustment
    - Dynamic correlation matrix with exponential weighting
    - Portfolio-level and per-symbol risk budgets
    - Proactive risk_pct reduction when exposure limits breached
    """
    
    def __init__(
        self,
        events_queue: Queue,
        data_provider: DataProvider,
        portfolio: Portfolio,
        risk_properties: BaseRiskProps,
        notification_service: NotificationService,
        connector: PlatformConnector,
        var_confidence_levels: List[float] = None,
        lookback_periods: int = 252,
        correlation_half_life: int = 60,
        max_portfolio_var_pct: float = 0.05,  # 5% max portfolio VaR at 95%
        max_correlated_exposure_pct: float = 0.15,  # 15% max correlated exposure
        risk_reduction_factor: float = 0.5,  # Reduce risk_pct by 50% when threshold breached
        min_risk_pct: float = 0.0025,  # Minimum risk_pct (from config)
        max_risk_pct: float = 0.02,    # Maximum risk_pct (from config)
        coinglass_oracle: Optional[CoinGlassOracle] = None,
        enable_derivatives_filter: bool = True,
    ):
        self.events_queue = events_queue
        self.data_provider = data_provider
        self.portfolio = portfolio
        self.notification_service = notification_service
        self.connector = connector
        
        # VaR configuration
        self.var_confidence_levels = var_confidence_levels or [0.95, 0.99]
        self.lookback_periods = lookback_periods
        self.correlation_half_life = correlation_half_life
        self.max_portfolio_var_pct = max_portfolio_var_pct
        self.max_correlated_exposure_pct = max_correlated_exposure_pct
        self.risk_reduction_factor = risk_reduction_factor
        self.min_risk_pct = min_risk_pct
        self.max_risk_pct = max_risk_pct
        
        # CoinGlass Oracle for derivatives filtering
        self.coinglass_oracle = coinglass_oracle or (create_coinglass_oracle_from_config() if enable_derivatives_filter else None)
        self.enable_derivatives_filter = enable_derivatives_filter and self.coinglass_oracle is not None
        
        # State
        self._correlation_matrix: Optional[CorrelationMatrix] = None
        self._historical_returns: Dict[str, np.ndarray] = {}
        self._last_var_result: Optional[VaRResult] = None
        self._risk_pct_multiplier = 1.0  # Applied to PositionSizer risk_pct
        self._derivatives_risk_multiplier = 1.0
        
    def assess_order(self, sizing_event: SizingEvent) -> float | None:
        """
        Assess order through VaR lens with CoinGlass derivatives filtering.
        
        If portfolio VaR exceeds threshold, reduce the position size by
        adjusting the effective risk_pct before passing to position sizer.
        
        Applies CDRI-based penalty factor: RiskFactor_final = RiskFactor_base * (1 - CDRI/100)
        Blocks LONG entries when traffic light is RED.
        """
        symbol = getattr(sizing_event, 'symbol', None)
        signal_direction = getattr(sizing_event, 'signal', None)
        
        # Calculate current portfolio VaR
        var_result = self.calculate_portfolio_var()
        self._last_var_result = var_result
        
        # Check if VaR threshold breached
        if var_result.threshold_breached:
            # Reduce risk multiplier
            self._risk_pct_multiplier = self.risk_reduction_factor
            self._notify_var_breach(var_result)
        else:
            # Gradually restore risk multiplier (with hysteresis)
            self._risk_pct_multiplier = min(1.0, self._risk_pct_multiplier * 1.05)
        
        # Apply CoinGlass derivatives filter
        if self.enable_derivatives_filter and self.coinglass_oracle and symbol:
            try:
                # Get CDRI-based risk multiplier: (1 - CDRI/100)
                derivatives_multiplier = self.coinglass_oracle.get_risk_multiplier(symbol)
                self._derivatives_risk_multiplier = derivatives_multiplier
                
                # Check traffic light for LONG blocking
                light, details = self.coinglass_oracle.get_market_traffic_light(symbol)
                
                if light == TrafficLight.RED and signal_direction == "BUY":
                    # Block LONG entries completely in RED
                    print(f"{Utils.dateprint()} - VaR Risk Manager: LONG BLOCKED for {symbol} - CDRI={details['cdri']:.1f} (RED light)")
                    return 0.0
                
                # Apply position multiplier from traffic light
                position_multiplier = details.get("position_multiplier", 1.0)
                
                # Log derivatives filter status
                print(f"{Utils.dateprint()} - VaR Risk Manager: Derivatives filter for {symbol} - "
                      f"CDRI={details['cdri']:.1f}, Light={light.value}, "
                      f"RiskMult={derivatives_multiplier:.3f}, PosMult={position_multiplier:.2f}")
                
            except Exception as e:
                print(f"{Utils.dateprint()} - VaR Risk Manager: Derivatives filter error: {e}")
                self._derivatives_risk_multiplier = 1.0
        else:
            self._derivatives_risk_multiplier = 1.0
        
        # Apply combined risk reduction to sizing event
        if hasattr(sizing_event, 'risk_pct_override') and sizing_event.risk_pct_override > 0:
            # RiskFactor_final = RiskFactor_base * (1 - CDRI/100) * VaR_multiplier
            combined_multiplier = self._risk_pct_multiplier * self._derivatives_risk_multiplier
            adjusted_risk = sizing_event.risk_pct_override * combined_multiplier
            adjusted_risk = max(self.min_risk_pct, min(self.max_risk_pct, adjusted_risk))
            sizing_event.risk_pct_override = adjusted_risk
        
        # Delegate to next risk manager in chain (if any) or approve
        # For now, we return the volume as-is but with adjusted risk_pct_override
        # The actual volume calculation happens in PositionSizer
        return sizing_event.volume
    
    def calculate_portfolio_var(self) -> VaRResult:
        """
        Calculate portfolio Value at Risk using multiple methods.
        
        Returns:
            VaRResult with VaR, CVaR, and threshold breach status
        """
        # Get current positions
        positions = self.portfolio.get_strategy_open_positions()
        if not positions:
            return self._empty_var_result()
        
        # Get symbols and weights
        symbols = []
        weights = []
        portfolio_value = 0.0
        
        account_info = self.connector.get_account_info()
        if account_info:
            portfolio_value = account_info.equity
        
        for pos in positions:
            symbols.append(pos.symbol)
            # Calculate position value in account currency
            pos_value = self._get_position_value(pos)
            weights.append(pos_value)
        
        if portfolio_value <= 0:
            return self._empty_var_result()
        
        weights = np.array(weights) / portfolio_value
        
        # Get historical returns for each symbol
        returns_matrix = self._get_historical_returns_matrix(symbols)
        if returns_matrix is None or returns_matrix.shape[1] == 0:
            return self._empty_var_result()
        
        # Calculate portfolio returns
        portfolio_returns = returns_matrix @ weights
        
        # Calculate VaR using historical simulation
        var_95 = np.percentile(portfolio_returns, (1 - 0.95) * 100)
        var_99 = np.percentile(portfolio_returns, (1 - 0.99) * 100)
        
        # Calculate CVaR (Expected Shortfall)
        cvar_95 = portfolio_returns[portfolio_returns <= var_95].mean() if len(portfolio_returns[portfolio_returns <= var_95]) > 0 else var_95
        cvar_99 = portfolio_returns[portfolio_returns <= var_99].mean() if len(portfolio_returns[portfolio_returns <= var_99]) > 0 else var_99
        
        # Apply Cornish-Fisher adjustment for skewness/kurtosis
        var_95_cf = self._cornish_fisher_var(portfolio_returns, 0.95)
        var_99_cf = self._cornish_fisher_var(portfolio_returns, 0.99)
        
        # Use more conservative (higher) VaR
        var_95 = min(var_95, var_95_cf)  # More negative = higher risk
        var_99 = min(var_99, var_99_cf)
        
        # Convert to positive values for reporting (loss amounts)
        var_95_abs = abs(var_95) * portfolio_value
        var_99_abs = abs(var_99) * portfolio_value
        cvar_95_abs = abs(cvar_95) * portfolio_value
        cvar_99_abs = abs(cvar_99) * portfolio_value
        
        # Calculate correlated exposure
        correlated_exposure = self._calculate_correlated_exposure(symbols, weights, portfolio_value)
        correlated_exposure_pct = correlated_exposure / portfolio_value if portfolio_value > 0 else 0
        
        # Check thresholds
        var_pct_95 = var_95_abs / portfolio_value if portfolio_value > 0 else 0
        var_pct_99 = var_99_abs / portfolio_value if portfolio_value > 0 else 0
        
        threshold_breached = (
            var_pct_95 > self.max_portfolio_var_pct or
            correlated_exposure_pct > self.max_correlated_exposure_pct
        )
        
        return VaRResult(
            var_95=var_95_abs,
            var_99=var_99_abs,
            cvar_95=cvar_95_abs,
            cvar_99=cvar_99_abs,
            portfolio_value=portfolio_value,
            var_pct_95=var_pct_95,
            var_pct_99=var_pct_99,
            correlated_exposure=correlated_exposure,
            threshold_breached=threshold_breached,
            timestamp=Utils.dateprint()
        )
    
    def _get_historical_returns_matrix(self, symbols: List[str]) -> Optional[np.ndarray]:
        """Build aligned historical returns matrix for all symbols."""
        all_returns = {}
        min_length = float('inf')
        
        for symbol in symbols:
            bars = self.data_provider.get_latest_closed_bars(symbol, "1h", self.lookback_periods + 10)
            if bars.empty or len(bars) < 20:
                continue
            
            close = bars['close'].values
            returns = np.diff(close) / close[:-1]
            all_returns[symbol] = returns
            min_length = min(min_length, len(returns))
        
        if not all_returns or min_length < 20:
            return None
        
        # Align all series to same length (most recent)
        aligned_returns = {}
        for symbol, returns in all_returns.items():
            aligned_returns[symbol] = returns[-min_length:]
        
        # Create matrix (time x assets)
        return_matrix = np.column_stack([aligned_returns[s] for s in symbols if s in aligned_returns])
        
        # Update correlation matrix
        self._update_correlation_matrix(symbols, return_matrix)
        
        return return_matrix
    
    def _update_correlation_matrix(self, symbols: List[str], returns_matrix: np.ndarray) -> None:
        """Update exponentially weighted correlation matrix."""
        if returns_matrix.shape[0] < 20:
            return
        
        # Exponential weights
        n = returns_matrix.shape[0]
        weights = np.exp(np.linspace(-n / self.correlation_half_life, 0, n))
        weights = weights / weights.sum()
        
        # Weighted correlation
        weighted_returns = returns_matrix * weights[:, np.newaxis]
        corr_matrix = np.corrcoef(weighted_returns, rowvar=False)
        
        self._correlation_matrix = CorrelationMatrix(
            matrix=pd.DataFrame(corr_matrix, index=symbols, columns=symbols),
            symbols=symbols,
            last_updated=Utils.dateprint(),
            lookback_periods=n
        )
    
    def _calculate_correlated_exposure(
        self, 
        symbols: List[str], 
        weights: np.ndarray,
        portfolio_value: float
    ) -> float:
        """Calculate total correlated exposure using correlation matrix."""
        if self._correlation_matrix is None or portfolio_value <= 0:
            # Fallback: sum of absolute weights
            return np.sum(np.abs(weights)) * portfolio_value
        
        # Get correlation submatrix for current symbols
        common_symbols = [s for s in symbols if s in self._correlation_matrix.symbols]
        if len(common_symbols) < 2:
            return np.sum(np.abs(weights)) * portfolio_value
        
        try:
            idx = [symbols.index(s) for s in common_symbols]
            sub_weights = weights[idx]
            sub_corr = self._correlation_matrix.matrix.loc[common_symbols, common_symbols].values
            
            # Validate dimensions match
            if sub_weights.shape[0] != sub_corr.shape[0]:
                return np.sum(np.abs(weights)) * portfolio_value
            
            # Portfolio variance = w' * Σ * w
            # Correlated exposure ~ sqrt(w' * Σ * w) * portfolio_value
            portfolio_variance = sub_weights @ sub_corr @ sub_weights
            correlated_exposure = np.sqrt(max(portfolio_variance, 0)) * portfolio_value
            
            return correlated_exposure
        except Exception:
            # Fallback on any matrix computation error
            return np.sum(np.abs(weights)) * portfolio_value
    
    def _cornish_fisher_var(self, returns: np.ndarray, confidence: float) -> float:
        """
        Cornish-Fisher VaR adjustment for skewness and kurtosis.
        
        z_cf = z + (z²-1)S/6 + (z³-3z)K/24 - (2z³-5z)S²/36
        where S = skewness, K = excess kurtosis
        """
        if len(returns) < 30:
            return np.percentile(returns, (1 - confidence) * 100)
        
        z = stats.norm.ppf(1 - confidence)
        skewness = stats.skew(returns)
        kurtosis = stats.kurtosis(returns)  # Excess kurtosis
        
        z_cf = (z + 
                (z**2 - 1) * skewness / 6 + 
                (z**3 - 3*z) * kurtosis / 24 - 
                (2*z**3 - 5*z) * skewness**2 / 36)
        
        # Convert back to quantile
        mu = np.mean(returns)
        sigma = np.std(returns)
        
        return mu + z_cf * sigma
    
    def _get_position_value(self, position) -> float:
        """Get position value in account currency."""
        symbol_info = self.connector.get_symbol_info(position.symbol)
        if symbol_info is None:
            return 0.0
        
        latest_tick = self.data_provider.get_latest_tick(position.symbol)
        if not latest_tick:
            return 0.0
        
        traded_units = position.volume * symbol_info.trade_contract_size
        price_key = 'ask' if position.type == 1 else 'bid'
        market_price = latest_tick.get(price_key) or latest_tick.get('bid') or latest_tick.get('ask')
        if market_price is None:
            return 0.0
        
        value_traded_in_profit_ccy = traded_units * market_price
        account_info = self.connector.get_account_info()
        if account_info is None:
            return 0.0
        
        value_traded_in_account_ccy = self.connector.convert_currency_amount_to_another_currency(
            value_traded_in_profit_ccy, symbol_info.currency_profit, account_info.currency
        )
        
        return value_traded_in_account_ccy
    
    def _empty_var_result(self) -> VaRResult:
        """Return empty VaR result when no positions or data."""
        return VaRResult(
            var_95=0.0,
            var_99=0.0,
            cvar_95=0.0,
            cvar_99=0.0,
            portfolio_value=0.0,
            var_pct_95=0.0,
            var_pct_99=0.0,
            correlated_exposure=0.0,
            threshold_breached=False,
            timestamp=Utils.dateprint()
        )
    
    def _notify_var_breach(self, var_result: VaRResult) -> None:
        """Send notification when VaR threshold breached."""
        try:
            message = (
                f"⚠️ VaR THRESHOLD BREACHED\n"
                f"Portfolio VaR (95%): {var_result.var_pct_95:.2%} (limit: {self.max_portfolio_var_pct:.2%})\n"
                f"Correlated Exposure: {var_result.correlated_exposure/var_result.portfolio_value:.2%} (limit: {self.max_correlated_exposure_pct:.2%})\n"
                f"Risk multiplier reduced to: {self._risk_pct_multiplier:.2f}"
            )
            self.notification_service.send_notification(
                title="🚨 VaR Risk Alert",
                message=message
            )
        except Exception as e:
            print(f"{Utils.dateprint()} - VaR Risk Manager: Notification error: {e}")
    
    def get_var_report(self) -> Dict:
        """Get detailed VaR report for monitoring."""
        if self._last_var_result is None:
            self.calculate_portfolio_var()
        
        if self._last_var_result is None:
            return {}
        
        vr = self._last_var_result
        report = {
            "var_95": vr.var_95,
            "var_99": vr.var_99,
            "cvar_95": vr.cvar_95,
            "cvar_99": vr.cvar_99,
            "portfolio_value": vr.portfolio_value,
            "var_pct_95": vr.var_pct_95,
            "var_pct_99": vr.var_pct_99,
            "correlated_exposure": vr.correlated_exposure,
            "correlated_exposure_pct": vr.correlated_exposure / vr.portfolio_value if vr.portfolio_value > 0 else 0,
            "threshold_breached": vr.threshold_breached,
            "risk_pct_multiplier": self._risk_pct_multiplier,
            "derivatives_risk_multiplier": self._derivatives_risk_multiplier,
            "combined_risk_multiplier": self._risk_pct_multiplier * self._derivatives_risk_multiplier,
            "max_var_pct": self.max_portfolio_var_pct,
            "max_correlated_exposure_pct": self.max_correlated_exposure_pct,
            "timestamp": vr.timestamp,
            "correlation_matrix_age": (
                (pd.Timestamp.now() - pd.Timestamp(self._correlation_matrix.last_updated)).total_seconds() / 3600
                if self._correlation_matrix else None
            ),
            "derivatives_filter_enabled": self.enable_derivatives_filter,
        }
        
        if self.enable_derivatives_filter and self.coinglass_oracle:
            try:
                symbols = [pos.symbol for pos in self.portfolio.get_strategy_open_positions()]
                derivatives_details = {}
                for sym in symbols:
                    light, details = self.coinglass_oracle.get_market_traffic_light(sym)
                    derivatives_details[sym] = details
                report["derivatives_details"] = derivatives_details
            except Exception:
                pass
        
        return report
    
    def get_risk_pct_multiplier(self) -> float:
        """Get current risk_pct multiplier (for PositionSizer integration)."""
        return self._risk_pct_multiplier * self._derivatives_risk_multiplier
    
    def get_derivatives_multiplier(self) -> float:
        """Get current derivatives filter multiplier."""
        return self._derivatives_risk_multiplier
    
    def force_risk_reduction(self, factor: float = None) -> None:
        """Manually force risk reduction (e.g., from external risk signal)."""
        self._risk_pct_multiplier = factor if factor is not None else self.risk_reduction_factor
        print(f"{Utils.dateprint()} - VaR Risk Manager: Manual risk reduction to {self._risk_pct_multiplier:.2f}")


class VaRRiskProps(BaseRiskProps):
    """Properties for VaR Risk Manager."""
    var_confidence_levels: List[float] = [0.95, 0.99]
    lookback_periods: int = 252
    correlation_half_life: int = 60
    max_portfolio_var_pct: float = 0.05
    max_correlated_exposure_pct: float = 0.15
    risk_reduction_factor: float = 0.5
    min_risk_pct: float = 0.0025
    max_risk_pct: float = 0.02