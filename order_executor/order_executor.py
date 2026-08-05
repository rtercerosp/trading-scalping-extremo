# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from platform_connector.platform_connector import PlatformConnector
from portfolio.portfolio import Portfolio
from notifications.notifications import NotificationService
from events.events import OrderEvent, ExecutionEvent, PlacedPendingOrderEvent, SignalType
from utils.utils import Utils
from utils.symbol_utils import normalize_symbol
import pandas as pd
from queue import Queue 
import MetaTrader5 as mt5
import time
from datetime import datetime

class OrderExecutor():

    def __init__(self, events_queue: Queue, portfolio: Portfolio, notification_service: NotificationService, connector: PlatformConnector, trading_director=None) -> None:
        self.events_queue = events_queue
        self.portfolio = portfolio
        self.notification_service = notification_service
        self.connector = connector
        self.trading_director = trading_director
        self._error_blacklist: dict[str, float] = {}
        self._error_blacklist_seconds = 60

    def execute_order(self, order_event: OrderEvent) -> None:
        if order_event.symbol in self._error_blacklist:
            last_error_time = self._error_blacklist[order_event.symbol]
            if time.time() - last_error_time < self._error_blacklist_seconds:
                return
            del self._error_blacklist[order_event.symbol]

        if self.portfolio is not None:
            symbol_key = normalize_symbol(order_event.symbol)
            if not self.portfolio.can_open_position(symbol_key):
                print(f"{Utils.dateprint()} - ORD EXEC: Límite de portfolio alcanzado. Se omite orden para {order_event.symbol} ({order_event.signal} {order_event.volume} lotes)")
                return

        if order_event.target_order == "MARKET":
            if order_event.tp1 > 0.0 and order_event.tp2 > 0.0:
                self._execute_dual_entry_order(order_event)
            else:
                self._execute_market_order(order_event)
        else:
            self._send_pending_order(order_event)

    def _blacklist_symbol(self, symbol: str) -> None:
        self._error_blacklist[symbol] = time.time()

    def _validate_pre_trade(self, order_event: OrderEvent) -> tuple:
        symbol_info = self.connector.get_symbol_info(order_event.symbol)
        if symbol_info is None:
            return False, f"No se pudo obtener symbol_info para {order_event.symbol}"

        is_tradable, tradable_msg = self.connector.is_symbol_tradable(order_event.symbol)
        if not is_tradable:
            return False, f"Símbolo {order_event.symbol} no es negociable: {tradable_msg}"

        account_info = self.connector.get_account_info()
        if account_info is None or not account_info.trade_allowed:
            return False, f"Cuenta no permite trading. Trade allowed: {account_info.trade_allowed if account_info else 'N/A'}"

        if order_event.volume < symbol_info.volume_min:
            return False, f"Volumen {order_event.volume} menor al mínimo {symbol_info.volume_min}"

        if order_event.volume > symbol_info.volume_max:
            return False, f"Volumen {order_event.volume} mayor al máximo {symbol_info.volume_max}"

        return True, "OK"

    def _get_filling_mode(self, symbol: str) -> int:
        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            return mt5.ORDER_FILLING_IOC

        filling_modes = getattr(symbol_info, 'filling_modes', 0)

        if filling_modes & 1:
            return mt5.ORDER_FILLING_IOC
        if filling_modes & 2:
            return mt5.ORDER_FILLING_RETURN
        return mt5.ORDER_FILLING_IOC

    @staticmethod
    def _make_valid_stops(signal: str, price: float, sl: float, tp: float, symbol_info, symbol: str = "") -> tuple:
        from utils.symbol_utils import get_asset_category, normalize_symbol
        asset_cat = get_asset_category(normalize_symbol(symbol)) if symbol else "forex"
        
        if symbol_info is None:
            return sl, tp
        point = symbol_info.point
        stops_level = int(getattr(symbol_info, 'trade_stops_level', 0) or 0)
        
        min_stop_points = max(stops_level, 0) + 5
        if asset_cat == "gold":
            min_stop_points = max(min_stop_points, 300)
        elif asset_cat == "crypto":
            price_for_calc = price if price > 0 else 1.0
            min_stop_points = max(min_stop_points, int(price_for_calc * 0.0005 / point) if point > 0 else 5000)
        
        sl_distance_points = abs(sl - price) / point if point > 0 else 0
        tp_distance_points = abs(tp - price) / point if point > 0 else 0
        
        sl_distance_points = max(sl_distance_points, min_stop_points)
        tp_distance_points = max(tp_distance_points, min_stop_points)
        
        if signal == "BUY":
            sl = price - sl_distance_points * point
            tp = price + tp_distance_points * point
        else:
            sl = price + sl_distance_points * point
            tp = price - tp_distance_points * point

        decimals = max(0, -int(__import__('math').floor(__import__('math').log10(point)))) if point > 0 else 0
        sl = round(sl, decimals)
        tp = round(tp, decimals)
        price = round(price, decimals)

        print(f"{Utils.dateprint()} - ORD EXEC: Stops calc point={point} stops_level={stops_level} raw_sl_pts={abs(sl - price) / point if point > 0 else 0:.2f} raw_tp_pts={abs(tp - price) / point if point > 0 else 0:.2f} => sl={sl} tp={tp}")
        return sl, tp


    def _execute_market_order(self, order_event: OrderEvent, skip_tp2_pending: bool = False) -> None:
        if order_event.signal == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
        elif order_event.signal == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
        else:
            raise Exception(f"ORD EXEC: La señal {order_event.signal} no es válida")

        valid, msg = self._validate_pre_trade(order_event)
        if not valid:
            print(f"{Utils.dateprint()} - ORD EXEC: Validación fallida para {order_event.symbol}: {msg}")
            return

        symbol_info = self.connector.get_symbol_info(order_event.symbol)
        if symbol_info:
            volume = round(order_event.volume / symbol_info.volume_step) * symbol_info.volume_step
            if volume < symbol_info.volume_min:
                volume = symbol_info.volume_min

        sl = order_event.sl
        tp = order_event.tp
        comment = "FWK Market Order"

        if tp == 0.0 and order_event.tp1 > 0.0 and order_event.tp2 <= 0.0:
            tp = order_event.tp1
        
        if order_event.tp1 > 0.0 and order_event.tp2 > 0.0:
            if tp == order_event.tp1:
                comment = "FWK Market Order TP1"
            elif tp == order_event.tp2:
                comment = "FWK Market Order TP2"

        filling_mode = self._get_filling_mode(order_event.symbol)
        symbol_info = self.connector.get_symbol_info(order_event.symbol)
        if symbol_info:
            print(f"{Utils.dateprint()} - ORD EXEC: {order_event.symbol} point={symbol_info.point} trade_stops_level={symbol_info.trade_stops_level} filling={filling_mode} ask={symbol_info.ask} bid={symbol_info.bid} spread={symbol_info.ask - symbol_info.bid:.2f}")
        price = symbol_info.ask if order_event.signal == "BUY" else symbol_info.bid

        sl, tp = self._make_valid_stops(order_event.signal, price, sl, tp, symbol_info, symbol=order_event.symbol)

        if order_event.signal == "BUY" and (sl >= price or tp <= price):
            print(f"{Utils.dateprint()} - ORD EXEC: Stops inválidos para BUY {order_event.symbol}: sl={sl} tp={tp} price={price}")
            return
        if order_event.signal == "SELL" and (sl <= price or tp >= price):
            print(f"{Utils.dateprint()} - ORD EXEC: Stops inválidos para SELL {order_event.symbol}: sl={sl} tp={tp} price={price}")
            return

        market_order_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order_event.symbol,
            "volume": volume,
            "price": price,
            "sl": sl,
            "tp": tp,
            "type": order_type,
            "deviation": 20 if order_event.symbol.startswith(("XAU", "GOLD")) else 10,
            "magic": order_event.magic_number,
            "comment": comment,
            "type_filling": filling_mode,
        }

        print(f"{Utils.dateprint()} - ORD EXEC: {order_event.signal} {order_event.symbol} exec_price={price} spread={symbol_info.ask - symbol_info.bid:.2f} sl={sl} tp={tp}" + (" [PRIORITY:GOLD]" if order_event.symbol.startswith(("XAU", "GOLD")) else ""))
        result = self.connector.order_send(market_order_request)
        if result.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL):
            if result.retcode == mt5.TRADE_RETCODE_INVALID_STOPS and (sl != 0.0 or tp != 0.0):
                min_stops = int(getattr(symbol_info, 'trade_stops_level', 0) or 0) + 5
                from utils.symbol_utils import get_asset_category, normalize_symbol
                asset_cat = get_asset_category(normalize_symbol(order_event.symbol))
                if asset_cat == "crypto":
                    min_stops = max(min_stops, int(price * 0.0005 / symbol_info.point) if symbol_info.point > 0 else 5000)
                
                point = symbol_info.point
                if order_event.signal == "BUY":
                    sl = price - min_stops * point
                    tp = price + min_stops * point
                else:
                    sl = price + min_stops * point
                    tp = price - min_stops * point
                
                decimals = max(0, -int(__import__('math').floor(__import__('math').log10(point)))) if point > 0 else 0
                sl = round(sl, decimals)
                tp = round(tp, decimals)
                
                print(f"{Utils.dateprint()} - ORD EXEC: Reintento {order_event.symbol} con SL/TP reducidos por retcode 10016: sl={sl} tp={tp}")
                retry_request = dict(market_order_request)
                retry_request["sl"] = sl
                retry_request["tp"] = tp
                result = self.connector.order_send(retry_request)
                if result.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL):
                    print(f"{Utils.dateprint()} - ORD EXEC: Fallo reintento con SL/TP reducidos para {order_event.symbol}: {result.comment} (retcode: {result.retcode}). Cancelando orden.")
                    try:
                        cancel_request = {
                            "action": mt5.TRADE_ACTION_REMOVE,
                            "order": result.order,
                            "symbol": order_event.symbol,
                        }
                        self.connector.order_send(cancel_request)
                    except Exception as e:
                        logging.error("ORD EXEC: No se pudo cancelar la orden fallida para %s: %s", order_event.symbol, e, exc_info=True)
                    error_message = f"Error al ejecutar Market Order {order_event.signal} para {order_event.symbol}: {result.comment} (retcode: {result.retcode}) - SL/TP inválidos"
                    print(f"{Utils.dateprint()} - {error_message}")
                    self.notification_service.send_notification(
                        title=f"❌ FALLO DE ORDEN - {order_event.symbol}",
                        message=error_message
                    )
                    return

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            message = f"Market Order {order_event.signal} para {order_event.symbol} de {volume} lotes ejecutada correctamente. Ticket: {result.order}"
            print(f"{Utils.dateprint()} - {message}")
            self.notification_service.send_notification(
                title=f"✅ ORDEN EJECUTADA - {order_event.symbol}",
                message=message
            )
        else:
            error_message = f"Error al ejecutar Market Order {order_event.signal} para {order_event.symbol}: {result.comment} (retcode: {result.retcode})"
            print(f"{Utils.dateprint()} - {error_message}")
            print(f"{Utils.dateprint()} - ORD EXEC: Request: {market_order_request}")
            self._blacklist_symbol(order_event.symbol)
            self.notification_service.send_notification(
                title=f"❌ FALLO DE ORDEN - {order_event.symbol}",
                message=error_message
            )
            return

        log_tp_part = f"TP={tp}"
        if "TP1" in comment:
            log_tp_part = f"TP1={tp}"
        elif "TP2" in comment:
            log_tp_part = f"TP2={tp}"
        
        print(f"{Utils.dateprint()} - Market Order {order_event.signal} para {order_event.symbol} de {volume} lotes ejecutada correctamente ({log_tp_part})")
        self._create_and_put_execution_event(
            result,
            tp1=order_event.tp1,
            tp2=order_event.tp2,
            strategy_name=order_event.strategy_name,
            asset_category=order_event.asset_category,
            market_regime=order_event.market_regime,
            analysis_context=order_event.analysis_context,
        )
        if not skip_tp2_pending and order_event.tp1 > 0.0 and order_event.tp2 > 0.0:
            self._place_tp2_pending_order(order_event, result)

    def _execute_dual_entry_order(self, order_event: OrderEvent) -> None:
        symbol_info = self.connector.get_symbol_info(order_event.symbol)
        if symbol_info is None:
            print(f"{Utils.dateprint()} - ORD EXEC: No se pudo obtener symbol_info para {order_event.symbol}")
            return

        volume_step = symbol_info.volume_step
        volume_min = symbol_info.volume_min
        half_volume = round(order_event.volume / 2 / volume_step) * volume_step
        if half_volume < volume_min:
            half_volume = volume_min

        tp1_order = OrderEvent(
            symbol=order_event.symbol,
            signal=order_event.signal,
            target_order=order_event.target_order,
            target_price=order_event.target_price,
            magic_number=order_event.magic_number,
            sl=order_event.sl,
            tp=order_event.tp1,
            tp1=order_event.tp1,
            tp2=order_event.tp2,
            volume=half_volume,
            strategy_name=order_event.strategy_name,
            asset_category=order_event.asset_category,
            market_regime=order_event.market_regime,
            analysis_context=order_event.analysis_context,
        )

        tp2_order = OrderEvent(
            symbol=order_event.symbol,
            signal=order_event.signal,
            target_order=order_event.target_order,
            target_price=order_event.target_price,
            magic_number=order_event.magic_number,
            sl=order_event.sl,
            tp=order_event.tp2,
            tp1=order_event.tp1,
            tp2=order_event.tp2,
            volume=half_volume,
            strategy_name=order_event.strategy_name,
            asset_category=order_event.asset_category,
            market_regime=order_event.market_regime,
            analysis_context=order_event.analysis_context,
        )

        print(f"{Utils.dateprint()} - ORD EXEC: Ejecutando entrada dual para {order_event.symbol} - Volumen total: {order_event.volume}, TP1: {order_event.tp1}, TP2: {order_event.tp2}")

        valid1, msg1 = self._validate_pre_trade(tp1_order)
        valid2, msg2 = self._validate_pre_trade(tp2_order)

        if not valid1:
            print(f"{Utils.dateprint()} - ORD EXEC: Validación fallida para TP1 order: {msg1}")
        if not valid2:
            print(f"{Utils.dateprint()} - ORD EXEC: Validación fallida para TP2 order: {msg2}")

        if valid1:
            self._execute_market_order(tp1_order, skip_tp2_pending=True)
        if valid2:
            self._execute_market_order(tp2_order, skip_tp2_pending=True)

    def _send_pending_order(self, order_event: OrderEvent) -> None:
        if order_event.target_order == "STOP":
            order_type = mt5.ORDER_TYPE_BUY_STOP if order_event.signal == "BUY" else mt5.ORDER_TYPE_SELL_STOP
        elif order_event.target_order == "LIMIT":
            order_type = mt5.ORDER_TYPE_BUY_LIMIT if order_event.signal == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
        else:
            raise Exception(f"ORD EXEC: La orden pendiente objetivo {order_event.target_order} no es válida")

        valid, msg = self._validate_pre_trade(order_event)
        if not valid:
            print(f"{Utils.dateprint()} - ORD EXEC: Validación fallida para pending order {order_event.symbol}: {msg}")
            return

        filling_mode = self._get_filling_mode(order_event.symbol)

        pending_order_request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": order_event.symbol,
            "volume": order_event.volume,
            "sl": order_event.sl,
            "tp": order_event.tp,
            "type": order_type,
            "price": order_event.target_price,
            "deviation": 10,
            "magic": order_event.magic_number,
            "comment": "FWK Pnding Order",
            "type_filling": filling_mode,
            "type_time": mt5.ORDER_TIME_GTC,
        }

        result = self.connector.order_send(pending_order_request)

        if self._check_execution_status(result):
            print(f"{Utils.dateprint()} - Pending Order {order_event.signal} {order_event.target_order} para {order_event.symbol} de {order_event.volume} lotes colocada en {order_event.target_price} correctamente")
            self._create_and_put_placed_pending_order_event(order_event)
        else:
            message = f"Error al colocar pending order {order_event.signal} {order_event.target_order} para {order_event.symbol}: {result.comment} (retcode: {result.retcode})"
            print(f"{Utils.dateprint()} - {message}")
            self._blacklist_symbol(order_event.symbol)
            self.notification_service.send_notification(
                title=f"❌ FALLO DE ORDEN PENDIENTE - {order_event.symbol}",
                message=message
            )

    def cancel_pending_order_by_ticket(self, ticket: int) -> None:
        orders = self.connector.get_orders(ticket=ticket)
        if not orders:
            print(f"{Utils.dateprint()} - ORD EXEC: No existe ninguna orden pendiente con el ticket {ticket}")
            return

        order = orders[0]

        cancel_request = {
            'action': mt5.TRADE_ACTION_REMOVE,
            'order': order.ticket,
            'symbol': order.symbol
        }

        result = self.connector.order_send(cancel_request)

        if self._check_execution_status(result):
            print(f"{Utils.dateprint()} - Orden pendiente con ticket {ticket} en {order.symbol} cancelada correctamente")
        else:
            print(f"{Utils.dateprint()} - Error al cancelar la orden {ticket} en {order.symbol}: {result.comment}")
            self._blacklist_symbol(order.symbol)

    def close_position_by_ticket(self, ticket: int, volume: float = 0.0, exit_reason: str = "CLOSED") -> None:
        positions = self.connector.get_positions(ticket=ticket)
        if not positions:
            print(f"{Utils.dateprint()} - ORD EXEC: No existe ninguna posición con el ticket {ticket} para cerrar.")
            return

        position = positions[0]

        close_volume = volume if volume > 0.0 else position.volume
        symbol_info = self.connector.get_symbol_info(position.symbol)
        if symbol_info:
            close_volume = round(close_volume / symbol_info.volume_step) * symbol_info.volume_step
            if close_volume < symbol_info.volume_min:
                close_volume = symbol_info.volume_min

        close_request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'position': position.ticket,
            'symbol': position.symbol,
            'volume': close_volume,
            'type': mt5.ORDER_TYPE_BUY if position.type == mt5.ORDER_TYPE_SELL else mt5.ORDER_TYPE_SELL,
            'price': self.connector.get_symbol_info(position.symbol).ask if position.type == mt5.ORDER_TYPE_SELL else self.connector.get_symbol_info(position.symbol).bid,
            'type_filling': self._get_filling_mode(position.symbol)
        }

        result = self.connector.order_send(close_request)

        if self._check_execution_status(result):
            print(f"{Utils.dateprint()} - Posición con ticket {ticket} en {position.symbol} y volumen {close_volume} se ha cerrado correctamente")
            self._create_and_put_execution_event(result, exit_reason=exit_reason)
        else:
            print(f"{Utils.dateprint()} - Error al cerrar la posición {ticket} en {position.symbol} con volumen {close_volume}: {result.comment}")
            self._blacklist_symbol(position.symbol)

    def close_strategy_long_positions_by_symbol(self, symbol: str) -> None:
        positions = self.portfolio.get_strategy_open_positions()
        for position in positions:
            if position.symbol == symbol and position.type == mt5.ORDER_TYPE_BUY:
                self.close_position_by_ticket(position.ticket)

    def close_strategy_short_positions_by_symbol(self, symbol: str) -> None:
        positions = self.portfolio.get_strategy_open_positions()
        for position in positions:
            if position.symbol == symbol and position.type == mt5.ORDER_TYPE_SELL:
                self.close_position_by_ticket(position.ticket)

    def _create_and_put_placed_pending_order_event(self, order_event: OrderEvent) -> None:
        placed_pending_order_event = PlacedPendingOrderEvent(
            symbol=order_event.symbol,
            signal=order_event.signal,
            target_order=order_event.target_order,
            target_price=order_event.target_price,
            magic_number=order_event.magic_number,
            sl=order_event.sl,
            tp=order_event.tp,
            volume=order_event.volume)
        self.events_queue.put(placed_pending_order_event)

    def _create_and_put_execution_event(self, order_result, tp1=0.0, tp2=0.0, strategy_name="UNKNOWN", asset_category="forex", market_regime="unknown", analysis_context=None, exit_reason: str = "OPEN") -> None:
        deal = None
        fill_time = datetime.now()
        position_ticket = 0
        deal_ticket = getattr(order_result, 'deal', 0)
        if analysis_context is None:
            analysis_context = {}

        if deal_ticket > 0:
            for _ in range(10):
                time.sleep(0.1)
                deals = self.connector.get_history_deals(ticket=deal_ticket)
                if deals and len(deals) > 0:
                    deal = deals[0]
                    break

        if deal:
            fill_time = pd.to_datetime(deal.time_msc, unit='ms')
            position_ticket = deal.position_id
        else:
            print(f"{Utils.dateprint()} - ORD EXEC: No se ha podido obtener el deal {deal_ticket} para la orden {order_result.order}.")

        execution_event = ExecutionEvent(
            symbol=order_result.request.symbol,
            signal=SignalType.BUY if order_result.request.type == mt5.DEAL_TYPE_BUY else SignalType.SELL,
            fill_price=order_result.price,
            fill_time=fill_time if not deal else pd.to_datetime(deal.time_msc, unit='ms'),
            entry_price=order_result.price,
            initial_sl=order_result.request.sl,
            initial_tp=order_result.request.tp,
            tp1=tp1,
            tp2=tp2,
            volume=order_result.request.volume,
            position_ticket=position_ticket,
            strategy_type=strategy_name,
            strategy_name=strategy_name,
            asset_category=asset_category,
            market_regime=market_regime,
            analysis_context=analysis_context,
            deal_ticket=deal_ticket,
            exit_reason=exit_reason,
        )

        self.events_queue.put(execution_event)

    def modify_position_sl(self, position_ticket: int, new_sl: float, new_tp: float = 0.0) -> None:
        positions = self.connector.get_positions(ticket=position_ticket)
        if not positions:
            print(f"{Utils.dateprint()} - ORD EXEC: No existe ninguna posición con el ticket {position_ticket} para modificar SL/TP.")
            return

        position = positions[0]
        symbol_info = self.connector.get_symbol_info(position.symbol)
        if symbol_info:
            new_sl, new_tp = self._make_valid_stops(
                "BUY" if position.type == mt5.ORDER_TYPE_BUY else "SELL",
                position.price_current,
                new_sl,
                new_tp if new_tp != 0.0 else position.tp,
                symbol_info,
                symbol=position.symbol,
            )

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": position.ticket,
            "sl": new_sl,
            "tp": new_tp if new_tp != 0.0 else position.tp,
            "magic": position.magic,
            "comment": "FWK SL/TP Modified"
        }

        print(f"{Utils.dateprint()} - ORD EXEC: modify_position_sl ticket={position_ticket} symbol={position.symbol} request={request} current_sl={position.sl} current_tp={position.tp} price={position.price_current}")
        result = self.connector.order_send(request)
        print(f"{Utils.dateprint()} - ORD EXEC: modify_position_sl result retcode={result.retcode} comment={result.comment}")
        if self._check_execution_status(result):
            print(f"{Utils.dateprint()} - ORD EXEC: SL/TP de posición {position_ticket} modificado a SL={new_sl}, TP={new_tp if new_tp != 0.0 else position.tp} correctamente.")
        else:
            print(f"{Utils.dateprint()} - ORD EXEC: Error al modificar SL/TP de posición {position_ticket}: {result.comment}")
            self._blacklist_symbol(position.symbol)

    def _check_execution_status(self, order_result) -> bool:
        if order_result.retcode == mt5.TRADE_RETCODE_DONE:
            return True
        elif order_result.retcode == mt5.TRADE_RETCODE_DONE_PARTIAL:
            return True
        else:
            return False

    def _place_tp2_pending_order(self, order_event: OrderEvent, initial_result) -> None:
        symbol = order_event.symbol
        volume = order_event.volume
        tp2_price = order_event.tp2

        if tp2_price <= 0.0:
            return

        positions = self.connector.get_positions(symbol=symbol)
        if not positions:
            return

        position = None
        for pos in positions:
            if pos.magic == order_event.magic_number and pos.symbol == symbol:
                position = pos
                break

        if position is None:
            return

        if order_event.signal == "BUY":
            order_type = mt5.ORDER_TYPE_SELL_LIMIT
        else:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            print(f"{Utils.dateprint()} - ORD EXEC: No se pudo obtener symbol_info para TP2 pending {symbol}")
            return

        min_stop_points = symbol_info.trade_stops_level + 5
        original_sl_distance_points = max(abs(order_event.sl - initial_result.price) / symbol_info.point, min_stop_points)

        if order_event.signal == "BUY":
            pending_sl = tp2_price + original_sl_distance_points * symbol_info.point
        else:
            pending_sl = tp2_price - original_sl_distance_points * symbol_info.point

        pending_order_request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "sl": pending_sl,
            "tp": 0.0,
            "type": order_type,
            "price": tp2_price,
            "deviation": 10,
            "magic": order_event.magic_number,
            "comment": "FWK TP2 Pending Order",
            "type_filling": self._get_filling_mode(symbol),
            "type_time": mt5.ORDER_TIME_GTC,
        }

        result = self.connector.order_send(pending_order_request)
        if self._check_execution_status(result):
            print(f"{Utils.dateprint()} - Pending TP2 order placed for {symbol} at {tp2_price}")
        else:
            print(f"{Utils.dateprint()} - Error placing TP2 pending order for {symbol}: {result.comment}")
