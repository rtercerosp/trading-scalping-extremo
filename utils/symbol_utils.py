from __future__ import annotations

CRYPTO_SYMBOLS = {
    "BTCUSD",
    "ETHUSD",
    "XRPUSD",
    "SOLUSD",
    "ADAUSD",
    "DOGEUSD",
    "MATICUSD",
    "AVAXUSD",
    "DOTUSD",
    "LINKUSD",
    "UNIUSD",
    "LTCUSD",
    "BCHUSD",
    "XLMUSD",
    "ATOMUSD",
    "FILUSD",
    "APTUSD",
    "OPUSD",
    "ARBUSD",
    "INJUSD",
}

GOLD_SYMBOLS = {"XAUUSD", "GOLD"}
FOREX_SYMBOLS = {
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "NZDUSD",
    "USDCAD",
    "USDSEK",
    "USDNOK",
    "EURGBP",
    "EURJPY",
    "GBPJPY",
    "AUDJPY",
    "EURAUD",
    "EURCHF",
    "GBPCHF",
    "AUDCAD",
    "NZDJPY",
    "CADJPY",
    "CHFJPY",
    "GBPAUD",
    "GBPCAD",
    "EURCAD",
    "EURNZD",
    "AUDNZD",
    "AUDCHF",
    "AUDSGD",
    "CADCHF",
    "EURHKD",
    "EURSGD",
    "GBPHKD",
    "GBPSGD",
    "HKDJPY",
    "NZDSGD",
    "SGDJPY",
    "USDSGD",
    "USDHKD",
}

KNOWN_SYMBOLS = CRYPTO_SYMBOLS | GOLD_SYMBOLS | FOREX_SYMBOLS
_SUFFIX_CHARS = set("CM+._-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def normalize_symbol(symbol: str) -> str:
    if not symbol:
        return ""

    upper = symbol.strip().upper()
    if upper in KNOWN_SYMBOLS:
        return upper

    if upper.startswith("XAUUSD"):
        return "XAUUSD"

    for base_symbol in sorted(KNOWN_SYMBOLS, key=len, reverse=True):
        if not upper.startswith(base_symbol):
            continue
        suffix = upper[len(base_symbol):]
        if suffix and all(char in _SUFFIX_CHARS for char in suffix):
            return base_symbol

    return upper


def get_asset_category(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if normalized in CRYPTO_SYMBOLS:
        return "crypto"
    if normalized in GOLD_SYMBOLS:
        return "gold"
    return "forex"


def symbol_matches(symbol: str, aliases: list[str] | tuple[str, ...] | set[str]) -> bool:
    normalized_symbol = normalize_symbol(symbol)
    return normalized_symbol in {normalize_symbol(alias) for alias in aliases}
