#!/usr/bin/env python3
"""Verificador de integridad de la versión V9_SCALPING_MAX_QUALITY."""

import hashlib
import sys
from pathlib import Path

FILES_TO_CHECK = [
    "brain/models.py",
    "brain/trade_history_manager.py",
    "brain/performance_tracker.py",
    "brain/trading_brain.py",
    "trading_director/trading_director.py",
    "signal_generator/signal_generator.py",
    "events/events.py",
    "data_provider/data_provider.py",
    "order_executor/order_executor.py",
    "order_executor/break_even_manager.py",
    "position_sizer/position_sizer.py",
    "risk_manager/risk_manager.py",
    "signal_generator/signals/signal_trend_pullback.py",
    "signal_generator/signals/signal_smart_money_btc.py",
    "signal_generator/signals/signal_smart_money_eth.py",
    "signal_generator/signals/signal_smart_money_eurusd.py",
    "news/news_protection.py",
    "tests/test_trend_pullback_strategy.py",
    "tests/test_refactoring.py",
    "ai/__init__.py",
    "V9_SCALPING_MAX_QUALITY_REPORT.md",
    "version_snapshot_V9.txt",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parent
    missing = []
    ok = []
    for rel in FILES_TO_CHECK:
        p = root / rel
        if not p.exists():
            missing.append(rel)
            continue
        try:
            digest = sha256(p)
            ok.append((rel, digest))
        except Exception as e:
            missing.append(f"{rel} (error lectura: {e})")

    print("Verificacion V9_SCALPING_MAX_QUALITY")
    print(f"Archivos esperados: {len(FILES_TO_CHECK)}")
    print(f"Archivos ok: {len(ok)}")
    print(f"Archivos faltantes/con error: {len(missing)}")
    if missing:
        print("FALTANTES/ERRORES:")
        for item in missing:
            print(f" - {item}")
        return 1

    print("Integridad: OK")
    print("\nArchivos y SHA256:")
    for rel, digest in ok:
        print(f" {digest}  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
