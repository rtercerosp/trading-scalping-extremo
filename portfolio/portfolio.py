# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import MetaTrader5 as mt5
from typing import Dict
from utils.symbol_utils import CRYPTO_SYMBOLS, get_asset_category, normalize_symbol

class Portfolio():
    def __init__(self, magic_number: int, max_total_positions: int = 999, max_positions_per_symbol: int = 99, max_positions_by_symbol: Dict[str, int] | None = None, max_positions_by_category: Dict[str, int] | None = None, max_notional_pct_per_trade: float = 0.25, connector=None):
        self.magic = magic_number
        self.max_total_positions = max_total_positions
        self.max_positions_per_symbol = max_positions_per_symbol
        self.max_positions_by_symbol = {
            normalize_symbol(symbol): limit for symbol, limit in (max_positions_by_symbol or {}).items()
        }
        self.max_positions_by_category = max_positions_by_category or {}
        self._crypto_symbols = CRYPTO_SYMBOLS
        self.max_notional_pct_per_trade = max_notional_pct_per_trade
        self.connector = connector

    def _safe_positions_get(self, symbol: str | None = None) -> tuple:
        """
        Returns a tuple even when MT5 responds with None.
        """
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return tuple()
        return tuple(positions)

    def _get_asset_category(self, symbol: str) -> str:
        return get_asset_category(symbol)

    def get_open_positions(self) -> tuple:
        """
        Retrieves the open positions from the MetaTrader 5 platform.

        Returns:
            tuple: A tuple containing the open positions.
        """
        return self._safe_positions_get()

    def get_strategy_open_positions(self) -> tuple:
        """
        Retrieves the open positions for the strategy.

        Returns:
            tuple: A tuple containing the open positions for the strategy.
        """
        positions = []
        for position in self._safe_positions_get():
            if position.magic == self.magic:
                positions.append(position)

        return tuple(positions)

    def get_number_of_open_positions_by_symbol(self, symbol: str) -> Dict[str, int]:
        """
        Get the number of open positions for a given symbol.

        Args:
            symbol (str): The symbol for which to retrieve the open positions.

        Returns:
            Dict[str, int]: A dictionary containing the count of long positions, short positions, and total positions.

        """
        longs = 0
        shorts = 0
        for position in self._safe_positions_get(symbol=symbol):
            if position.type == mt5.ORDER_TYPE_BUY:
                longs += 1
            else:
                shorts += 1

        return {"LONG": longs, "SHORT": shorts, "TOTAL": longs + shorts}

    def get_number_of_strategy_open_positions_by_symbol(self, symbol: str) -> Dict[str, int]:
        """
        Get the number of open positions for a given symbol in the strategy's portfolio.

        Args:
            symbol (str): The symbol for which to count the open positions.

        Returns:
            Dict[str, int]: A dictionary containing the count of long positions, short positions, and the total count.

        """
        longs = 0
        shorts = 0
        normalized_symbol = normalize_symbol(symbol)

        for position in self._safe_positions_get(symbol=normalized_symbol):
            if position.magic == self.magic:
                if position.type == mt5.ORDER_TYPE_BUY:
                    longs += 1
                else:
                    shorts += 1

        return {"LONG": longs, "SHORT": shorts, "TOTAL": longs + shorts}

    def get_strategy_open_positions_by_symbol(self, symbol: str) -> tuple:
        """
        Retrieves the open positions for the strategy for a specific symbol.

        Args:
            symbol (str): The symbol to filter positions by.

        Returns:
            tuple: A tuple containing the open positions for the strategy matching the symbol.
        """
        normalized_symbol = normalize_symbol(symbol)
        positions = []
        for position in self._safe_positions_get(symbol=normalized_symbol):
            if position.magic == self.magic:
                positions.append(position)

        return tuple(positions)

    def get_total_strategy_positions(self) -> int:
        """
        Returns the total number of open positions for the strategy.

        Returns:
            int: The total number of open positions.
        """
        return len(self.get_strategy_open_positions())

    def _get_position_notional_acc_ccy(self, position) -> float:
        if self.connector is None:
            return 0.0
        try:
            symbol_info = self.connector.get_symbol_info(position.symbol)
            account_info = self.connector.get_account_info()
            if symbol_info is None or account_info is None:
                return 0.0
            price = position.price_open
            volume = position.volume
            contract_size = getattr(symbol_info, 'trade_contract_size', 0.0)
            if contract_size <= 0 or price <= 0 or volume <= 0:
                return 0.0
            notional = price * volume * contract_size
            if getattr(symbol_info, 'currency_profit', '') != getattr(account_info, 'currency', ''):
                return self.connector.convert_currency_amount_to_another_currency(notional, symbol_info.currency_profit, account_info.currency) or 0.0
            return notional
        except Exception:
            return 0.0

    def _get_total_open_notional_acc_ccy(self) -> float:
        total = 0.0
        for position in self.get_strategy_open_positions():
            total += self._get_position_notional_acc_ccy(position)
        return total

    def can_open_position(self, symbol: str, boost_multiplier: float = 1.0, new_position_notional: float = 0.0) -> bool:
        """
        Checks if a new position can be opened based on portfolio limits.

        Args:
            symbol (str): The symbol to check.
            boost_multiplier (float): Multiplicador de límite para el mejor activo.
            new_position_notional (float): Notional estimado de la nueva posición en moneda de cuenta.

        Returns:
            bool: True if a new position can be opened, False otherwise.
        """
        total_positions = self.get_total_strategy_positions()
        if total_positions >= self.max_total_positions:
            return False

        symbol_positions = self.get_number_of_strategy_open_positions_by_symbol(symbol)
        max_for_symbol = self.max_positions_by_symbol.get(normalize_symbol(symbol), self.max_positions_per_symbol)
        if boost_multiplier > 1.0:
            max_for_symbol = max(1, int(max_for_symbol * boost_multiplier))
        if symbol_positions["TOTAL"] >= max_for_symbol:
            return False

        category = self._get_asset_category(symbol)
        max_for_category = self.max_positions_by_category.get(category)
        if max_for_category is not None:
            category_positions = sum(
                1 for p in self.get_strategy_open_positions()
                if self._get_asset_category(p.symbol) == category
            )
            if category_positions >= max_for_category:
                return False

        if self.max_notional_pct_per_trade > 0 and new_position_notional > 0 and self.connector is not None:
            try:
                account_info = self.connector.get_account_info()
                if account_info and account_info.equity > 0:
                    max_notional = account_info.equity * self.max_notional_pct_per_trade
                    if new_position_notional > max_notional:
                        return False
            except Exception:
                pass

        return True

    def get_portfolio_summary(self) -> dict:
        """
        Returns a summary of the portfolio.

        Returns:
            dict: A dictionary containing portfolio summary information.
        """
        all_positions = self.get_strategy_open_positions()
        total_positions = len(all_positions)
        symbols = {}
        category_counts = {"crypto": 0, "gold": 0, "forex": 0, "index": 0, "commodity": 0}
        for position in all_positions:
            if position.symbol not in symbols:
                symbols[position.symbol] = 0
            symbols[position.symbol] += 1
            cat = self._get_asset_category(position.symbol)
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_positions": total_positions,
            "max_total_positions": self.max_total_positions,
            "symbols": symbols,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "category_counts": category_counts,
            "max_positions_by_category": self.max_positions_by_category,
        }

    def get_initial_portfolio_status_message(self) -> str | None:
        """
        Generates a message detailing preexisting positions for the strategy.

        Returns:
            str | None: A summary message if positions exist, otherwise None.
        """
        summary = self.get_portfolio_summary()
        total_positions = summary.get("total_positions", 0)

        if total_positions == 0:
            return None

        symbols_breakdown = summary.get("symbols", {})
        breakdown_str_parts = []
        for symbol, count in symbols_breakdown.items():
            breakdown_str_parts.append(f"{symbol} ({count})")
        
        breakdown_str = ", ".join(breakdown_str_parts)

        message = (
            f"PORTFOLIO: Se han detectado {total_positions} posiciones preexistentes para el Magic Number {self.magic} "
            f"que cuentan para el límite de {self.max_total_positions} posiciones totales.\n"
            f"Desglose por símbolo: {breakdown_str}"
        )
        return message
