"""SQLite-backed local cache for SET50 (and benchmark) daily OHLC prices.

Why: fetching ~50+ tickers fresh from yfinance on every run is slow and,
worse, a single giant multi-ticker download can silently fail or truncate
for a subset of tickers without raising an error. This module persists
whatever's been successfully fetched to a local SQLite file, so each run
only needs to fetch the *new* days since the last sync (much smaller,
much less likely to fail silently), and the app can show exactly which
ticker was last updated when.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "set50_prices.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prices (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            close REAL,
            PRIMARY KEY (ticker, date)
        )
        """
    )
    return conn


def last_date(conn: sqlite3.Connection, ticker: str) -> dt.date | None:
    row = conn.execute("SELECT MAX(date) FROM prices WHERE ticker = ?", (ticker,)).fetchone()
    if row and row[0]:
        return dt.date.fromisoformat(row[0])
    return None


def last_dates_for(conn: sqlite3.Connection, tickers: list[str]) -> dict[str, dt.date | None]:
    if not tickers:
        return {}
    placeholders = ",".join("?" * len(tickers))
    rows = conn.execute(
        f"SELECT ticker, MAX(date) FROM prices WHERE ticker IN ({placeholders}) GROUP BY ticker",
        tickers,
    ).fetchall()
    found = {t: dt.date.fromisoformat(d) for t, d in rows if d}
    return {t: found.get(t) for t in tickers}


def upsert_prices(conn: sqlite3.Connection, ticker: str, df: pd.DataFrame) -> None:
    """`df` must be indexed by date with 'Open' and 'Close' columns."""
    if df.empty:
        return
    rows = []
    for idx, row in df.iterrows():
        date_str = idx.date().isoformat() if hasattr(idx, "date") else pd.Timestamp(idx).date().isoformat()
        o = float(row["Open"]) if pd.notna(row.get("Open")) else None
        c = float(row["Close"]) if pd.notna(row.get("Close")) else None
        if c is None:
            continue
        rows.append((ticker, date_str, o, c))
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO prices (ticker, date, open, close) VALUES (?, ?, ?, ?)", rows
        )
        conn.commit()


def load_prices(
    conn: sqlite3.Connection, tickers: list[str], start: dt.date, end: dt.date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (open_df, close_df) pivoted wide (date index, ticker columns)
    from whatever's cached in the DB for [start, end]."""
    if not tickers:
        return pd.DataFrame(), pd.DataFrame()
    placeholders = ",".join("?" * len(tickers))
    query = (
        f"SELECT ticker, date, open, close FROM prices "
        f"WHERE ticker IN ({placeholders}) AND date >= ? AND date <= ? ORDER BY date"
    )
    rows = conn.execute(query, (*tickers, start.isoformat(), end.isoformat())).fetchall()
    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    long_df = pd.DataFrame(rows, columns=["ticker", "date", "open", "close"])
    long_df["date"] = pd.to_datetime(long_df["date"])
    open_df = long_df.pivot(index="date", columns="ticker", values="open")
    close_df = long_df.pivot(index="date", columns="ticker", values="close")
    open_df.index.name = "Date"
    close_df.index.name = "Date"
    return open_df, close_df


def clear_all(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM prices")
    conn.commit()
