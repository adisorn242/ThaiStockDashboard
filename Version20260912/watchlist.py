"""Local JSON-backed watchlist persistence."""
from __future__ import annotations

import json
from pathlib import Path

WATCHLIST_PATH = Path(__file__).parent / "watchlist.json"

DEFAULT_WATCHLIST = ["PTT.BK", "AOT.BK", "CPALL.BK"]


def load_watchlist() -> list[str]:
    if not WATCHLIST_PATH.exists():
        save_watchlist(DEFAULT_WATCHLIST)
        return list(DEFAULT_WATCHLIST)
    try:
        data = json.loads(WATCHLIST_PATH.read_text())
        if isinstance(data, list):
            return [str(s).upper() for s in data]
    except (json.JSONDecodeError, OSError):
        pass
    return list(DEFAULT_WATCHLIST)


def save_watchlist(tickers: list[str]) -> None:
    WATCHLIST_PATH.write_text(json.dumps(tickers, indent=2))


def add_ticker(tickers: list[str], symbol: str) -> list[str]:
    symbol = symbol.strip().upper()
    if symbol and symbol not in tickers:
        tickers = [*tickers, symbol]
        save_watchlist(tickers)
    return tickers


def remove_ticker(tickers: list[str], symbol: str) -> list[str]:
    symbol = symbol.strip().upper()
    tickers = [t for t in tickers if t != symbol]
    save_watchlist(tickers)
    return tickers
