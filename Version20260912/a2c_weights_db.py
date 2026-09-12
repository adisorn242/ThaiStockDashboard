"""SQLite-backed cache of each A2C model's computed monthly target weights.

Why: replaying a model's policy forward (fetch prices -> resample ->
`model.predict()` for every month since its training cutoff) is the
expensive part of `a2c_strategy.py`, and Streamlit's own `st.cache_data`
is in-memory only -- it's wiped on every server restart and re-keyed
every time the daily `as_of` cache-bust changes, so in practice the full
replay was being redone from scratch on effectively every fresh run.

This module persists each model's weights for months that are fully
*closed* (the month has ended, so the model's decision for it can never
change) to a local SQLite file. On a later run, only the months after
the last cached one need to be computed -- and only a small trailing
window of price history (just enough to seed the lookback observation)
needs to be fetched, not the model's entire history. The current,
still-in-progress month is never cached (its trailing return data can
still shift while the month is open), so it's always recomputed fresh,
which is cheap since it's just one extra step.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "a2c_weights_cache.db"


def get_connection():
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS a2c_weights (
            model_name TEXT NOT NULL,
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY (model_name, date, ticker)
        )
        """
    )
    return conn


def last_closed_date(conn, model_name: str, before: dt.date) -> dt.date | None:
    """Latest cached date for this model that is strictly before `before`
    (i.e. the start of the current, still-open month)."""
    row = conn.execute(
        "SELECT MAX(date) FROM a2c_weights WHERE model_name = ? AND date < ?",
        (model_name, before.isoformat()),
    ).fetchone()
    if row and row[0]:
        return dt.date.fromisoformat(row[0])
    return None


def load_closed_weights(conn, model_name: str, tickers: list[str], before: dt.date) -> pd.DataFrame:
    """All cached rows for this model with date < `before`, pivoted wide
    (date index, ticker columns) -- same shape `_weights_sequence_for_model`
    returns."""
    rows = conn.execute(
        "SELECT date, ticker, weight FROM a2c_weights WHERE model_name = ? AND date < ? ORDER BY date",
        (model_name, before.isoformat()),
    ).fetchall()
    if not rows:
        return pd.DataFrame(columns=tickers)
    long_df = pd.DataFrame(rows, columns=["date", "ticker", "weight"])
    long_df["date"] = pd.to_datetime(long_df["date"])
    wide = long_df.pivot(index="date", columns="ticker", values="weight")
    wide.index.name = None
    return wide.reindex(columns=tickers)


def upsert_weights(conn, model_name: str, date: pd.Timestamp, weights: dict) -> None:
    date_str = pd.Timestamp(date).date().isoformat()
    rows = [(model_name, date_str, ticker, float(w)) for ticker, w in weights.items()]
    if not rows:
        return
    conn.executemany(
        "INSERT OR REPLACE INTO a2c_weights (model_name, date, ticker, weight) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
