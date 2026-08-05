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
        self.linked_positions: Dict[int, int] = {}
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

    def add_position_to_monitor(self, position_ticket: int, symbol: str, entry_price: float, initial_tp: float, signal_type: SignalType, tp1: float = 0.0, tp2: float = 0.0, linked_ticket: int = 0) -> None:
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
            'initial_tp': initial_tp,
            'signal_type': signal_type,
            'tp1': tp1,
            'tp2': tp2,
            'initial_sl': 0.0,
            'sl_moved_to_breakeven': False,
            'breakeven_triggered': False,
            'breakeven_trigger_price': 0.0,
            'reverse_protection_triggered': False,
            'tp1_hit': False,
            'volume': 0.0,
            'last_gap': 0.0,
            'last_close_time': 0.0,
            '_last_log_ts': 0.0,
            '_zero_loss_params': params,
        }

        if linked_ticket > 0:
            self.linked_positions[position_ticket] = linked_ticket
            if linked_ticket not in self.linked_positions:
                self.linked_positions[linked_ticket] = position_ticket
        else:
            for existing_ticket, existing_details in list(self.positions_to_monitor.items()):
                if existing_ticket != position_ticket and existing_details['symbol'] == symbol and existing_ticket not in self.linked_positions:
                    self.linked_positions[existing_ticket] = position_ticket
                    self.linked_positions[position_ticket] = existing_ticket
                    print(f"{Utils.dateprint()} - BREAK EVEN MGR: Vinculando posiciones {existing_ticket} y {position_ticket} para {symbol}")
                    break

        print(f"{Utils.dateprint()} - BREAK EVEN MGR: Posición {position_ticket} ({symbol}) añadida para monitoreo V10. TP1: {tp1}, TP2: {tp2}, Linked: {linked_ticket}")

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

            tp1 = current_tp
            tp2 = current_tp
            if current_tp > 0:
                distance = abs(current_tp - entry_price)
                if signal_type == SignalType.BUY:
                    tp1 = entry_price + distance * 0.618
                    tp2 = current_tp
                else:
                    tp1 = entry_price - distance * 0.618
                    tp2 = current_tp

            self.add_position_to_monitor(
                position_ticket=position.ticket,
                symbol=symbol,
                entry_price=entry_price,
                initial_tp=current_tp,
                signal_type=signal_type,
                tp1=tp1,
                tp2=tp2,
            )
            resumed += 1

        if resumed > 0:
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Reanudados {resumed} posiciones abiertas para monitoreo V10.")
        else:
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: No hay posiciones abiertas para reanudar.")

    def _move_linked_position_to_breakeven(self, position_ticket: int) -> None:
        linked_ticket = self.linked_positions.get(position_ticket)
        if not linked_ticket or linked_ticket not in self.positions_to_monitor:
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: No hay posición vinculada válida para {position_ticket}. Se salta el move.")
            return

        linked_details = self.positions_to_monitor[linked_ticket]
        if linked_details.get('sl_moved_to_breakeven'):
            return

        current_open_position_tickets = {pos.ticket for pos in (self.connector.get_positions() or ())}
        if linked_ticket not in current_open_position_tickets:
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: La posición vinculada {linked_ticket} ya está cerrada. No se puede mover SL.")
            linked_details['sl_moved_to_breakeven'] = True
            return

        symbol_info = self.connector.get_symbol_info(linked_details['symbol'])
        stops_level = getattr(symbol_info, 'trade_stops_level', 0) if symbol_info else 0
        point = getattr(symbol_info, 'point', 0.0001) if symbol_info else 0.0001
        buffer = max(stops_level * point, point)
        signal_type = linked_details['signal_type']
        entry_price = linked_details['entry_price']
        last_tick = self.data_provider.get_latest_tick(linked_details['symbol'])
        current_price = None
        if last_tick:
            current_price = last_tick.get("bid") if signal_type == SignalType.SELL else last_tick.get("ask")
        if current_price is None:
            positions = self.connector.get_positions(ticket=linked_ticket)
            if positions:
                current_price = positions[0].price_current

        trailing_activation_pct, trailing_offset_pct = self._get_trailing_params(linked_details['symbol'])
        params = linked_details.get('_zero_loss_params', {})
        aggressive_activation = params.get("trailing_aggressive_activation_pct", 0.003)
        aggressive_offset = params.get("trailing_aggressive_offset_pct", 0.0015)
        reverse_protection_pct = params.get("reverse_protection_pct", 0.30)
        breakeven_trigger_price = linked_details.get('breakeven_trigger_price', entry_price)

        if current_price is not None:
            if signal_type == SignalType.BUY:
                profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0
                if profit_pct >= aggressive_activation and linked_details.get('breakeven_triggered'):
                    trailing_sl = current_price * (1.0 - aggressive_offset)
                    new_sl = max(linked_details.get('sl', entry_price), trailing_sl)
                    if new_sl < current_price - buffer:
                        try:
                            self.order_executor.modify_position_sl(linked_ticket, new_sl)
                            linked_details['sl'] = new_sl
                            message = f"TRAILING AGRESIVO V10 activado en {linked_ticket}: SL={new_sl}"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"📈 TRAILING AGRESIVO - {linked_details['symbol']}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error al modificar SL agresivo de posición {linked_ticket}: {e}")
                    return

                if linked_details.get('breakeven_triggered') and not linked_details.get('reverse_protection_triggered'):
                    reverse_trigger = breakeven_trigger_price * (1.0 - reverse_protection_pct)
                    if current_price <= reverse_trigger:
                        linked_details['reverse_protection_triggered'] = True
                        try:
                            self.order_executor.close_position_by_ticket(linked_ticket, exit_reason="REVERSE_PROTECTION")
                            message = f"REVERSE PROTECTION V10: cerrada {linked_ticket} por retroceso {reverse_protection_pct:.0%} desde break-even trigger"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛑 REVERSE PROTECTION - {linked_details['symbol']}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error cerrando posición por reverse protection {linked_ticket}: {e}")
                        return

                new_sl = entry_price + buffer
                if new_sl > current_price - buffer:
                    print(f"{Utils.dateprint()} - BREAK EVEN MGR: SL de breakeven {new_sl} arriba del precio actual {current_price} para BUY {linked_details['symbol']}. Se salta el modify para evitar invalid stops.")
                    return
            else:
                profit_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0.0
                if profit_pct >= aggressive_activation and linked_details.get('breakeven_triggered'):
                    trailing_sl = current_price * (1.0 + aggressive_offset)
                    new_sl = min(linked_details.get('sl', entry_price), trailing_sl)
                    if new_sl > current_price + buffer:
                        try:
                            self.order_executor.modify_position_sl(linked_ticket, new_sl)
                            linked_details['sl'] = new_sl
                            message = f"TRAILING AGRESIVO V10 activado en {linked_ticket}: SL={new_sl}"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"📉 TRAILING AGRESIVO - {linked_details['symbol']}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error al modificar SL agresivo de posición {linked_ticket}: {e}")
                    return

                if linked_details.get('breakeven_triggered') and not linked_details.get('reverse_protection_triggered'):
                    reverse_trigger = breakeven_trigger_price * (1.0 + reverse_protection_pct)
                    if current_price >= reverse_trigger:
                        linked_details['reverse_protection_triggered'] = True
                        try:
                            self.order_executor.close_position_by_ticket(linked_ticket, exit_reason="REVERSE_PROTECTION")
                            message = f"REVERSE PROTECTION V10: cerrada {linked_ticket} por retroceso {reverse_protection_pct:.0%} desde break-even trigger"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛑 REVERSE PROTECTION - {linked_details['symbol']}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error cerrando posición por reverse protection {linked_ticket}: {e}")
                        return

                new_sl = entry_price - buffer
                if new_sl < current_price + buffer:
                    print(f"{Utils.dateprint()} - BREAK EVEN MGR: SL de breakeven {new_sl} abajo del precio actual {current_price} para SELL {linked_details['symbol']}. Se salta el modify para evitar invalid stops.")
                    return

        try:
            self.order_executor.modify_position_sl(linked_ticket, new_sl)
            linked_details['sl_moved_to_breakeven'] = True
            message = f"TP1 alcanzado en posición {position_ticket}. Moviendo SL de posición vinculada {linked_ticket} a break-even ({new_sl})."
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
            self.notification_service.send_notification(
                title=f"🛡️ BREAK-EVEN VINCULADO - {linked_details['symbol']}",
                message=message
            )
        except Exception as e:
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error al modificar SL de posición {linked_ticket}: {e}")

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
                if details.get('tp1_hit', False):
                    self._move_linked_position_to_breakeven(position_ticket)
                tickets_to_remove.append(position_ticket)
                continue

            if details['sl_moved_to_breakeven']:
                continue

            symbol = details['symbol']
            entry_price = details['entry_price']
            tp1 = details['tp1']
            tp2 = details.get('tp2', 0.0)
            signal_type = details['signal_type']
            initial_tp = details.get('initial_tp', 0.0)
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
                    dist_to_tp1 = (tp1 - current_price) / point
                    dist_to_sl = (current_price - entry_price) / point
                else:
                    dist_to_tp1 = (current_price - tp1) / point
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
                    if position_ticket in self.linked_positions:
                        del self.linked_positions[position_ticket]
                    continue

                if now - last_log_ts > 5:
                    print(f"{Utils.dateprint()} - BREAK EVEN MGR: {symbol} ticket={position_ticket} type={signal_type} current={current_price} tp1={tp1} tp2={tp2} dist_to_tp1={dist_to_tp1:.1f}pts dist_to_sl={dist_to_sl:.1f}pts gap={gap:.4f}")
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

            tp1_hit = False
            if signal_type == SignalType.BUY and current_price >= tp1 and tp1 > 0:
                tp1_hit = True
            elif signal_type == SignalType.SELL and current_price <= tp1 and tp1 > 0:
                tp1_hit = True

            if tp1_hit and not details['tp1_hit']:
                details['tp1_hit'] = True
                is_tp1_position = (initial_tp > 0 and abs(initial_tp - tp1) < abs(initial_tp - tp2) if tp2 > 0 else True)

                print(f"{Utils.dateprint()} - BREAK EVEN MGR: TP1 ALCANZADO para {symbol} ticket={position_ticket} current={current_price} tp1={tp1} tp2={tp2} type={signal_type}")

                positions = self.connector.get_positions(ticket=position_ticket)
                if positions:
                    position = positions[0]
                    details['volume'] = position.volume
                    symbol_info = self.connector.get_symbol_info(symbol)
                    close_volume = position.volume
                    if symbol_info:
                        close_volume = round(close_volume / symbol_info.volume_step) * symbol_info.volume_step
                        if close_volume < symbol_info.volume_min:
                            close_volume = symbol_info.volume_min

                    if is_tp1_position and close_volume > 0:
                        try:
                            self.order_executor.close_position_by_ticket(position_ticket, volume=close_volume, exit_reason="TP1")
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error al cerrar posición {position_ticket}: {e}")

                self._move_linked_position_to_breakeven(position_ticket)
                details['sl_moved_to_breakeven'] = True
                message = f"TP1 alcanzado para {symbol}. SL movido a break-even + buffer para posición vinculada."
                print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                self.notification_service.send_notification(
                    title=f"🛡️ BREAK-EVEN - {symbol}",
                    message=message
                )

        for ticket in tickets_to_remove:
            if ticket in self.linked_positions:
                del self.linked_positions[ticket]
            if ticket in self.positions_to_monitor:
                del self.positions_to_monitor[ticket]
