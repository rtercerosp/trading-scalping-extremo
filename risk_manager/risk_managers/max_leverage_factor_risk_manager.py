# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from utils.utils import Utils
from platform_connector.platform_connector import PlatformConnector
from events.events import SizingEvent
from ..interfaces.risk_manager_interface import IRiskManager
from ..properties.risk_manager_properties import MaxLeverageFactorRiskProps
import MetaTrader5 as mt5
from notifications.notifications import NotificationService
import sys

class MaxLeverageFactorRiskManager(IRiskManager):

    def __init__(self, properties: MaxLeverageFactorRiskProps, notification_service: NotificationService, connector: PlatformConnector):
        """
        Initializes a MaxLeverageFactorRiskManager object.

        Args:
            properties (MaxLeverageFactorRiskProps): The properties object containing the maximum leverage factor.
            notification_service (NotificationService): The notification service instance.
            connector (PlatformConnector): The platform connector instance.
        """
        self.max_leverage_factor = properties.max_leverage_factor
        self.NOTIFICATIONS = notification_service
        self.connector = connector

    def _compute_leverage_factor(self, account_value_acc_ccy: float) -> float:
        """
        Computes the leverage factor based on the account value and equity.

        Args:
            account_value_acc_ccy (float): The account value in the account currency.

        Returns:
            float: The computed leverage factor.
        """

        account_equity = self.connector.get_account_info().equity

        if account_equity <= 0:
            return sys.float_info.max
        else:
            return account_value_acc_ccy / account_equity

    def _compute_adjusted_volume(self, sizing_event: SizingEvent,
                                                                   current_positions_value_acc_ccy: float,
                                                                   new_position_value_acc_ccy: float) -> float:
        account_info = self.connector.get_account_info()
        account_equity = account_info.equity if account_info else 0.0
        
        symbol_info = self.connector.get_symbol_info(sizing_event.symbol)
        if symbol_info and account_equity > 0:
            max_position_value = account_equity * self.max_leverage_factor
            if new_position_value_acc_ccy > max_position_value:
                volume_step = getattr(symbol_info, 'volume_step', 0.01) or 0.01
                max_volume_by_equity = max_position_value / new_position_value_acc_ccy * sizing_event.volume
                max_volume_by_equity = max(symbol_info.volume_min, round(max_volume_by_equity / volume_step) * volume_step)
                if max_volume_by_equity < sizing_event.volume:
                    message = f"RISK MGMT: Leverage cap exceeded. Max position value {max_position_value:.2f} {account_info.currency}. Adjusting volume from {sizing_event.volume:.2f} to {max_volume_by_equity:.2f}"
                    print(f"{Utils.dateprint()} - {message}")
                    self.NOTIFICATIONS.send_notification(
                        title=f"⚠️ RIESGO AJUSTADO - {sizing_event.symbol}",
                        message=message
                    )
                    return max_volume_by_equity

        new_account_value = current_positions_value_acc_ccy + new_position_value_acc_ccy
        new_leverage_factor = self._compute_leverage_factor(new_account_value)

        if abs(new_leverage_factor) <= self.max_leverage_factor:
            return sizing_event.volume

        adjusted_value = current_positions_value_acc_ccy + (new_position_value_acc_ccy * (self.max_leverage_factor / abs(new_leverage_factor)))
        adjusted_volume = sizing_event.volume * (self.max_leverage_factor / abs(new_leverage_factor))

        adjusted_leverage_factor = self._compute_leverage_factor(adjusted_value)
        if abs(adjusted_leverage_factor) > self.max_leverage_factor:
            adjusted_volume = sizing_event.volume * (self.max_leverage_factor / abs(adjusted_leverage_factor))

        if symbol_info and adjusted_volume < symbol_info.volume_min:
            return 0.0

        message = f"RISK MGMT: Leverage factor {abs(new_leverage_factor):.2f} exceeds max {self.max_leverage_factor}. Adjusting volume from {sizing_event.volume:.2f} to {adjusted_volume:.2f}"
        print(f"{Utils.dateprint()} - {message}")
        self.NOTIFICATIONS.send_notification(
            title=f"⚠️ RIESGO AJUSTADO - {sizing_event.symbol}",
            message=message
        )
        return adjusted_volume

    def assess_order(self, sizing_event: SizingEvent, current_positions_value_acc_ccy: float, new_position_value_acc_ccy: float) -> float:
        """
        Assess the order and determine the adjusted volume based on the maximum leverage factor.

        Args:
            sizing_event (SizingEvent): The sizing event for the order.
            current_positions_value_acc_ccy (float): The current value of all positions in the account currency.
            new_position_value_acc_ccy (float): The value of the new position in the account currency.

        Returns:
            float: The adjusted volume of the order that complies with the maximum leverage factor.
        """
        adjusted_volume = self._compute_adjusted_volume(sizing_event, current_positions_value_acc_ccy, new_position_value_acc_ccy)
        return max(adjusted_volume, 0.0)