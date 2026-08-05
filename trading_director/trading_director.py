# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from data_provider.data_provider import DataProvider
from signal_generator.interfaces.signal_generator_interface import ISignalGenerator
from position_sizer.position_sizer import PositionSizer
from risk_manager.risk_manager import RiskManager
from order_executor.order_executor import OrderExecutor
from order_executor.break_even_manager import BreakEvenManager
from notifications.notifications import NotificationService
from events.events import DataEvent, SignalEvent, SizingEvent, OrderEvent, ExecutionEvent, PlacedPendingOrderEvent, ReportEvent
from utils.utils import Utils
from utils.symbol_utils import get_asset_category, normalize_symbol
from typing import Dict, Callable
import queue
import time
import logging
from datetime import datetime
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


class TradingDirector():
    
    def __init__(self, events_queue: queue.Queue, data_provider: DataProvider, signal_generator: ISignalGenerator,
                 position_sizer: PositionSizer, break_even_manager: BreakEvenManager, risk_manager: RiskManager, order_executor: OrderExecutor, notification_service: NotificationService,
                 news_protection=None, trading_brain=None, portfolio=None, connector=None):
        self.events_queue = events_queue
        
        self.data_provider = data_provider
        self.signal_generator = signal_generator
        self.position_sizer = position_sizer
        self.break_even_manager = break_even_manager
        self.risk_manager = risk_manager
        self.order_executor = order_executor
        self.order_executor.trading_director = self
        self.notification_service = notification_service
        self.news_protection = news_protection
        self.trading_brain = trading_brain
        self.portfolio = portfolio
        self.connector = connector

        self.continue_trading: bool = True
        self._last_weekend_close_date = None
        self._last_circuit_breaker_reset_date = None
        self._market_status_cache: Dict[str, tuple] = {}
        self._market_status_cache_ttl: float = 2.0
        self._previous_market_open_state: Dict[str, bool] = {}
        self._last_institutional_report_ts: float = 0.0
        self._institutional_report_interval_seconds = 600
        self._last_data_event_ts: float = 0.0
        self._breakeven_check_interval: float = 1.0

        self.event_handler: Dict[str, Callable] = {
            "DATA": self._handle_data_event,
            "SIGNAL": self._handle_signal_event,
            "SIZING": self._handle_sizing_event,
            "ORDER": self._handle_order_event,
            "EXECUTION": self._handle_execution_event,
            "PENDING": self._handle_pending_order_event,
            "NEWS": self._handle_news_event,
            "FVG": self._handle_fvg_event,
            "REPORT": self._handle_report_event,
        }

    def _get_system_local_now(self) -> datetime:
        return datetime.now()

    def _reset_daily_circuit_breaker_if_new_day(self) -> None:
        if self.trading_brain is None:
            return
        now = self._get_system_local_now()
        today = now.date()
        if getattr(self, '_last_circuit_breaker_reset_date', None) != today:
            self._last_circuit_breaker_reset_date = today
            self.trading_brain.reset_daily_circuit_breaker()

    def _get_cached_market_status(self, symbol: str) -> dict:
        now_ts = time.time()
        cached = self._market_status_cache.get(symbol)
        if cached and (now_ts - cached[1]) < self._market_status_cache_ttl:
            return cached[0]

        status = {"open": True, "reason": "unchecked"}
        if self.connector is not None:
            try:
                status = self.connector.get_market_status(symbol) or status
            except Exception as e:
                logger.error("TRADING DIRECTOR: Error obteniendo estado de mercado para %s: %s", symbol, e, exc_info=True)

        self._market_status_cache[symbol] = (status, now_ts)
        return status

    def _is_trading_hours(self, symbol: str, asset_category: str = "forex") -> bool:
        if asset_category == "crypto":
            print(f"{Utils.dateprint()} - TRADING DIRECTOR: {symbol} es crypto, horario permitido")
            return True

        symbol_key = normalize_symbol(symbol)
        market_status = self._get_cached_market_status(symbol_key)
        mt5_says_open = bool(market_status.get("open", True))

        if self.connector is not None:
            if mt5_says_open:
                print(f"{Utils.dateprint()} - TRADING DIRECTOR: MT5 indica mercado abierto para {symbol_key}")
                return True
            if market_status.get("reason") in {"trading_disabled", "not_visible", "symbol_not_found"}:
                print(f"{Utils.dateprint()} - TRADING DIRECTOR: {symbol_key} bloqueado por MT5 reason={market_status.get('reason')}")
                return False

        now = self._get_system_local_now()
        if now.weekday() >= 5:
            print(f"{Utils.dateprint()} - TRADING DIRECTOR: {symbol_key} bloqueado por weekend local={now}")
            return False

        print(f"{Utils.dateprint()} - TRADING DIRECTOR: {symbol_key} permitido por fallback local={now}")
        return True

    def _close_all_open_positions(self, symbol: str | None = None, asset_category: str = "forex") -> None:
        positions = self.order_executor.PORTFOLIO.get_strategy_open_positions()
        closed = 0
        for position in positions:
            symbol_key = normalize_symbol(position.symbol)
            if symbol is not None and symbol_key != normalize_symbol(symbol):
                continue
            if symbol is None:
                position_category = getattr(self.signal_generator, '_get_asset_category', lambda s: "forex")(symbol_key)
                if position_category != asset_category:
                    continue
            try:
                self.order_executor.close_position_by_ticket(position.ticket)
                closed += 1
            except Exception as e:
                print(f"{Utils.dateprint()} - TRADING DIRECTOR: Error cerrando posición {position.ticket}: {e}")
        if closed > 0:
            self.notification_service.send_notification(
                title="🔴 CIERRE POR SUSPENSIÓN DE MERCADO",
                message=f"Se cerraron {closed} posiciones por cierre de mercado."
            )

        if self.portfolio:
            initial_status_message = self.portfolio.get_initial_portfolio_status_message()
            if initial_status_message:
                print(f"{Utils.dateprint()} - {initial_status_message}")
                self.notification_service.send_notification(
                    title="⚠️ AVISO DE PORTFOLIO INICIAL",
                    message=initial_status_message
                )

    def _handle_data_event(self, event: DataEvent):
        symbol_key = normalize_symbol(event.symbol)
        print(f"{Utils.dateprint()} - TRADING DIRECTOR: DataEvent recibido para {event.symbol} (normalizado: {symbol_key})")

        if self.trading_brain:
            cb_active, cb_reason = self.trading_brain.is_circuit_breaker_active()
            if cb_active:
                print(f"{Utils.dateprint()} - TRADING DIRECTOR: Trading detenido por circuit breaker: {cb_reason}")
                return

            trade_state = self.trading_brain.get_symbol_trade_state(symbol_key)
            if not trade_state.get("tradeable", False):
                print(f"{Utils.dateprint()} - TRADING DIRECTOR: {symbol_key} excluido temporalmente - {trade_state.get('reason')}")
                return
            risk_override = trade_state.get("risk_override")
            if risk_override is not None:
                event.risk_pct_override = float(risk_override)

        if self.news_protection:
            in_news_window, news_info = self.news_protection.check_symbol_for_news(symbol_key)
            if in_news_window:
                if self.trading_brain:
                    should_block, decision_info = self.trading_brain.should_block_for_news(symbol_key)
                    if should_block:
                        self.trading_brain.record_news_decision(symbol_key, "BLOCK", decision_info)
                        print(f"{Utils.dateprint()} - NEWS PROTECTION: Omitiendo señal para {event.symbol} - {decision_info.get('reason', news_info)}")
                        return
                    self.trading_brain.record_news_decision(symbol_key, "ALLOW_WITH_CAUTION", decision_info)
                    risk_override = decision_info.get("risk_pct_override")
                    if risk_override:
                        print(f"{Utils.dateprint()} - NEWS PROTECTION: Reduciendo riesgo a {risk_override} para {event.symbol} por noticia: {decision_info.get('news', [])}")
                        try:
                            event.risk_pct_override = float(risk_override)
                        except Exception as e:
                            logger.error("TRADING DIRECTOR: Risk override invalido para %s: %s", event.symbol, e, exc_info=True)
                else:
                    print(f"{Utils.dateprint()} - NEWS PROTECTION: Omitiendo señal para {event.symbol} - {news_info}")
                    return

        asset_category = getattr(self.signal_generator, '_get_asset_category', lambda s: "forex")(symbol_key)
        if not self._is_trading_hours(symbol_key, asset_category):
            return

        self.signal_generator.generate_signal(event)

    def execute(self, max_iterations: int | None = None) -> None:
        iterations = 0
        while self.continue_trading:
            if max_iterations is not None and iterations >= max_iterations:
                break
            try:
                event = self.events_queue.get(block=False)
            except queue.Empty:
                self._reset_daily_circuit_breaker_if_new_day()
                self._check_weekend_closure()
                self._check_market_close_closure()
                self.data_provider.check_for_new_data()

                now_ts = time.time()
                if now_ts - self._last_data_event_ts >= self._breakeven_check_interval:
                    self._last_data_event_ts = now_ts
                    self.break_even_manager.check_for_tp_hit_and_move_sl()

                if self.trading_brain:
                    self.trading_brain.scan_closed_positions(self.connector)
                    self.trading_brain.maybe_run_evaluation(label="periodic")
                    self._maybe_print_institutional_report()
                time.sleep(0.01)
                iterations += 1
                continue

            if event is not None:
                symbol_key = normalize_symbol(getattr(event, 'symbol', ''))
                asset_category = getattr(self.signal_generator, '_get_asset_category', lambda s: "forex")(symbol_key)
                if self._should_process_event_by_priority(symbol_key, asset_category):
                    handler = self.event_handler.get(event.event_type, self._handle_unknown_event)
                    handler(event)
                else:
                    self.events_queue.put(event)
                    time.sleep(0.05)
            else:
                self._handle_none_event(event)

            iterations += 1

        print(f"{Utils.dateprint()} - FIN")

    def _check_weekend_closure(self) -> None:
        now = self._get_system_local_now()
        today = now.date()

        if now.weekday() >= 5:
            if self._last_weekend_close_date != today:
                self._last_weekend_close_date = today
                if self.signal_generator and hasattr(self.signal_generator, "asset_category_map"):
                    for symbol in self.signal_generator.asset_category_map.keys():
                        symbol_key = normalize_symbol(symbol)
                        market_status = self._get_cached_market_status(symbol_key)
                        if bool(market_status.get("open", True)):
                            continue
                        self._close_all_open_positions(symbol=symbol_key)
            return

        self._last_weekend_close_date = None

    def _check_market_close_closure(self) -> None:
        if not self.signal_generator or not hasattr(self.signal_generator, "asset_category_map"):
            return

        symbols_to_check = list(self.signal_generator.asset_category_map.keys())
        symbols_to_close = []

        for symbol in symbols_to_check:
            symbol_key = normalize_symbol(symbol)
            market_status = self._get_cached_market_status(symbol_key)
            is_open_now = bool(market_status.get("open", True))

            if symbol_key not in self._previous_market_open_state:
                self._previous_market_open_state[symbol_key] = is_open_now
                continue

            was_open = self._previous_market_open_state[symbol_key]
            self._previous_market_open_state[symbol_key] = is_open_now

            if was_open and not is_open_now:
                symbols_to_close.append(symbol_key)

        for symbol_key in symbols_to_close:
            self._close_all_open_positions(symbol=symbol_key)

    def _handle_signal_event(self, event: SignalEvent):
        print(f"{Utils.dateprint()} - Recibido SIGNAL EVENT {event.signal} para {event.symbol}")
        symbol_key = normalize_symbol(event.symbol)
        if self.trading_brain and self.trading_brain.is_circuit_breaker_active()[0]:
            print(f"{Utils.dateprint()} - TRADING DIRECTOR: Trading detenido por circuit breaker. Se omite señal para {event.symbol}")
            return
        if self.portfolio and not self.portfolio.can_open_position(symbol_key):
            print(f"{Utils.dateprint()} - TRADING DIRECTOR: Límite de portfolio alcanzado. Se omite señal para {event.symbol}")
            return
        if self._check_opposite_position(symbol_key, event.signal):
            return
        if self.trading_brain and self._check_trade_loss_limit(event):
            return
        self.position_sizer.size_signal(event)

    def _should_process_event_by_priority(self, symbol_key: str, asset_category: str) -> bool:
        if asset_category != "gold":
            try:
                queue_size = self.events_queue.qsize()
                if queue_size > 20:
                    return False
            except Exception:
                pass
        return True

    def _handle_sizing_event(self, event: SizingEvent):
        print(f"{Utils.dateprint()} - Recibido SIZING EVENT con volumen {event.volume} para {event.signal} en {event.symbol}")
        self.risk_manager.assess_order(event)

    def _handle_order_event(self, event: OrderEvent):
        print(f"{Utils.dateprint()} - Recibido ORDER EVENT con volumen {event.volume} para {event.signal} en {event.symbol}")
        self.order_executor.execute_order(event)

    def _handle_execution_event(self, event: ExecutionEvent):
        print(f"{Utils.dateprint()} - Recibido EXECUTION EVENT {event.signal} en {event.symbol} con volumen {event.volume} al precio {event.fill_price}")
        if hasattr(event, 'position_ticket') and event.position_ticket and hasattr(event, 'initial_tp') and event.initial_tp > 0 and hasattr(event, 'initial_sl') and event.initial_sl != event.entry_price:
            if self.connector is not None:
                try:
                    open_positions = self.connector.get_positions(ticket=event.position_ticket)
                    if not open_positions:
                        print(f"{Utils.dateprint()} - TRADING DIRECTOR: Posición {event.position_ticket} ya cerrada, no se agrega a break_even_manager")
                        self._process_execution_or_pending_events(event)
                        if self.trading_brain:
                            self.trading_brain.record_execution(event)
                        return
                except Exception as e:
                    print(f"{Utils.dateprint()} - TRADING DIRECTOR: Error verificando posición {event.position_ticket}: {e}")

            tp1 = getattr(event, 'tp1', 0.0)
            tp2 = getattr(event, 'tp2', 0.0)
            initial_sl = getattr(event, 'initial_sl', 0.0)
            self.break_even_manager.add_position_to_monitor(
                event.position_ticket,
                event.symbol,
                event.entry_price,
                event.initial_tp,
                event.signal,
                tp1=tp1,
                tp2=tp2
            )
            if self.break_even_manager.positions_to_monitor.get(event.position_ticket):
                self.break_even_manager.positions_to_monitor[event.position_ticket]['initial_sl'] = initial_sl
        if self.trading_brain:
            self.trading_brain.record_execution(event)
        self._process_execution_or_pending_events(event)

    def _handle_pending_order_event(self, event: PlacedPendingOrderEvent):
        print(f"{Utils.dateprint()} - Recibido PLACED PENDING ORDER EVENT con volumen {event.volume} para {event.signal} {event.target_order} en {event.symbol} al precio {event.target_price}")
        self._process_execution_or_pending_events(event)

    def _handle_news_event(self, event):
        print(f"{Utils.dateprint()} - Recibido NEWS EVENT - Evaluando con IA si cerrar posiciones")
        affected_symbols = getattr(event, 'affected_symbols', []) or []
        normalized_affected = {normalize_symbol(s) for s in affected_symbols if s}

        if self.trading_brain and self.trading_brain.NEWS_PROTECTION:
            close_positions = True
            if hasattr(self.trading_brain, 'ai') and self.trading_brain.ai_enabled and self.trading_brain.ai is not None:
                close_positions = False
                for symbol_key, perf in self.trading_brain.asset_performance.items():
                    if normalized_affected and symbol_key not in normalized_affected:
                        continue
                    total_trades = perf.get("total_trades", 0)
                    win_rate = perf.get("win_rate", 0.0)
                    if total_trades >= 20 and win_rate >= 0.5:
                        close_positions = True
                        break

            if close_positions:
                positions = self.order_executor.PORTFOLIO.get_strategy_open_positions()
                for position in positions:
                    symbol_key = normalize_symbol(position.symbol)
                    if normalized_affected and symbol_key not in normalized_affected:
                        continue
                    self.order_executor.close_position_by_ticket(position.ticket)
                self.notification_service.send_notification(
                    title="📰 NOTICIA DETECTADA",
                    message=f"Se han cerrado posiciones afectadas por protección de noticias"
                )
            else:
                self.notification_service.send_notification(
                    title="📰 NOTICIA DETECTADA",
                    message=f"IA decidió mantener posiciones abiertas durante noticia (rendimiento histórico aceptable)"
                )

    def _handle_fvg_event(self, event):
        print(f"{Utils.dateprint()} - Recibido FVG EVENT - Fair Value Gap detectado")

    def _process_execution_or_pending_events(self, event: ExecutionEvent | PlacedPendingOrderEvent):
        if isinstance(event, ExecutionEvent):
            self.notification_service.send_notification(title=f"{event.symbol} - MARKET ORDER", message=f"{Utils.dateprint()} - Ejecutada MARKET ORDER {event.signal} en {event.symbol} con volumen {event.volume} al precio {event.fill_price}")
        elif isinstance(event, PlacedPendingOrderEvent):
            self.notification_service.send_notification(title=f"{event.symbol} - PENDING PLACED", message=f"{Utils.dateprint()} - Colocada PENDING ORDER con volumen {event.volume} para {event.signal} {event.target_order} en {event.symbol} al precio {event.target_price}")
        else:
            pass

    def _handle_none_event(self, event):
        print(f"{Utils.dateprint()} - ERROR: Recibido evento nulo. Terminando ejecución del Framework")
        self.continue_trading = False

    def _handle_unknown_event(self, event):
        print(f"{Utils.dateprint()} - ERROR: Recibido evento desconocido. Terminando ejecución del Framework. Evento: {event}")
        self.continue_trading = False

    def _handle_report_event(self, event: ReportEvent):
        if self.trading_brain:
            print(self.trading_brain.get_institutional_report())

    def _maybe_print_institutional_report(self) -> None:
        now_ts = time.time()
        if now_ts - self._last_institutional_report_ts < self._institutional_report_interval_seconds:
            return
        self._last_institutional_report_ts = now_ts
        if self.trading_brain:
            current_symbols = []
            if self.signal_generator and hasattr(self.signal_generator, "asset_category_map"):
                current_symbols = list(self.signal_generator.asset_category_map.keys())
            print(self.trading_brain.get_institutional_report(current_symbols=current_symbols))

    def _check_trade_loss_limit(self, signal_event) -> bool:
        """Verifica si la pérdida potencial de una operación excede el límite del circuit breaker."""
        daily_start_balance = getattr(self.trading_brain, '_daily_start_balance', 0.0)
        max_loss_per_trade_pct = getattr(self.trading_brain, '_daily_loss_pct_limit', 0.02) # Usamos el límite diario como máximo por trade

        if self.connector is None or daily_start_balance <= 0.0:
            return False

        sl = getattr(signal_event, 'sl', 0.0)
        if sl <= 0.0:
            return False

        symbol_info = self.connector.get_symbol_info(signal_event.symbol)
        last_tick = self.data_provider.get_latest_tick(signal_event.symbol)
        if symbol_info is None or not last_tick:
            return False

        entry_price = last_tick.get("ask") if signal_event.signal == "BUY" else last_tick.get("bid")
        if entry_price is None or entry_price <= 0: return False

        sl_distance = abs(entry_price - sl)
        if sl_distance <= 0: return False

        volume = getattr(signal_event, 'volume', 0.0)
        if volume <= 0.0: return False

        tick_value = getattr(symbol_info, 'trade_tick_value', 0.0)
        tick_size = getattr(symbol_info, 'trade_tick_size', 0.0)
        if tick_value <= 0 or tick_size <= 0:
            return False

        sl_ticks = sl_distance / tick_size
        loss_amount = sl_ticks * tick_value * volume
        max_loss = daily_start_balance * max_loss_per_trade_pct

        if loss_amount > max_loss:
            logger.warning("TRADING DIRECTOR: Señal %s %s descartada: pérdida potencial %.2f > máximo %.2f",
                         signal_event.symbol, signal_event.signal, loss_amount, max_loss)
            return True
        return False

    def _check_opposite_position(self, symbol: str, signal: str) -> bool:
        if self.portfolio is None:
            return False
        positions = self.portfolio.get_strategy_open_positions_by_symbol(symbol)
        for position in positions:
            position_signal = "BUY" if position.type == mt5.ORDER_TYPE_BUY else "SELL"
            if position_signal != signal:
                print(f"{Utils.dateprint()} - TRADING DIRECTOR: Omitiendo señal {signal} para {symbol}: ya existe posición opuesta {position_signal} (ticket {position.ticket})")
                return True
        return False
