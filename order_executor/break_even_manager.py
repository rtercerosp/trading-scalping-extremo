# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from typing import Dict
from utils.utils import Utils
from platform_connector.platform_connector import PlatformConnector
from data_provider.data_provider import DataProvider
from notifications.notifications import NotificationService
from order_executor.order_executor import OrderExecutor
from events.events import SignalType
import MetaTrader5 as mt5
import time
import logging

logger = logging.getLogger(__name__)


class BreakEvenManager:
    """
    V10_ZERO_LOSS_SCALPING BreakEven Manager.

    - Moves SL to entry + buffer when position reaches 50% of projected TP.
    - Pre-breakeven SL is capped to initial SL (no improvement before trigger).
    - Reverse protection: if price retraces 30% from breakeven trigger level, closes position.
    - Gap protection: blocks breakeven move if last bar gap exceeds threshold.
    - Aggressive trailing after breakeven with tighter offset.
    - Logs every candidate event for auditability.
    """

    def __init__(self, data_provider: DataProvider, order_executor: OrderExecutor, notification_service: NotificationService, connector: PlatformConnector, trading_brain=None):
        self.data_provider = data_provider
        self.order_executor = order_executor
        self.notification_service = notification_service
        self.connector = connector
        self.trading_brain = trading_brain

        self.positions_to_monitor: Dict[int, Dict] = {}
        self._trailing_activation_pct: float = 0.003
        self._trailing_offset_pct: float = 0.002

    def _get_zero_loss_params(self, symbol: str) -> dict:
        defaults = {
            "break_even_trigger_pct": 0.50,
            "break_even_buffer_points": 2,
            "reverse_protection_pct": 0.30,
            "gap_protection_pct": 0.003,
            "pre_breakeven_max_sl_improvement_pct": 0.25,
            "trailing_aggressive_activation_pct": 0.003,
            "trailing_aggressive_offset_pct": 0.0015,
            "compounding_volume_multiplier": 2.0,
            "compounding_min_equity": 5000.0,
            "spread_max_points_multiplier": 1.5,
            "min_broker_coverage_points": 2,
            "max_volume_per_candle_ratio": 0.05,
        }
        if self.trading_brain and hasattr(self.trading_brain, 'get_zero_loss_params'):
            params = self.trading_brain.get_zero_loss_params(symbol)
            if params:
                defaults.update(params)
        return defaults

    def _get_trailing_params(self, symbol: str) -> tuple:
        if self.trading_brain and hasattr(self.trading_brain, 'get_extreme_scalping_params'):
            params = self.trading_brain.get_extreme_scalping_params(symbol)
            if params.get("enabled", True):
                return params.get("trailing_activation_pct", self._trailing_activation_pct), params.get("trailing_offset_pct", self._trailing_offset_pct)
        return self._trailing_activation_pct, self._trailing_offset_pct

    def add_position_to_monitor(self, position_ticket: int, symbol: str, entry_price: float, initial_tp: float, signal_type: SignalType, initial_sl: float = 0.0) -> None:
        if initial_tp <= 0:
            return

        symbol_info = self.connector.get_symbol_info(symbol)
        point = getattr(symbol_info, 'point', 0.0001) if symbol_info else 0.0001
        params = self._get_zero_loss_params(symbol)
        buffer_points = params.get("break_even_buffer_points", 2)
        buffer = max(buffer_points * point, point)

        self.positions_to_monitor[position_ticket] = {
            'symbol': symbol,
            'entry_price': entry_price,
            'initial_sl': initial_sl if initial_sl != 0.0 else entry_price,
            'initial_tp': initial_tp,
            'signal_type': signal_type,
            'current_sl': initial_sl if initial_sl != 0.0 else entry_price,
            'sl_moved_to_breakeven': False,
            'breakeven_triggered': False,
            'breakeven_trigger_price': 0.0,
            'reverse_protection_triggered': False,
            'last_gap': 0.0,
            '_last_log_ts': 0.0,
            '_zero_loss_params': params,
        }

        print(f"{Utils.dateprint()} - BREAK EVEN MGR: Posición {position_ticket} ({symbol}) añadida para monitoreo V10. TP: {initial_tp}, SL inicial: {initial_sl}")

    def resume_open_positions(self, magic_number: int) -> None:
        positions = self.connector.get_positions() or ()
        resumed = 0
        for position in positions:
            if position.magic != magic_number:
                continue
            if position.ticket in self.positions_to_monitor:
                continue

            symbol = position.symbol
            signal_type = SignalType.BUY if position.type == mt5.ORDER_TYPE_BUY else SignalType.SELL
            entry_price = position.price_open
            current_tp = position.tp
            current_sl = position.sl

            self.add_position_to_monitor(
                position_ticket=position.ticket,
                symbol=symbol,
                entry_price=entry_price,
                initial_tp=current_tp,
                signal_type=signal_type,
                initial_sl=current_sl,
            )
            resumed += 1

        if resumed > 0:
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Reanudados {resumed} posiciones abiertas para monitoreo V10.")
        else:
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: No hay posiciones abiertas para reanudar.")

    def _detect_gap(self, symbol: str, current_price: float, signal_type: SignalType) -> float:
        bars = self.data_provider.get_latest_closed_bars(symbol, "1min", 5)
        if bars is None or bars.empty or len(bars) < 2:
            return 0.0
        last_open = bars['open'].iloc[-1]
        prev_close = bars['close'].iloc[-2]
        if last_open <= 0 or prev_close <= 0:
            return 0.0
        gap = abs(last_open - prev_close) / prev_close
        return gap

    def check_for_tp_hit_and_move_sl(self) -> None:
        tickets_to_remove = []
        current_open_positions = self.connector.get_positions() or ()
        current_open_position_tickets = {pos.ticket for pos in current_open_positions}

        for position_ticket, details in list(self.positions_to_monitor.items()):
            if position_ticket not in current_open_position_tickets:
                tickets_to_remove.append(position_ticket)
                continue

            if details['sl_moved_to_breakeven']:
                continue

            symbol = details['symbol']
            entry_price = details['entry_price']
            initial_tp = details['initial_tp']
            initial_sl = details['initial_sl']
            signal_type = details['signal_type']
            params = details.get('_zero_loss_params', {})

            latest_tick = self.data_provider.get_latest_tick(symbol)
            if not latest_tick:
                continue

            current_price = latest_tick['bid'] if signal_type == SignalType.SELL else latest_tick['ask']

            symbol_info = self.connector.get_symbol_info(symbol)
            point = getattr(symbol_info, 'point', None) if symbol_info else None
            if not point or point <= 0:
                point = 0.0001

            gap_protection_pct = params.get("gap_protection_pct", 0.003)
            gap = self._detect_gap(symbol, current_price, signal_type)
            details['last_gap'] = gap
            if gap > gap_protection_pct:
                now = time.time()
                last_log_ts = details.get('_last_log_ts', 0.0)
                if now - last_log_ts > 10:
                    print(f"{Utils.dateprint()} - BREAK EVEN MGR: GAP PROTECTION V10 activado para {symbol} ticket={position_ticket} gap={gap:.4f}")
                    details['_last_log_ts'] = now
                continue

            dist_to_tp1 = None
            dist_to_sl = None
            try:
                if signal_type == SignalType.BUY:
                    dist_to_tp1 = (initial_tp - current_price) / point
                    dist_to_sl = (current_price - entry_price) / point
                else:
                    dist_to_tp1 = (current_price - initial_tp) / point
                    dist_to_sl = (entry_price - current_price) / point
            except Exception as e:
                print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error calculando distancias para {symbol} ticket={position_ticket}: {e}")

            now = time.time()
            last_log_ts = details.get('_last_log_ts', 0.0)
            if dist_to_tp1 is not None and dist_to_sl is not None:
                if abs(dist_to_tp1) > 5000 or abs(dist_to_sl) > 5000:
                    if now - last_log_ts > 300:
                        print(f"{Utils.dateprint()} - BREAK EVEN MGR: {symbol} ticket={position_ticket} type={signal_type} TP IRREAL detectado dist_to_tp1={dist_to_tp1:.1f}pts dist_to_sl={dist_to_sl:.1f}pts - No se monitoreará más")
                        details['_last_log_ts'] = now
                    tickets_to_remove.append(position_ticket)
                    continue

                if now - last_log_ts > 5:
                    print(f"{Utils.dateprint()} - BREAK EVEN MGR: {symbol} ticket={position_ticket} type={signal_type} current={current_price} tp={initial_tp} dist_to_tp={dist_to_tp1:.1f}pts dist_to_sl={dist_to_sl:.1f}pts gap={gap:.4f}")
                    details['_last_log_ts'] = now

            breakeven_trigger_pct = params.get("break_even_trigger_pct", 0.50)
            if initial_tp > 0:
                total_tp_distance = abs(initial_tp - entry_price)
                if total_tp_distance > 0:
                    breakeven_trigger_distance = total_tp_distance * breakeven_trigger_pct
                    breakeven_trigger_price = entry_price + breakeven_trigger_distance if signal_type == SignalType.BUY else entry_price - breakeven_trigger_distance
                    details['breakeven_trigger_price'] = breakeven_trigger_price

                    breakeven_hit = (signal_type == SignalType.BUY and current_price >= breakeven_trigger_price) or (signal_type == SignalType.SELL and current_price <= breakeven_trigger_price)
                    if breakeven_hit and not details.get('breakeven_triggered'):
                        details['breakeven_triggered'] = True
                        print(f"{Utils.dateprint()} - BREAK EVEN MGR: BREAK EVEN TRIGGER V10 alcanzado para {symbol} ticket={position_ticket} current={current_price} trigger={breakeven_trigger_price} pct={breakeven_trigger_pct:.0%}")

                        buffer_points = params.get("break_even_buffer_points", 2)
                        buffer = max(buffer_points * point, point)
                        new_sl = entry_price + buffer if signal_type == SignalType.BUY else entry_price - buffer
                        if signal_type == SignalType.BUY and new_sl >= current_price - buffer:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: SL de breakeven {new_sl} arriba del precio actual {current_price} para BUY {symbol}. Se salta el modify.")
                        elif signal_type == SignalType.SELL and new_sl <= current_price + buffer:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: SL de breakeven {new_sl} abajo del precio actual {current_price} para SELL {symbol}. Se salta el modify.")
                        else:
                            try:
                                self.order_executor.modify_position_sl(position_ticket, new_sl)
                                details['current_sl'] = new_sl
                                details['sl_moved_to_breakeven'] = True
                                message = f"BREAK EVEN V10 activado en {position_ticket}: SL movido a {new_sl} (entry {entry_price} + buffer {buffer})"
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                                self.notification_service.send_notification(
                                    title=f"🛡️ BREAK-EVEN V10 - {symbol}",
                                    message=message
                                )
                            except Exception as e:
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error al modificar SL a breakeven para {position_ticket}: {e}")

            if details.get('breakeven_triggered') and not details.get('reverse_protection_triggered'):
                reverse_protection_pct = params.get("reverse_protection_pct", 0.30)
                breakeven_trigger_price = details.get('breakeven_trigger_price', entry_price)
                if signal_type == SignalType.BUY:
                    reverse_trigger = breakeven_trigger_price * (1.0 - reverse_protection_pct)
                    if current_price <= reverse_trigger:
                        details['reverse_protection_triggered'] = True
                        try:
                            self.order_executor.close_position_by_ticket(position_ticket, exit_reason="REVERSE_PROTECTION")
                            message = f"REVERSE PROTECTION V10: cerrada {position_ticket} por retroceso {reverse_protection_pct:.0%} desde break-even trigger"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛑 REVERSE PROTECTION - {symbol}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error cerrando posición por reverse protection {position_ticket}: {e}")
                else:
                    reverse_trigger = breakeven_trigger_price * (1.0 + reverse_protection_pct)
                    if current_price >= reverse_trigger:
                        details['reverse_protection_triggered'] = True
                        try:
                            self.order_executor.close_position_by_ticket(position_ticket, exit_reason="REVERSE_PROTECTION")
                            message = f"REVERSE PROTECTION V10: cerrada {position_ticket} por retroceso {reverse_protection_pct:.0%} desde break-even trigger"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛑 REVERSE PROTECTION - {symbol}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error cerrando posición por reverse protection {position_ticket}: {e}")

            if details.get('breakeven_triggered') and not details.get('reverse_protection_triggered'):
                trailing_activation_pct, trailing_offset_pct = self._get_trailing_params(symbol)
                aggressive_activation = params.get("trailing_aggressive_activation_pct", 0.003)
                aggressive_offset = params.get("trailing_aggressive_offset_pct", 0.0015)
                profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0
                if signal_type == SignalType.SELL:
                    profit_pct = -profit_pct

                if profit_pct >= aggressive_activation:
                    if signal_type == SignalType.BUY:
                        trailing_sl = current_price * (1.0 - aggressive_offset)
                        new_sl = max(details.get('current_sl', entry_price), trailing_sl)
                        if new_sl < current_price - buffer:
                            try:
                                self.order_executor.modify_position_sl(position_ticket, new_sl)
                                details['current_sl'] = new_sl
                                message = f"TRAILING AGRESIVO V10 activado en {position_ticket}: SL={new_sl}"
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                                self.notification_service.send_notification(
                                    title=f"📈 TRAILING AGRESIVO - {symbol}",
                                    message=message
                                )
                            except Exception as e:
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error al modificar SL agresivo de posición {position_ticket}: {e}")
                    else:
                        trailing_sl = current_price * (1.0 + aggressive_offset)
                        new_sl = min(details.get('current_sl', entry_price), trailing_sl)
                        if new_sl > current_price + buffer:
                            try:
                                self.order_executor.modify_position_sl(position_ticket, new_sl)
                                details['current_sl'] = new_sl
                                message = f"TRAILING AGRESIVO V10 activado en {position_ticket}: SL={new_sl}"
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                                self.notification_service.send_notification(
                                    title=f"📉 TRAILING AGRESIVO - {symbol}",
                                    message=message
                                )
                            except Exception as e:
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error al modificar SL agresivo de posición {position_ticket}: {e}")

        for ticket in tickets_to_remove:
            if ticket in self.positions_to_monitor:
                del self.positions_to_monitor[ticket]
