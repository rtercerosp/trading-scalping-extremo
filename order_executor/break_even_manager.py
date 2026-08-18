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
import config

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
        self._last_sl_update_ts: Dict[int, float] = {}
        self._sl_update_throttle_seconds: float = 1.0

    def _get_zero_loss_params(self, symbol: str) -> dict:
        from utils.symbol_utils import normalize_symbol
        symbol_key = normalize_symbol(symbol)
        defaults = {
            "break_even_trigger_pct": getattr(config, "V10_BREAK_EVEN_TRIGGER_PCT", 0.40),
            "break_even_min_trigger_points": getattr(config, "V10_BREAK_EVEN_MIN_TRIGGER_POINTS", {}).get(symbol_key, 0),
            "break_even_max_trigger_points": getattr(config, "V10_BREAK_EVEN_MAX_TRIGGER_POINTS", {}).get(symbol_key, 0),
            "break_even_buffer_points": 2,
            "broker_cost_coverage": getattr(config, "V10_BROKER_COST_COVERAGE", {}).get(symbol_key, {"spread_points": 0, "commission_per_lot": 0.0, "min_profit_points": 0}),
            "reverse_protection_pct": getattr(config, "V10_REVERSE_PROTECTION_PCT", 0.25),
            "gap_protection_pct": getattr(config, "V10_GAP_PROTECTION_PCT", 0.003),
            "pre_breakeven_max_sl_improvement_pct": getattr(config, "V10_PRE_BREAK_EVEN_MAX_SL_IMPROVEMENT_PCT", 0.15),
            "trailing_aggressive_activation_pct": getattr(config, "V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT", 0.003),
            "trailing_aggressive_offset_points": getattr(config, "V10_TRAILING_AGGRESSIVE_OFFSET_POINTS", {}).get(symbol_key, 20),
            "compounding_volume_multiplier": getattr(config, "V10_COMPOUNDING_VOLUME_MULTIPLIER", 2.0),
            "compounding_min_equity": getattr(config, "V10_COMPOUNDING_MIN_EQUITY", 5000.0),
            "spread_max_points_multiplier": getattr(config, "V10_SPREAD_MAX_POINTS_MULTIPLIER", 1.5),
            "min_broker_coverage_points": getattr(config, "V10_MIN_BROKER_COVERAGE_POINTS", 2),
            "max_volume_per_candle_ratio": getattr(config, "V10_MAX_VOLUME_PER_CANDLE_RATIO", 0.05),
        }
        if symbol_key == "ETHUSD":
            defaults["reverse_protection_pct"] = 0.35
            defaults["trailing_aggressive_activation_pct"] = 0.002
            defaults["break_even_buffer_points"] = 3
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

    def _calculate_breakeven_sl(self, symbol: str, entry_price: float, signal_type: SignalType, volume: float, point: float) -> float:
        params = self._get_zero_loss_params(symbol)
        broker_cost = params.get("broker_cost_coverage", {})
        spread_pts = broker_cost.get("spread_points", 0)
        commission_per_lot = broker_cost.get("commission_per_lot", 0.0)
        min_profit_pts = broker_cost.get("min_profit_points", 0)
        buffer_pts = params.get("break_even_buffer_points", 2)
        
        total_cost_pts = spread_pts + min_profit_pts + buffer_pts
        
        if commission_per_lot > 0 and volume > 0:
            symbol_info = self.connector.get_symbol_info(symbol)
            if symbol_info:
                tick_value = getattr(symbol_info, 'trade_tick_value', 0.0)
                if tick_value > 0:
                    commission_pts = (commission_per_lot * volume) / (tick_value * volume)
                    total_cost_pts += commission_pts
        
        if signal_type == SignalType.BUY:
            return entry_price + (total_cost_pts * point)
        else:
            return entry_price - (total_cost_pts * point)

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
            'pre_breakeven_active': False,
            'last_gap': 0.0,
            '_last_log_ts': 0.0,
            '_zero_loss_params': params,
            'max_profit_reached': 0.0,
            'partial_tp_taken': False,
        }

        print(f"{Utils.dateprint()} - BREAK EVEN MGR: Posición {position_ticket} ({symbol}) añadida para monitoreo V10 ZERO LOSS. TP: {initial_tp}, SL inicial: {initial_sl}")

    def _can_update_sl(self, position_ticket: int) -> bool:
        now = time.time()
        last_ts = self._last_sl_update_ts.get(position_ticket, 0.0)
        if now - last_ts < self._sl_update_throttle_seconds:
            return False
        self._last_sl_update_ts[position_ticket] = now
        return True

    def _apply_sl_update(self, position_ticket: int, new_sl: float) -> bool:
        if not self._can_update_sl(position_ticket):
            return False
        try:
            self.order_executor.modify_position_sl(position_ticket, new_sl)
            return True
        except Exception:
            return False

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
            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Reanudados {resumed} posiciones abiertas para monitoreo V10 ZERO LOSS.")
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

            symbol = details['symbol']
            entry_price = details['entry_price']
            initial_tp = details['initial_tp']
            initial_sl = details['initial_sl']
            signal_type = details['signal_type']
            params = details.get('_zero_loss_params', {})
            current_sl = details.get('current_sl', initial_sl)

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
                print(f"{Utils.dateprint()} - BREAK EVEN MGR: GAP PROTECTION V10 activado para {symbol} ticket={position_ticket} gap={gap:.4f}")
                continue

            try:
                if signal_type == SignalType.BUY:
                    dist_to_tp = (initial_tp - current_price) / point
                    dist_to_entry = (current_price - entry_price) / point
                else:
                    dist_to_tp = (current_price - initial_tp) / point
                    dist_to_entry = (entry_price - current_price) / point
            except Exception as e:
                print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error calculando distancias para {symbol} ticket={position_ticket}: {e}")
                continue

            if abs(dist_to_tp) > 5000 or abs(dist_to_entry) > 5000:
                tickets_to_remove.append(position_ticket)
                continue

            # Track max profit reached for reverse protection AFTER breakeven
            current_profit_points = dist_to_entry
            if signal_type == SignalType.SELL:
                current_profit_points = -current_profit_points
            max_profit_reached = details.get('max_profit_reached', 0.0)
            if current_profit_points > max_profit_reached:
                details['max_profit_reached'] = current_profit_points
                max_profit_reached = current_profit_points

            # Reverse protection solo DESPUÉS de break-even: close when price retraces 30% from breakeven trigger
            if details.get('breakeven_triggered') and not details.get('reverse_protection_triggered'):
                reverse_protection_pct = params.get("reverse_protection_pct", 0.30)
                breakeven_trigger_price = details.get('breakeven_trigger_price', entry_price)
                if signal_type == SignalType.BUY:
                    reverse_trigger = breakeven_trigger_price - (breakeven_trigger_price - entry_price) * reverse_protection_pct
                    if current_price <= reverse_trigger:
                        details['reverse_protection_triggered'] = True
                        try:
                            self.order_executor.close_position_by_ticket(position_ticket, exit_reason="REVERSE_PROTECTION")
                            message = f"REVERSE PROTECTION V10: cerrada {position_ticket} por retroceso {reverse_protection_pct:.0%} desde breakeven (max profit {max_profit_reached:.1f} pts)"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛑 REVERSE PROTECTION - {symbol}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error cerrando posición por reverse protection {position_ticket}: {e}")
                        continue
                else:
                    reverse_trigger = breakeven_trigger_price + (entry_price - breakeven_trigger_price) * reverse_protection_pct
                    if current_price >= reverse_trigger:
                        details['reverse_protection_triggered'] = True
                        try:
                            self.order_executor.close_position_by_ticket(position_ticket, exit_reason="REVERSE_PROTECTION")
                            message = f"REVERSE PROTECTION V10: cerrada {position_ticket} por retroceso {reverse_protection_pct:.0%} desde breakeven (max profit {max_profit_reached:.1f} pts)"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛑 REVERSE PROTECTION - {symbol}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error cerrando posición por reverse protection {position_ticket}: {e}")
                        continue

            breakeven_trigger_pct = params.get("break_even_trigger_pct", 0.40)
            min_trigger_points = params.get("break_even_min_trigger_points", 0)
            max_trigger_points = params.get("break_even_max_trigger_points", 0)
            if initial_tp > 0:
                total_tp_distance = abs(initial_tp - entry_price)
                if total_tp_distance > 0:
                    trigger_distance_pct = total_tp_distance * breakeven_trigger_pct
                    min_trigger_distance = min_trigger_points * point if min_trigger_points > 0 else 0
                    if min_trigger_distance > 0:
                        breakeven_trigger_distance = max(trigger_distance_pct, min_trigger_distance)
                    else:
                        breakeven_trigger_distance = trigger_distance_pct
                    if max_trigger_points > 0:
                        max_trigger_distance = max_trigger_points * point
                        breakeven_trigger_distance = min(breakeven_trigger_distance, max_trigger_distance)
                    
                    breakeven_trigger_price = entry_price + breakeven_trigger_distance if signal_type == SignalType.BUY else entry_price - breakeven_trigger_distance
                    details['breakeven_trigger_price'] = breakeven_trigger_price

                    # Log detallado cada 10s
                    now = time.time()
                    last_log_ts = details.get('_last_log_ts', 0.0)
                    if now - last_log_ts > 10:
                        print(f"{Utils.dateprint()} - BREAK EVEN MGR: {symbol} #{position_ticket} entry={entry_price:.5f} tp={initial_tp:.5f} sl={initial_sl:.5f} current={current_price:.5f} dist_to_tp={dist_to_tp:.1f}pts dist_to_entry={dist_to_entry:.1f}pts trigger_dist={breakeven_trigger_distance/point:.1f}pts trigger_price={breakeven_trigger_price:.5f} triggered={details.get('breakeven_triggered', False)}")
                        details['_last_log_ts'] = now

                    breakeven_hit = (signal_type == SignalType.BUY and current_price >= breakeven_trigger_price) or (signal_type == SignalType.SELL and current_price <= breakeven_trigger_price)
                    if breakeven_hit and not details.get('breakeven_triggered'):
                        details['breakeven_triggered'] = True
                        position = next((p for p in current_open_positions if p.ticket == position_ticket), None)
                        volume = position.volume if position else 0.01
                        target_sl = self._calculate_breakeven_sl(symbol, entry_price, signal_type, volume, point)
                        
                        if signal_type == SignalType.BUY:
                            if target_sl >= current_price:
                                new_sl = current_price - (params.get("break_even_buffer_points", 2) * point)
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: SL objetivo {target_sl} >= precio actual {current_price} para BUY {symbol}. Ajustando a {new_sl} (micro-profit lock)")
                            else:
                                new_sl = target_sl
                        else:
                            if target_sl <= current_price:
                                new_sl = current_price + (params.get("break_even_buffer_points", 2) * point)
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: SL objetivo {target_sl} <= precio actual {current_price} para SELL {symbol}. Ajustando a {new_sl} (micro-profit lock)")
                            else:
                                new_sl = target_sl
                        
                        try:
                            self.order_executor.modify_position_sl(position_ticket, new_sl)
                            details['current_sl'] = new_sl
                            details['sl_moved_to_breakeven'] = True
                            message = f"BREAK EVEN V10 ZERO LOSS activado en {position_ticket}: SL movido a {new_sl} (entry {entry_price} + costos broker, trigger@{breakeven_trigger_pct:.0%} TP)"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛡️ ZERO LOSS BREAK-EVEN - {symbol}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error al modificar SL a breakeven para {position_ticket}: {e}")

                    if not details.get('breakeven_triggered') and dist_to_entry > 0:
                        pre_breakeven_pct = params.get("pre_breakeven_max_sl_improvement_pct", 0.20)
                        max_improvement = abs(initial_sl - entry_price) * pre_breakeven_pct if initial_sl != entry_price else 0
                        if max_improvement > 0:
                            if signal_type == SignalType.BUY:
                                improved_sl = max(current_sl, entry_price - max_improvement)
                                if improved_sl > current_sl:
                                    try:
                                        self.order_executor.modify_position_sl(position_ticket, improved_sl)
                                        details['current_sl'] = improved_sl
                                        details['pre_breakeven_active'] = True
                                    except Exception:
                                        pass
                            else:
                                improved_sl = min(current_sl, entry_price + max_improvement)
                                if improved_sl < current_sl:
                                    try:
                                        self.order_executor.modify_position_sl(position_ticket, improved_sl)
                                        details['current_sl'] = improved_sl
                                        details['pre_breakeven_active'] = True
                                    except Exception:
                                        pass

            if details.get('breakeven_triggered') and not details.get('reverse_protection_triggered'):
                reverse_protection_pct = params.get("reverse_protection_pct", 0.25)
                breakeven_trigger_price = details.get('breakeven_trigger_price', entry_price)
                if signal_type == SignalType.BUY:
                    reverse_trigger = breakeven_trigger_price - (breakeven_trigger_price - entry_price) * reverse_protection_pct
                    if current_price <= reverse_trigger:
                        details['reverse_protection_triggered'] = True
                        try:
                            self.order_executor.close_position_by_ticket(position_ticket, exit_reason="REVERSE_PROTECTION")
                            message = f"REVERSE PROTECTION V10: cerrada {position_ticket} por retroceso {reverse_protection_pct:.0%} desde break-even"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛑 REVERSE PROTECTION - {symbol}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error cerrando posición por reverse protection {position_ticket}: {e}")
                else:
                    reverse_trigger = breakeven_trigger_price + (entry_price - breakeven_trigger_price) * reverse_protection_pct
                    if current_price >= reverse_trigger:
                        details['reverse_protection_triggered'] = True
                        try:
                            self.order_executor.close_position_by_ticket(position_ticket, exit_reason="REVERSE_PROTECTION")
                            message = f"REVERSE PROTECTION V10: cerrada {position_ticket} por retroceso {reverse_protection_pct:.0%} desde break-even"
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                            self.notification_service.send_notification(
                                title=f"🛑 REVERSE PROTECTION - {symbol}",
                                message=message
                            )
                        except Exception as e:
                            print(f"{Utils.dateprint()} - BREAK EVEN MGR: Error cerrando posición por reverse protection {position_ticket}: {e}")

            if details.get('breakeven_triggered') and not details.get('reverse_protection_triggered'):
                aggressive_activation = params.get("trailing_aggressive_activation_pct", 0.003)
                aggressive_offset_points = params.get("trailing_aggressive_offset_points", 20)
                profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0
                if signal_type == SignalType.SELL:
                    profit_pct = -profit_pct

                if profit_pct >= aggressive_activation:
                    buffer_points = params.get("break_even_buffer_points", 2)
                    buffer = max(buffer_points * point, point)
                    offset = aggressive_offset_points * point
                    if signal_type == SignalType.BUY:
                        trailing_sl = current_price - offset
                        new_sl = max(details.get('current_sl', entry_price), trailing_sl)
                        if new_sl < current_price - buffer:
                            if self._apply_sl_update(position_ticket, new_sl):
                                details['current_sl'] = new_sl
                                message = f"TRAILING AGRESIVO V10 activado en {position_ticket}: SL={new_sl}"
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                                self.notification_service.send_notification(
                                    title=f"📈 TRAILING AGRESIVO - {symbol}",
                                    message=message
                                )
                    else:
                        trailing_sl = current_price + offset
                        new_sl = min(details.get('current_sl', entry_price), trailing_sl)
                        if new_sl > current_price + buffer:
                            if self._apply_sl_update(position_ticket, new_sl):
                                details['current_sl'] = new_sl
                                message = f"TRAILING AGRESIVO V10 activado en {position_ticket}: SL={new_sl}"
                                print(f"{Utils.dateprint()} - BREAK EVEN MGR: {message}")
                                self.notification_service.send_notification(
                                    title=f"📉 TRAILING AGRESIVO - {symbol}",
                                    message=message
                                )

        for ticket in tickets_to_remove:
            if ticket in self.positions_to_monitor:
                del self.positions_to_monitor[ticket]
