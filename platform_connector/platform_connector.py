# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from utils.utils import Utils
from utils.symbol_utils import normalize_symbol
import MetaTrader5 as mt5
import os
import pandas as pd
import logging
from dotenv import load_dotenv, find_dotenv

class PlatformConnector():

    def __init__(self, symbol_list: list, skip_warning: bool = False):
        """
        Initializes the platform connector object.

        Args:
            symbol_list (list): List of symbols to be added to the MarketWatch.
            skip_warning (bool): If True, skips the live account warning prompt.
        """
        # --- Carga de Configuración ---
        env_file_path = find_dotenv()
        if env_file_path:
            print(f"[i] Cargando configuracion desde: {env_file_path}")
            load_dotenv(env_file_path)
        else:
            print("[!] ADVERTENCIA: No se encontró ningún archivo .env. Se usarán variables de entorno del sistema si existen.")

        # Inicialización de la plataforma
        self._initialize_platform()

        # Comprobación del tipo de cuenta
        self._live_account_warning(skip_warning=skip_warning)

        # Imprimimos información de la cuenta
        self._print_account_info()

        # Comprobación del trading algorítmico
        self._check_algo_trading_enabled()

        # Añadimos los símbolos al MarketWatch
        self._add_symbols_to_marketwatch(symbol_list)

    def _initialize_platform(self) -> None:
        """
        Initializes the MT5 platform.

        Raises:
            Exception: If there is any error while initializing the Platform

        """
        portable_str = os.getenv("MT5_PORTABLE", "False").lower()
        portable_bool = portable_str in ('true', '1', 't', 'y', 'yes')

        try:
            login = int(os.getenv("MT5_LOGIN"))
            timeout = int(os.getenv("MT5_TIMEOUT"))
        except (ValueError, TypeError):
            raise Exception("[!] ERROR: MT5_LOGIN y MT5_TIMEOUT deben ser números enteros en tu archivo .env.")

        # --- DIAGNÓSTICO: Imprimir las credenciales que se van a utilizar ---
        login_to_use = login
        server_to_use = os.getenv("MT5_SERVER")
        path_to_use = os.getenv("MT5_PATH")
        print("-" * 60)
        print("[i] INTENTANDO CONECTAR CON LOS SIGUIENTES DATOS:")
        print(f"    - Path:   {path_to_use}")
        masked_login = str(login_to_use)[:4] + "****" if login_to_use else "****"
        masked_server = "****" if server_to_use else "****"
        print(f"    - Login:  {masked_login}")
        print(f"    - Server: {masked_server}")
        print("-" * 60)

        if mt5.initialize(
            path=path_to_use,
            login=login_to_use,
            password=os.getenv("MT5_PASSWORD"),
            server=server_to_use,
            timeout=timeout,
            portable=portable_bool):
            print(f"{Utils.dateprint()} - La plataforma MT5 se ha lanzado con éxito!")
        else:
            raise Exception(f"Ha ocurrido un error al inicializar la plataforma MT5: {mt5.last_error()}")

    def _live_account_warning(self, skip_warning: bool = False) -> None:
        """
        Displays a warning message if a real trading account is detected.
        Prompts the user to confirm if they want to continue.
        If the user chooses not to continue, the program is shut down.
        
        Args:
            skip_warning (bool): If True, skips the prompt and continues automatically.
        """
        # Recuperamos el objeto de tipo AccountInfo
        account_info = mt5.account_info()
        
        # Comprobar el tipo de cuenta que se ha lanzado
        if account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO:
            print("Cuenta de tipo DEMO detectada.")
        
        elif account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL:
            if skip_warning:
                print("ALERTA! Cuenta de tipo REAL detectada. Continuando en modo prueba sin confirmación.")
            elif not input("ALERTA! Cuenta de tipo REAL detectada. Capital en riesgo. ¿Deseas continuar? (y/n): ").lower() == "y":
                mt5.shutdown()
                raise Exception("Usuario ha decidido DETENER el programa.")
        else:
            print("Cuenta de tipo CONCURSO detectada.")

    def _check_algo_trading_enabled(self) -> None:
        """
        Checks if algorithmic trading is enabled.

        Raises:
            Exception: If algorithmic trading is disabled.
        """
        terminal_info = mt5.terminal_info()
        if terminal_info is None or not terminal_info.trade_allowed:
            raise Exception("El trading algorítmico está desactivado. Por favor, actívalo MANUALMENTE desde la configuración del terminal MT5.")

        account_info = mt5.account_info()
        if account_info is None or not account_info.trade_allowed:
            raise Exception(f"La cuenta no tiene habilitado el trading. Trade allowed: {account_info.trade_allowed if account_info else 'N/A'}")

    def is_symbol_tradable(self, symbol: str) -> tuple:
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return False, f"Symbol {symbol} not found"
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None or not symbol_info.visible:
                return False, f"Symbol {symbol} not visible in MarketWatch"
        return True, "OK"

    def _resolve_mt5_symbol(self, symbol: str) -> str:
        candidates = [symbol, normalize_symbol(symbol)]
        if not symbol.endswith("c"):
            candidates.append(f"{symbol}c")
        if not normalize_symbol(symbol).endswith("c"):
            candidates.append(f"{normalize_symbol(symbol)}c")
        for candidate in candidates:
            if mt5.symbol_info(candidate) is not None:
                return candidate
        return symbol

    def _add_symbols_to_marketwatch(self, symbols: list) -> None:
        """
        Adds symbols to the MarketWatch if they are not already visible.

        Args:
            symbols (list): List of symbols to be added.

        Returns:
            None
        """
        # 1) Comprobamos si el símbolo ya está visible en el MW
        # 2) Si no lo está, lo añadiremos

        for symbol in symbols:            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                print(f"{Utils.dateprint()} - ERROR: El símbolo '{symbol}' no existe en el broker. Error: {mt5.last_error()}")
                continue
            
            if not symbol_info.visible:
                if not mt5.symbol_select(symbol, True):
                    print(f"{Utils.dateprint()} - ERROR: No se ha podido AÑADIR el símbolo '{symbol}' al MarketWatch. Error: {mt5.last_error()}")
                else:
                    print(f"{Utils.dateprint()} - Símbolo {symbol} se ha añadido con éxito al MarketWatch!")
            else:
                print(f"{Utils.dateprint()} - El símbolo {symbol} ya estaba en el MarketWatch.")

    def _print_account_info(self) -> None:
        """
        Prints the account information including account ID, trader name, broker, server, leverage, currency, and balance.
        """
        # Recuperar un objeto de tipo AccountInfo
        account_info = mt5.account_info()._asdict()

        print(f"+------------ Información de la cuenta ------------")
        print(f"| - ID de cuenta: {account_info['login']}")
        print(f"| - Nombre trader: {account_info['name']}")
        print(f"| - Broker: {account_info['company']}")
        print(f"| - Servidor: {account_info['server']}")
        print(f"| - Apalancamiento: {account_info['leverage']}")
        print(f"| - Divisa de la cuenta: {account_info['currency']}")
        print(f"| - Balance de la cuenta: {account_info['balance']}")
        print(f"+--------------------------------------------------")

    def _map_timeframes(self, timeframe: str) -> int:
        """Maps a string timeframe to its corresponding integer value."""
        timeframe_mapping = {
            '1min': mt5.TIMEFRAME_M1, '2min': mt5.TIMEFRAME_M2, '3min': mt5.TIMEFRAME_M3,
            '4min': mt5.TIMEFRAME_M4, '5min': mt5.TIMEFRAME_M5, '6min': mt5.TIMEFRAME_M6,
            '10min': mt5.TIMEFRAME_M10, '12min': mt5.TIMEFRAME_M12, '15min': mt5.TIMEFRAME_M15,
            '20min': mt5.TIMEFRAME_M20, '30min': mt5.TIMEFRAME_M30, '1h': mt5.TIMEFRAME_H1,
            '2h': mt5.TIMEFRAME_H2, '3h': mt5.TIMEFRAME_H3, '4h': mt5.TIMEFRAME_H4,
            '6h': mt5.TIMEFRAME_H6, '8h': mt5.TIMEFRAME_H8, '12h': mt5.TIMEFRAME_H12,
            '1d': mt5.TIMEFRAME_D1, '1w': mt5.TIMEFRAME_W1, '1M': mt5.TIMEFRAME_MN1,
        }
        try:
            return timeframe_mapping[timeframe]
        except KeyError:
            print(f"{Utils.dateprint()} - Timeframe {timeframe} no es válido.")
            return None

    def get_latest_closed_bars(self, symbol: str, timeframe: str, num_bars: int = 1) -> pd.DataFrame:
        """Retrieves the latest closed bars for a given symbol and timeframe."""
        mt5_symbol = self._resolve_mt5_symbol(symbol)
        tf = self._map_timeframes(timeframe)
        if tf is None:
            return pd.DataFrame()
        
        from_position = 1
        bars_count = num_bars if num_bars > 0 else 1

        try:
            bars_np_array = mt5.copy_rates_from_pos(mt5_symbol, tf, from_position, bars_count)
            if bars_np_array is None:
                print(f"{Utils.dateprint()} - El símbolo {symbol} no existe o no se han podido recuperar su datos")
                return pd.DataFrame()

            bars = pd.DataFrame(bars_np_array)
            bars['time'] = pd.to_datetime(bars['time'], unit='s')
            bars.set_index('time', inplace=True)
            bars.rename(columns={'tick_volume': 'tickvol', 'real_volume': 'vol'}, inplace=True)
            bars = bars[['open', 'high', 'low', 'close', 'tickvol', 'vol', 'spread']]
        
        except Exception as e:
            print(f"{Utils.dateprint()} - No se han podido recuperar los datos de las velas de {symbol} {timeframe} - MT5 Error: {mt5.last_error()}, exception: {e}")
            return pd.DataFrame()
        
        else:
            return bars

    def get_latest_closed_bar(self, symbol: str, timeframe: str) -> pd.Series:
        """Retrieves the latest closed bar for a given symbol and timeframe."""
        bars = self.get_latest_closed_bars(symbol, timeframe, 1)
        if bars.empty:
            return pd.Series()
        else:
            return bars.iloc[-1]

    def get_account_info(self):
        """Returns the account information."""
        return mt5.account_info()

    def get_symbol_info(self, symbol: str):
        """Returns information about the specified symbol."""
        mt5_symbol = self._resolve_mt5_symbol(symbol)
        return mt5.symbol_info(mt5_symbol)

    def get_symbol_info_tick(self, symbol: str):
        """Returns the latest tick for the specified symbol."""
        mt5_symbol = self._resolve_mt5_symbol(symbol)
        return mt5.symbol_info_tick(mt5_symbol)

    def get_positions(self, ticket: int = None, symbol: str = None):
        """Returns open positions."""
        mt5_symbol = self._resolve_mt5_symbol(symbol) if symbol else None
        if ticket:
            return mt5.positions_get(ticket=ticket)
        if mt5_symbol:
            return mt5.positions_get(symbol=mt5_symbol)
        return mt5.positions_get()

    def get_orders(self, ticket: int = None):
        """Returns pending orders."""
        if ticket:
            return mt5.orders_get(ticket=ticket)
        return mt5.orders_get()

    def get_history_deals(self, ticket: int = None, from_date=None, to_date=None):
        """Returns historical deals."""
        if ticket is not None:
            return mt5.history_deals_get(ticket=ticket)
        if from_date is not None and to_date is not None:
            return mt5.history_deals_get(from_date, to_date)
        return mt5.history_deals_get()

    def order_send(self, request: dict):
        """Sends an order request."""
        result = mt5.order_send(request)
        print(f"{Utils.dateprint()} - PLATFORM CONNECTOR: order_send request={request}")
        if result is None:
            print(f"{Utils.dateprint()} - PLATFORM CONNECTOR: order_send returned None, error={mt5.last_error()}")
        else:
            print(f"{Utils.dateprint()} - PLATFORM CONNECTOR: order_send result retcode={result.retcode} comment={result.comment} order={result.order} deal={result.deal}")
        return result

    def convert_currency_amount_to_another_currency(self, amount: float, from_ccy: str, to_ccy: str) -> float:
        """Converts an amount from one currency to another using broker rates."""
        if from_ccy == to_ccy:
            return amount

        if from_ccy.upper() == 'USD' and to_ccy.upper() == 'USC':
            return amount * 100.0
        if from_ccy.upper() == 'USC' and to_ccy.upper() == 'USD':
            return amount / 100.0

        from_ccy = from_ccy.upper()
        to_ccy = to_ccy.upper()

        pair_direct = f"{from_ccy}{to_ccy}"
        pair_inverse = f"{to_ccy}{from_ccy}"
        
        fx_symbol = None
        if self.get_symbol_info(pair_direct):
            fx_symbol = pair_direct
        elif self.get_symbol_info(pair_inverse):
            fx_symbol = pair_inverse
        
        # Si no se encuentra par directo/inverso, intentar con USD como intermediario
        if not fx_symbol and from_ccy != 'USD' and to_ccy != 'USD':
            # Convertir from_ccy -> USD -> to_ccy
            pair1 = f"{from_ccy}USD"
            pair2 = f"USD{from_ccy}"
            pair3 = f"{to_ccy}USD"
            pair4 = f"USD{to_ccy}"
            
            # Buscar par para from_ccy a USD
            fx1 = None
            if self.get_symbol_info(pair1):
                fx1 = pair1
            elif self.get_symbol_info(pair2):
                fx1 = pair2
            
            # Buscar par para to_ccy a USD
            fx2 = None
            if self.get_symbol_info(pair3):
                fx2 = pair3
            elif self.get_symbol_info(pair4):
                fx2 = pair4
            
            if fx1 and fx2:
                # Conversión en dos pasos via USD
                tick1 = self.get_symbol_info_tick(fx1)
                tick2 = self.get_symbol_info_tick(fx2)
                if tick1 and tick1.bid > 0 and tick2 and tick2.bid > 0:
                    base1 = fx1[:3]
                    base2 = fx2[:3]
                    rate1 = tick1.bid if base1 == 'USD' else 1.0 / tick1.bid
                    rate2 = tick2.bid if base2 == to_ccy else 1.0 / tick2.bid
                    return amount * rate1 * rate2
        
        # Caso especial: convertir moneda de cotización (ej. JPY en USDJPY) a USD
        if not fx_symbol and to_ccy in ('USD', 'USC'):
            # Buscar par que tenga from_ccy como moneda de cotización (ej. USDJPY para JPY)
            for suffix in ('', 'c', 'm', '.m', 'z'):
                test_pair = f"USD{from_ccy}{suffix}"
                if self.get_symbol_info(test_pair):
                    fx_symbol = test_pair
                    break
                test_pair = f"{from_ccy}USD{suffix}"
                if self.get_symbol_info(test_pair):
                    fx_symbol = test_pair
                    break
        
        if not fx_symbol:
            print(f"ERROR: No se pudo encontrar un par de divisas para convertir de {from_ccy} a {to_ccy}.")
            return 0.0

        tick = self.get_symbol_info_tick(fx_symbol)
        if tick is None or tick.bid == 0:
            print(f"ERROR: No se pudo recuperar el precio para el par de conversión {fx_symbol}.")
            return 0.0

        last_price = tick.bid
        fx_symbol_base = fx_symbol[:3]

        return amount / last_price if fx_symbol_base == to_ccy else amount * last_price

    def get_symbol_trading_session(self, symbol: str) -> dict:
        """Returns trading session info for a symbol from MT5, if available."""
        mt5_symbol = self._resolve_mt5_symbol(symbol)
        symbol_info = self.get_symbol_info(mt5_symbol)
        if symbol_info is None:
            return {}
        
        session_info = {}
        
        if hasattr(symbol_info, 'trade_mode'):
            session_info['trade_mode'] = symbol_info.trade_mode
        
        if hasattr(symbol_info, 'session_open'):
            session_info['session_open'] = symbol_info.session_open
        if hasattr(symbol_info, 'session_close'):
            session_info['session_close'] = symbol_info.session_close
        
        if hasattr(symbol_info, 'trading_time') and symbol_info.trading_time:
            try:
                trading_time = symbol_info.trading_time
                if isinstance(trading_time, (list, tuple)) and len(trading_time) > 0:
                    session_info['trading_time'] = trading_time
            except Exception as e:
                logging.debug("PLATFORM CONNECTOR: No se pudo leer trading_time para %s: %s", getattr(symbol_info, 'name', 'unknown'), e)
        
        return session_info

    def is_market_open(self, symbol: str) -> bool:
        """Checks if the market is currently open for a symbol using MT5 data."""
        mt5_symbol = self._resolve_mt5_symbol(symbol)
        symbol_info = self.get_symbol_info(mt5_symbol)
        if symbol_info is None:
            return False
        
        if hasattr(symbol_info, 'trade_mode') and symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
            return False
        
        if hasattr(symbol_info, 'visible') and not symbol_info.visible:
            return False
        
        tick = self.get_symbol_info_tick(mt5_symbol)
        if tick is None:
            return False
        
        if hasattr(tick, 'bid') and tick.bid > 0 and hasattr(tick, 'ask') and tick.ask > 0:
            return True
        
        return False

    def get_market_status(self, symbol: str) -> dict:
        """Returns a complete market status for a symbol."""
        mt5_symbol = self._resolve_mt5_symbol(symbol)
        symbol_info = self.get_symbol_info(mt5_symbol)
        if symbol_info is None:
            return {"open": False, "reason": "symbol_not_found"}
        
        is_open = self.is_market_open(symbol)
        session = self.get_symbol_trading_session(symbol)
        
        status = {
            "symbol": symbol,
            "resolved_symbol": mt5_symbol,
            "open": is_open,
            "trade_mode": getattr(symbol_info, 'trade_mode', None),
            "visible": getattr(symbol_info, 'visible', False),
            "session": session,
        }
        
        if not is_open:
            if hasattr(symbol_info, 'trade_mode') and symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
                status["reason"] = "trading_disabled"
            elif hasattr(symbol_info, 'visible') and not symbol_info.visible:
                status["reason"] = "not_visible"
            else:
                status["reason"] = "market_closed"
        
        return status
