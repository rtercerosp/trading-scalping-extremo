# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from data_provider.data_provider import DataProvider
from platform_connector.platform_connector import PlatformConnector
from events.events import SignalEvent
from ..interfaces.position_sizer_interface import IPositionSizer
from ..properties.position_sizer_properties import RiskPctSizingProps
from utils.utils import Utils
from utils.symbol_utils import normalize_symbol
import config
import logging

logger = logging.getLogger(__name__)

class RiskPctPositionSizer(IPositionSizer):

    # Regla del 1% inviolable: nunca arriesgar más del 1% del capital por operación
    MAX_RISK_PCT_PER_TRADE = 0.01  # 1%

    def __init__(self, properties: RiskPctSizingProps, connector: PlatformConnector, get_risk_pct_callback=None, portfolio=None, max_leverage_factor=None):
        self.risk_pct = min(properties.risk_pct, self.MAX_RISK_PCT_PER_TRADE)
        self.connector = connector
        self.get_risk_pct_callback = get_risk_pct_callback
        self.portfolio = portfolio
        self.max_leverage_factor = max_leverage_factor or getattr(config, "RISK_MAX_LEVERAGE_FACTOR", None)

    def size_signal(self, signal_event: SignalEvent, data_provider: DataProvider) -> float:
        """
        Calculates the size of the position based on the risk percentage and signal event data.
        ENFORCES 1% MAX RISK RULE: Volume is calculated to risk exactly 1% (or less) of equity.
        """
        risk_pct = self.risk_pct
        if getattr(signal_event, 'risk_pct_override', 0.0) > 0.0:
            risk_pct = signal_event.risk_pct_override
        if self.get_risk_pct_callback:
            try:
                adaptive_risk = self.get_risk_pct_callback(signal_event.symbol)
                if adaptive_risk and adaptive_risk > 0:
                    risk_pct = adaptive_risk
            except Exception as e:
                logger.error("RISK SIZER: Error obteniendo risk_pct adaptativo para %s: %s", signal_event.symbol, e, exc_info=True)

        # Aplicar boost por mejor activo al riesgo (PERO NUNCA superar 1%)
        boost_multiplier = getattr(signal_event, 'boost_multiplier', 1.0)
        if boost_multiplier > 1.0:
            risk_pct *= boost_multiplier
            print(f"{Utils.dateprint()} - BOOST: {signal_event.symbol} TOP performer - riesgo aumentado x{boost_multiplier:.1f} a {risk_pct:.2%}")

        # REGLA DEL 1% INVIOLABLE: Clampear risk_pct a máximo 1%
        if risk_pct > self.MAX_RISK_PCT_PER_TRADE:
            print(f"{Utils.dateprint()} - RISK SIZER: ⚠️ risk_pct {risk_pct:.4%} excede límite 1%. Clampeando a {self.MAX_RISK_PCT_PER_TRADE:.2%}")
            risk_pct = self.MAX_RISK_PCT_PER_TRADE

        if risk_pct <= 0.0:
            print(f"{Utils.dateprint()} - ERROR (RiskPctPositionSizer): El porcentaje de riesgo introducido: {risk_pct} no es válido.")
            return 0.0

        if signal_event.sl <= 0.0:
            print(f"{Utils.dateprint()} - ERROR (RiskPctPositionSizer): El valor del SL: {signal_event.sl} no es válido.")
            return 0.0
        
        account_info = self.connector.get_account_info()
        if not account_info:
            print(f"{Utils.dateprint()} - ERROR (RiskPctPositionSizer): No se pudo obtener la información de la cuenta.")
            return 0.0
        
        symbol_info = self.connector.get_symbol_info(signal_event.symbol)
        if not symbol_info:
            print(f"{Utils.dateprint()} - ERROR (RiskPctPositionSizer): No se pudo obtener la información del símbolo {signal_event.symbol}.")
            return 0.0

        last_tick = data_provider.get_latest_tick(signal_event.symbol)
        if not last_tick:
            print(f"{Utils.dateprint()} - ERROR (RiskPctPositionSizer): No se pudo obtener el último tick para {signal_event.symbol}.")
            return 0.0

        if signal_event.target_order == "MARKET":
            entry_price = last_tick['ask'] if signal_event.signal == "BUY" else last_tick['bid']

        else:
            entry_price = signal_event.target_price

        equity = account_info.equity
        volume_step = symbol_info.volume_step
        tick_size = symbol_info.trade_tick_size
        account_ccy = account_info.currency
        symbol_profit_ccy = symbol_info.currency_profit
        contract_size = symbol_info.trade_contract_size

        tick_value_profit_ccy = contract_size * tick_size
        tick_value_account_ccy = self.connector.convert_currency_amount_to_another_currency(tick_value_profit_ccy, symbol_profit_ccy, account_ccy)

        max_allowed_volume = getattr(symbol_info, 'volume_max', None)
        if max_allowed_volume is None and self.portfolio is not None:
            max_for_symbol = self.portfolio.max_positions_by_symbol.get(normalize_symbol(signal_event.symbol), getattr(self.portfolio, 'max_positions_per_symbol', 2))
            max_allowed_volume = max(0.01, float(max_for_symbol))
        
        try:
            price_distance_in_ticks = abs(entry_price - signal_event.sl) / tick_size
            if price_distance_in_ticks < 1:
                print(f"{Utils.dateprint()} - ERROR (RiskPctPositionSizer): La distancia entre el precio de entrada y el SL es menor que un tick. No se puede calcular el volumen.")
                return 0.0

            min_sl_distance_pct = 0.001
            if price_distance_in_ticks * tick_size < entry_price * min_sl_distance_pct:
                price_distance_in_ticks = int(entry_price * min_sl_distance_pct / tick_size)
                if price_distance_in_ticks < 1:
                    price_distance_in_ticks = 1

            price_distance_in_integer_ticksizes = int(price_distance_in_ticks)
            monetary_risk = equity * risk_pct
            volume = monetary_risk / (price_distance_in_integer_ticksizes * tick_value_account_ccy) if tick_value_account_ccy > 0 else 0
            volume = round(volume / volume_step) * volume_step

            # VERIFICACIÓN MATEMÁTICA: El volumen calculado DEBE resultar en riesgo ≤ 1%
            actual_risk_pct = (price_distance_in_integer_ticksizes * tick_value_account_ccy * volume) / equity if equity > 0 else 0
            if actual_risk_pct > self.MAX_RISK_PCT_PER_TRADE * 1.001:  # Tolerancia 0.1% por redondeo
                print(f"{Utils.dateprint()} - RISK SIZER: ⚠️ Riesgo real {actual_risk_pct:.4%} > 1%. Ajustando volumen...")
                volume = (equity * self.MAX_RISK_PCT_PER_TRADE) / (price_distance_in_integer_ticksizes * tick_value_account_ccy)
                volume = round(volume / volume_step) * volume_step

            max_volume_by_equity = None
            if equity > 0 and entry_price > 0 and contract_size > 0:
                notional_value = entry_price * contract_size
                max_notional_pct = getattr(config, "PORTFOLIO_MAX_NOTIONAL_PCT_PER_TRADE", 0.25)
                max_volume_by_equity = equity * max_notional_pct / notional_value
                max_volume_by_equity = max(symbol_info.volume_min, round(max_volume_by_equity / volume_step) * volume_step)
                if max_volume_by_equity < volume:
                    volume = max_volume_by_equity
                    print(f"{Utils.dateprint()} - RISK MGMT: Volumen limitado por notional por trade a {max_volume_by_equity:.4f} lotes para {signal_event.symbol} (calculado: {monetary_risk / (price_distance_in_integer_ticksizes * tick_value_account_ccy):.4f})")

            if self.max_leverage_factor and equity > 0 and entry_price > 0 and contract_size > 0:
                notional_value = entry_price * contract_size
                max_volume_by_leverage = equity * self.max_leverage_factor / notional_value
                max_volume_by_leverage = max(symbol_info.volume_min, round(max_volume_by_leverage / volume_step) * volume_step)
                if max_volume_by_leverage < volume:
                    volume = max_volume_by_leverage
                    print(f"{Utils.dateprint()} - RISK MGMT: Volumen limitado por leverage max ({self.max_leverage_factor}x) a {max_volume_by_leverage:.4f} lotes para {signal_event.symbol}")

            if max_allowed_volume is not None and volume > max_allowed_volume:
                volume = max_allowed_volume
                print(f"{Utils.dateprint()} - RISK MGMT: Volumen limitado a {max_allowed_volume} lotes para {signal_event.symbol} (calculado: {monetary_risk / (price_distance_in_integer_ticksizes * tick_value_account_ccy):.4f})")

            volume_min = getattr(symbol_info, 'volume_min', 0.0)
            if volume_min > 0 and volume < volume_min:
                if max_allowed_volume is not None and volume_min > max_allowed_volume:
                    print(f"{Utils.dateprint()} - ERROR (RiskPctPositionSizer): volume_min ({volume_min}) > max_allowed_volume ({max_allowed_volume}) para {signal_event.symbol}. No se puede operar con los parámetros de riesgo actuales.")
                    return 0.0
                volume = volume_min
                print(f"{Utils.dateprint()} - WARNING (RiskPctPositionSizer): Volumen ajustado a volume_min {volume_min} para {signal_event.symbol}.")
            
            # Aplicar boost por mejor activo al volumen (después de verificaciones de riesgo)
            boost_multiplier = getattr(signal_event, 'boost_multiplier', 1.0)
            if boost_multiplier > 1.0:
                volume = round(volume * boost_multiplier / volume_step) * volume_step
                print(f"{Utils.dateprint()} - BOOST: {signal_event.symbol} TOP performer - volumen aumentado x{boost_multiplier:.1f} a {volume:.4f} lotes")
            
            # VERIFICACIÓN FINAL: Confirmar riesgo ≤ 1%
            final_risk_pct = (price_distance_in_integer_ticksizes * tick_value_account_ccy * volume) / equity if equity > 0 else 0
            print(f"{Utils.dateprint()} - RISK SIZER: {signal_event.symbol} Volumen={volume:.4f} lotes | Riesgo={final_risk_pct:.4%} (Máx 1%) | SL Dist={price_distance_in_integer_ticksizes} ticks | Equity={equity:.2f}")

            return volume

        except Exception as e:
            print(f"{Utils.dateprint()} - ERROR: Problema al calcular el tamaño de la posición en función del riesgo. Excepción: {e}")
            return 0.0
