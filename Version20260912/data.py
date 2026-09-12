"""Data access layer: everything that talks to yfinance lives here.

All fetch functions are wrapped with Streamlit's caching so repeated
UI interactions (switching panels, re-rendering) don't hammer Yahoo
Finance with duplicate requests.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd
import streamlit as st
import yfinance as yf

CACHE_TTL_SECONDS = 15 * 60  # 15 minutes

RANGE_OPTIONS = {
    "1M": 30,
    "3M": 90,
    "6M": 182,
    "YTD": None,  # handled specially
    "1Y": 365,
    "2Y": 730,
    "5Y": 1825,
}


@dataclass
class TickerData:
    symbol: str
    history: pd.DataFrame
    info: dict


def _date_range_for(range_key: str) -> tuple[dt.date, dt.date]:
    end = dt.date.today()
    if range_key == "YTD":
        start = dt.date(end.year, 1, 1)
    else:
        days = RANGE_OPTIONS.get(range_key, 365)
        start = end - dt.timedelta(days=days)
    return start, end


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_history(symbol: str, range_key: str = "1Y") -> pd.DataFrame:
    """Fetch daily OHLCV history for a symbol over the given range."""
    start, end = _date_range_for(range_key)
    # Add one day to `end` since yfinance's `end` is exclusive.
    df = yf.download(
        symbol,
        start=start,
        end=end + dt.timedelta(days=1),
        interval="1d",
        progress=False,
        auto_adjust=True,
        multi_level_index=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(how="all")
    df.index.name = "Date"
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_info(symbol: str) -> dict:
    """Fetch key fundamentals/company info for a symbol."""
    ticker = yf.Ticker(symbol)
    try:
        info = ticker.get_info()
    except Exception:
        info = {}
    return info or {}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_last_price(symbol: str) -> tuple[float | None, float | None]:
    """Return (last_close, pct_change_from_prev_close) for a watchlist row."""
    df = fetch_history(symbol, "1M")
    if df.empty or len(df) < 1:
        return None, None
    last_close = float(df["Close"].iloc[-1])
    if len(df) >= 2:
        prev_close = float(df["Close"].iloc[-2])
        pct_change = (last_close - prev_close) / prev_close * 100 if prev_close else None
    else:
        pct_change = None
    return last_close, pct_change


THAI_SUFFIX = ".BK"


def normalize_thai_symbol(raw_symbol: str) -> str:
    """Uppercase a symbol and append the Thai SET suffix (.BK) if missing.

    This app is restricted to Thai (SET) stocks, so any symbol typed
    without an exchange suffix is assumed to be a Thai ticker.
    """
    symbol = raw_symbol.strip().upper()
    if symbol and not symbol.endswith(THAI_SUFFIX):
        symbol = f"{symbol}{THAI_SUFFIX}"
    return symbol


def validate_symbol(symbol: str) -> bool:
    """Check whether a symbol resolves to real Thai (SET) stock data."""
    symbol = symbol.strip()
    if not symbol or not symbol.endswith(THAI_SUFFIX):
        return False
    df = fetch_history(symbol, "1M")
    return not df.empty
