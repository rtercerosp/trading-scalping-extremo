# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from platform_connector.platform_connector import PlatformConnector
from .interfaces.risk_manager_interface import IRiskManager
from .properties.risk_manager_properties import BaseRiskProps, MaxLeverageFactorRiskProps
from .risk_managers.max_leverage_factor_risk_manager import MaxLeverageFactorRiskManager
from data_provider.data_provider import DataProvider
from portfolio.portfolio import Portfolio
from notifications.notifications import NotificationService
from events.events import SizingEvent, OrderEvent
from utils.utils import Utils
from queue import Queue

class RiskManager(IRiskManager):
    
    def __init__(self, events_queue: Queue, data_provider: DataProvider, portfolio: Portfolio, risk_properties: BaseRiskProps, notification_service: NotificationService, connector: PlatformConnector):
        """
        Initializes a RiskManager object.

        Args:
            events_queue (Queue): The queue for receiving events.
            data_provider (DataProvider): The data provider for retrieving market data.
            portfolio (Portfolio): The portfolio object for managing positions and balances.
            risk_properties (BaseRiskProps): The risk properties object for configuring risk management.
            notification_service (NotificationService): The notification service object.
            connector (PlatformConnector): The platform connector instance.

        Returns:
            None
        """
        self.events_queue = events_queue
        self.data_provider = data_provider
        self.portfolio = portfolio
        self.notification_service = notification_service
        self.connector = connector
        self.risk_management_method = self._get_risk_management_method(risk_properties, self.notification_service, self.connector)
    
    def _get_risk_management_method(self, risk_props: BaseRiskProps, notification_service: NotificationService, connector: PlatformConnector) -> IRiskManager:
        """
        Returns the appropriate risk management method based on the given risk properties.

        Args:
            risk_props (BaseRiskProps): The risk properties object.

        Returns:
            IRiskManager: An instance of the appropriate risk manager.

        Raises:
            Exception: If the risk management method is unknown.
        """
        if isinstance(risk_props, MaxLeverageFactorRiskProps):
            return MaxLeverageFactorRiskManager(risk_props, notification_service, connector)
        else:
            raise Exception(f"ERROR: Método de Risk Mgmt desconocido: {risk_props}")

    def _compute_current_value_of_positions_in_account_currency(self) -> float:
        """
        Computes the current value of positions in the account currency.

        Returns:
            float: The total value of the positions in the account currency.
        """

        # Recopilamos las posiciones abiertas por nuestra estrategia
        current_positions = self.portfolio.get_strategy_open_positions()

        # Vamos a calcular el valor de las posiciones abiertas
        total_value = 0.0
        for position in current_positions:
            total_value += self._compute_value_of_position_in_account_currency(position.symbol, position.volume, position.type)
        
        return total_value

    def _compute_value_of_position_in_account_currency(self, symbol: str, volume: float, position_type: int) -> float:
        """
        Computes the REQUIRED MARGIN of a position in the account currency.
        Uses account leverage to convert notional value into margin requirement.
        """
        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            print(f"{Utils.dateprint()} - RISK MGMT: No se pudo recuperar symbol_info para {symbol}.")
            return 0.0

        latest_tick = self.data_provider.get_latest_tick(symbol)
        if not latest_tick:
            print(f"{Utils.dateprint()} - RISK MGMT: No se pudo recuperar el último tick para {symbol}.")
            return 0.0

        account_info = self.connector.get_account_info()
        if account_info is None:
            print(f"{Utils.dateprint()} - RISK MGMT: No se pudo recuperar account_info de MT5.")
            return 0.0

        # Unidades operadas en las unidades del symbol: (cantidad de moneda base, barriles de petroleo, onzas de oro)
        traded_units = volume * symbol_info.trade_contract_size

        # Valor de las unidades operadas en la divisa cotizada del símbolo
        price_key = 'ask' if position_type == 1 else 'bid'
        market_price = latest_tick.get(price_key) or latest_tick.get('bid') or latest_tick.get('ask')
        if market_price is None:
            print(f"{Utils.dateprint()} - RISK MGMT: Tick incompleto para {symbol}.")
            return 0.0
        value_traded_in_profit_ccy = traded_units * market_price

        # Valor en la divisa de la cuenta
        value_traded_in_account_ccy = self.connector.convert_currency_amount_to_another_currency(value_traded_in_profit_ccy, symbol_info.currency_profit, account_info.currency)

        # Usar margen real considerando el leverage de la cuenta
        account_leverage = getattr(account_info, 'leverage', 100) or 100
        margin_required = value_traded_in_account_ccy / account_leverage

        return margin_required

    def _create_and_put_order_event(self, sizing_event: SizingEvent, volume: float) -> None:
        """
        Creates an OrderEvent based on the given SizingEvent and volume, and puts it into the events queue.

        Args:
            sizing_event (SizingEvent): The sizing event to create the order event from.
            volume (float): The volume for the order event.

        Returns:
            None
        """
        order_event = OrderEvent(symbol=sizing_event.symbol,
                                    signal=sizing_event.signal,
                                    target_order=sizing_event.target_order,
                                    target_price=sizing_event.target_price,
                                    magic_number=sizing_event.magic_number,
                                    sl=sizing_event.sl,
                                    tp=sizing_event.tp,
                                    tp1=sizing_event.tp1,
                                    tp2=sizing_event.tp2,
                                    volume=volume,
                                    strategy_name=sizing_event.strategy_name,
                                    primary_strategy_name=sizing_event.primary_strategy_name,
                                    asset_category=sizing_event.asset_category,
                                    market_regime=sizing_event.market_regime,
                                    analysis_context=sizing_event.analysis_context,
                                    risk_pct_override=sizing_event.risk_pct_override,
                                    quality_score=sizing_event.quality_score,
                                    justification=sizing_event.justification)

        self.events_queue.put(order_event)
    
    def assess_order(self, sizing_event: SizingEvent) -> None:
        """
        Assess the order based on the risk management method and create an order event if the new volume is greater than 0.

        Args:
            sizing_event (SizingEvent): The sizing event containing information about the order.

        Returns:
            None
        """
        
        # Obtenemos el valor de todas las posiciones abiertas por la estrategia en la divisa de la cuenta
        current_position_value = self._compute_current_value_of_positions_in_account_currency()

        # Obtenemos el valor que tendría la nueva posición, también en la divisa de la cuenta
        position_type = 0 if sizing_event.signal == "BUY" else 1 # 0 for BUY, 1 for SELL
        new_position_value = self._compute_value_of_position_in_account_currency(sizing_event.symbol, sizing_event.volume, position_type)
        
        # Obtenemos el nuevo volumen de la operacion que queremos ejecutar después de pasar por el risk manager
        new_volume = self.risk_management_method.assess_order(sizing_event, current_position_value, new_position_value)

        # Evaluamos el nuevo volumen
        if new_volume > 0.0:
            # colocar el order event a la cola de eventos
            self._create_and_put_order_event(sizing_event, new_volume)
