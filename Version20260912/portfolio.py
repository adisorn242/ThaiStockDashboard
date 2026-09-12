"""SET50 equal-weight portfolio backtest: price data (SQLite-cached),
rebalancing, transaction costs, and performance metrics.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

import data as data_module
import set50_data
import set50_db

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
DAILY_UPDATE_HOUR = 18  # 18:00 Bangkok time, Mon-Fri

TRADING_DAYS_PER_YEAR = 252
RF_ANNUAL = 0.01

FEE_BPS = 15  # brokerage fee, basis points of value traded
VAT_RATE = 0.07  # 7% VAT on the fee
EFFECTIVE_COST_RATE = (FEE_BPS / 10_000) * (1 + VAT_RATE)  # ~0.001605

BENCHMARK_TICKER = "TDEX.BK"  # ThaiDEX SET50 ETF, tracks the SET50 index directly
FETCH_CHUNK_SIZE = 15  # tickers per yf.download call, to limit blast radius of a failed batch

PERIOD_OPTIONS: dict[str, pd.DateOffset | None] = {
    "Since Inception": None,
    "Last Month": pd.DateOffset(months=1),
    "Last 3 Months": pd.DateOffset(months=3),
    "Last 6 Months": pd.DateOffset(months=6),
    "Last Year": pd.DateOffset(years=1),
}


def effective_data_date(now: dt.datetime | None = None) -> dt.date:
    """The most recent date EOD data should be considered available for,
    per the 18:00 (Asia/Bangkok) Mon-Fri update cutoff."""
    now = now.astimezone(BANGKOK_TZ) if now else dt.datetime.now(BANGKOK_TZ)
    candidate = now.date()
    if now.weekday() >= 5 or now.hour < DAILY_UPDATE_HOUR:
        candidate -= dt.timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= dt.timedelta(days=1)
    return candidate


def _download_chunk(yf_tickers: list[str], start: dt.date, end: dt.date) -> dict[str, pd.DataFrame]:
    """Download Open/Close for a small batch of yfinance tickers.
    Returns {yf_ticker: DataFrame[Open, Close]}, empty dict on total failure."""
    if not yf_tickers:
        return {}
    try:
        raw = yf.download(
            yf_tickers,
            start=start,
            end=end + dt.timedelta(days=1),
            interval="1d",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
    except Exception:
        return {}
    if raw is None or raw.empty:
        return {}

    out = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for t in yf_tickers:
            if t in raw.columns.get_level_values(0):
                sub = raw[t][["Open", "Close"]].dropna(how="all")
                if not sub.empty:
                    out[t] = sub
    else:
        sub = raw[["Open", "Close"]].dropna(how="all")
        if not sub.empty:
            out[yf_tickers[0]] = sub
    return out


def sync_prices(base_tickers: list[str], start: dt.date, end: dt.date) -> dict[str, dt.date | None]:
    """Ensure the local SQLite cache has price data for `base_tickers`
    (bare SET symbols) from `start` through `end`, fetching only what's
    missing since the last sync. Returns {base_ticker: last_cached_date}
    for diagnostics (a stale/None date flags a ticker that failed to update).
    """
    conn = set50_db.get_connection()
    base_to_yf = {t: data_module.normalize_thai_symbol(t) for t in base_tickers}
    yf_to_base = {v: k for k, v in base_to_yf.items()}

    existing = set50_db.last_dates_for(conn, list(base_to_yf.values()))

    # Group tickers by the date range they still need, so a ticker that's
    # already fully cached doesn't get re-fetched.
    need_full: list[str] = []
    need_update: dict[dt.date, list[str]] = {}
    for base, yft in base_to_yf.items():
        last = existing.get(yft)
        if last is None:
            need_full.append(yft)
        elif last < end:
            need_update.setdefault(last + dt.timedelta(days=1), []).append(yft)
        # else: already up to date, nothing to fetch

    def _fetch_and_store(tickers: list[str], fetch_start: dt.date):
        for i in range(0, len(tickers), FETCH_CHUNK_SIZE):
            chunk = tickers[i : i + FETCH_CHUNK_SIZE]
            results = _download_chunk(chunk, fetch_start, end)
            for yft, df in results.items():
                set50_db.upsert_prices(conn, yft, df)

    if need_full:
        _fetch_and_store(need_full, start)
    for fetch_start, tickers in need_update.items():
        _fetch_and_store(tickers, fetch_start)

    updated = set50_db.last_dates_for(conn, list(base_to_yf.values()))
    conn.close()
    return {yf_to_base[yft]: d for yft, d in updated.items()}


def force_refresh() -> None:
    """Wipe the entire local price cache so the next sync re-fetches everything."""
    conn = set50_db.get_connection()
    set50_db.clear_all(conn)
    conn.close()


def build_ohlc_matrices(
    base_tickers: list[str], start: dt.date, end: dt.date
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dt.date | None]]:
    """Business-day (Mon-Fri) Open and Close price matrices, forward-filled
    so holidays/gaps produce a flat (0%) daily return.

    Columns are bare SET symbols (e.g. "PTT"). Returns
    (open_matrix, close_matrix, last_updated_by_ticker) where the last
    element is a diagnostic: the most recent cached date per ticker, so a
    ticker that silently stopped updating is visible rather than masked by
    forward-fill.
    """
    last_updated = sync_prices(base_tickers, start, end)

    conn = set50_db.get_connection()
    base_to_yf = {t: data_module.normalize_thai_symbol(t) for t in base_tickers}
    open_raw, close_raw = set50_db.load_prices(conn, list(base_to_yf.values()), start, end)
    conn.close()

    if close_raw.empty:
        return close_raw, close_raw, last_updated

    yf_to_base = {v: k for k, v in base_to_yf.items()}
    open_raw = open_raw.rename(columns=yf_to_base)
    close_raw = close_raw.rename(columns=yf_to_base)

    business_days = pd.bdate_range(start, end)
    close_matrix = close_raw.reindex(business_days).ffill().bfill()
    close_matrix.index.name = "Date"

    open_matrix = open_raw.reindex(business_days)
    open_matrix = open_matrix.fillna(close_matrix)  # holiday/gap day: no trade, flat at close
    open_matrix.index.name = "Date"

    return open_matrix, close_matrix, last_updated


def _month_start_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """First available trading day of each calendar month within `index`,
    plus the very first date (initial investment)."""
    dates = [index[0]]
    months_seen = {(index[0].year, index[0].month)}
    for d in index[1:]:
        key = (d.year, d.month)
        if key not in months_seen:
            months_seen.add(key)
            dates.append(d)
    return dates


def run_equal_weight_backtest(
    open_matrix: pd.DataFrame,
    close_matrix: pd.DataFrame,
    apply_costs: bool = True,
) -> dict:
    """Equal-weight SET50 portfolio, rebalanced to the current period's
    constituent list on the first trading day of every month.

    Trades execute at that day's OPEN price (including the very first,
    initial investment); daily portfolio value is marked at each day's
    CLOSE price, so returns used for metrics are close-to-close.

    Returns {'value': cumulative value series (base 100), 'rebalance_log': [...]}.
    """
    idx = close_matrix.index
    rebalance_dates = _month_start_rebalance_dates(idx)

    value_series = pd.Series(index=idx, dtype=float)
    portfolio_value = 100.0
    shares: dict[str, float] = {}
    rebalance_log = []

    for i, date in enumerate(idx):
        if date in rebalance_dates:
            target_tickers, period = set50_data.constituents_for_date(date.date())
            available = [
                t for t in target_tickers
                if t in open_matrix.columns and pd.notna(open_matrix.loc[date, t]) and open_matrix.loc[date, t] > 0
            ]

            if i > 0:
                # Mark existing holdings at today's OPEN (the execution price).
                portfolio_value = sum(
                    shares.get(t, 0) * open_matrix.loc[date, t] for t in shares if t in open_matrix.columns
                )

            if available:
                weight = 1.0 / len(available)
                old_value_by_ticker = {
                    t: shares.get(t, 0) * open_matrix.loc[date, t]
                    for t in (set(shares) | set(available))
                    if t in open_matrix.columns
                }
                target_value_by_ticker = {t: portfolio_value * weight for t in available}
                turnover = sum(
                    abs(target_value_by_ticker.get(t, 0) - old_value_by_ticker.get(t, 0))
                    for t in set(old_value_by_ticker) | set(target_value_by_ticker)
                )
                cost = turnover * EFFECTIVE_COST_RATE if apply_costs else 0.0
                portfolio_value -= cost
                shares = {t: (portfolio_value * weight) / open_matrix.loc[date, t] for t in available}

                rebalance_log.append(
                    {
                        "date": date.date().isoformat(),
                        "n_holdings": len(available),
                        "period_source": period["source"] if period else "n/a",
                        "is_initial": i == 0,
                        "turnover_value": round(turnover, 2),
                        "cost": round(cost, 4),
                    }
                )

        value_series.loc[date] = sum(
            shares.get(t, 0) * close_matrix.loc[date, t] for t in shares if t in close_matrix.columns
        )

    return {"value": value_series, "rebalance_log": rebalance_log}


def run_weighted_backtest(
    open_matrix: pd.DataFrame,
    close_matrix: pd.DataFrame,
    weights_by_date: dict[pd.Timestamp, dict[str, float]],
    apply_costs: bool = True,
    cash_rate_annual: float = 0.0,
) -> dict:
    """Generic monthly-rebalanced backtest driven by externally supplied
    target weights (used by the A2C strategy) rather than an equal-weight
    rule. `weights_by_date` maps each rebalance date to a
    {ticker: weight} dict; weights for a date may sum to less than 1 --
    the shortfall is held as cash, which accrues `cash_rate_annual`
    (simple interest, prorated by calendar days) between rebalances.
    There is no renormalization: a ticker's weight is applied directly
    against portfolio value, whatever isn't assigned to a ticker is cash.

    Same OPEN-to-trade / CLOSE-to-value convention as
    run_equal_weight_backtest, including paying transaction costs on the
    very first (initial) investment.

    Returns {'value': cumulative value series (base 100), 'rebalance_log': [...]}.
    """
    idx = close_matrix.index
    daily_cash_rate = cash_rate_annual / 365.0

    value_series = pd.Series(index=idx, dtype=float)
    portfolio_value = 100.0
    shares: dict[str, float] = {}
    cash_value = 100.0  # starts fully in cash until the first rebalance with data
    rebalance_log = []
    prev_date: pd.Timestamp | None = None

    for i, date in enumerate(idx):
        if prev_date is not None and cash_value:
            days_elapsed = (date - prev_date).days
            cash_value *= (1 + daily_cash_rate) ** days_elapsed

        if date in weights_by_date:
            target_weights = weights_by_date[date]

            if i > 0:
                portfolio_value = (
                    sum(shares.get(t, 0) * open_matrix.loc[date, t] for t in shares if t in open_matrix.columns)
                    + cash_value
                )

            available_targets = {
                t: w for t, w in target_weights.items()
                if t in open_matrix.columns and pd.notna(open_matrix.loc[date, t]) and open_matrix.loc[date, t] > 0 and w > 0
            }

            old_value_by_ticker = {
                t: shares.get(t, 0) * open_matrix.loc[date, t]
                for t in (set(shares) | set(available_targets))
                if t in open_matrix.columns
            }
            target_value_by_ticker = {t: portfolio_value * w for t, w in available_targets.items()}
            turnover = sum(
                abs(target_value_by_ticker.get(t, 0) - old_value_by_ticker.get(t, 0))
                for t in set(old_value_by_ticker) | set(target_value_by_ticker)
            )
            cost = turnover * EFFECTIVE_COST_RATE if apply_costs else 0.0
            portfolio_value -= cost

            invested_weight = sum(available_targets.values())
            cash_weight = max(0.0, 1.0 - invested_weight)
            cash_value = portfolio_value * cash_weight
            shares = {t: (portfolio_value * w) / open_matrix.loc[date, t] for t, w in available_targets.items()}

            rebalance_log.append(
                {
                    "date": date.date().isoformat(),
                    "n_holdings": len(available_targets),
                    "cash_weight": round(cash_weight, 4),
                    "is_initial": i == 0,
                    "turnover_value": round(turnover, 2),
                    "cost": round(cost, 4),
                }
            )

        value_series.loc[date] = (
            sum(shares.get(t, 0) * close_matrix.loc[date, t] for t in shares if t in close_matrix.columns)
            + cash_value
        )
        prev_date = date

    return {"value": value_series, "rebalance_log": rebalance_log}


def _fetch_index_history(ticker: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """Fetch OHLC for a single index ticker via yf.Ticker().history().

    Index-like tickers (e.g. the TDEX SET50 ETF) are fetched through Ticker.history() rather
    than the batched multi-ticker yf.download() path used for individual
    stocks: batch downloads for a single index ticker are more prone to
    silently returning a truncated range (which, combined with
    forward-fill, looks like the price going flat) — this is a distinct,
    more reliable code path specifically to avoid that failure mode.
    """
    try:
        hist = yf.Ticker(ticker).history(
            start=start, end=end + dt.timedelta(days=1), interval="1d", auto_adjust=True
        )
    except Exception:
        return pd.DataFrame()
    if hist is None or hist.empty:
        return pd.DataFrame()
    hist = hist[["Open", "Close"]].dropna(how="all")
    hist.index = pd.to_datetime(hist.index.date)  # drop timezone/intraday component
    return hist


def sync_index_price(ticker: str, start: dt.date, end: dt.date) -> dt.date | None:
    """Incrementally sync a single index ticker (see _fetch_index_history).
    Returns the most recent cached date for this ticker, or None if it has
    no data at all — the caller should treat a date older than expected as
    a sign this ticker's feed has stalled."""
    conn = set50_db.get_connection()
    last = set50_db.last_date(conn, ticker)
    fetch_start = start if last is None else last + dt.timedelta(days=1)
    if fetch_start <= end:
        hist = _fetch_index_history(ticker, fetch_start, end)
        set50_db.upsert_prices(conn, ticker, hist)
    updated_last = set50_db.last_date(conn, ticker)
    conn.close()
    return updated_last


def fetch_benchmark(start: dt.date, end: dt.date) -> tuple[pd.Series, dt.date | None]:
    """TDEX (ThaiDEX SET50 ETF), close-only, indexed to 100 at `start`.
    Returns (series, last_cached_date) — the date lets the caller flag a
    stalled benchmark feed the same way stock ticker staleness is flagged."""
    last_updated = sync_index_price(BENCHMARK_TICKER, start, end)

    conn = set50_db.get_connection()
    _, close_raw = set50_db.load_prices(conn, [BENCHMARK_TICKER], start, end)
    conn.close()
    if close_raw.empty or BENCHMARK_TICKER not in close_raw.columns:
        return pd.Series(dtype=float), last_updated

    business_days = pd.bdate_range(start, end)
    series = close_raw[BENCHMARK_TICKER].reindex(business_days).ffill().bfill()
    return series / series.iloc[0] * 100.0, last_updated


def window_and_rebase(series: pd.Series, period_label: str) -> tuple[pd.Series, bool]:
    """Slice `series` to the requested trailing window and rebase it to
    100 at the window's start. Returns (windowed_series, was_clipped) where
    was_clipped is True if the requested window exceeds available history
    (in which case the full series is returned instead)."""
    offset = PERIOD_OPTIONS.get(period_label)
    if offset is None or series.empty:
        return series, False

    end = series.index[-1]
    desired_start = end - offset
    clipped = desired_start < series.index[0]
    start = max(desired_start, series.index[0])
    sliced = series[series.index >= start]
    if sliced.empty or sliced.iloc[0] == 0:
        return series, False
    rebased = sliced / sliced.iloc[0] * 100.0
    return rebased, clipped


def compute_metrics(value_series: pd.Series, rf_annual: float = RF_ANNUAL) -> dict:
    """All performance metrics, computed from a cumulative value series."""
    returns = value_series.pct_change().dropna()
    n_days = len(returns)
    if n_days == 0:
        return {}

    cumulative_return = value_series.iloc[-1] / value_series.iloc[0] - 1
    annualized_return = (1 + cumulative_return) ** (TRADING_DAYS_PER_YEAR / n_days) - 1
    annualized_std = returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    rf_daily = rf_annual / TRADING_DAYS_PER_YEAR
    sharpe = (annualized_return - rf_annual) / annualized_std if annualized_std else np.nan

    downside = returns[returns < rf_daily] - rf_daily
    downside_std = downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR) if len(downside) > 0 else np.nan
    sortino = (annualized_return - rf_annual) / downside_std if downside_std else np.nan

    running_max = value_series.cummax()
    drawdown = value_series / running_max - 1
    max_drawdown = drawdown.min()

    calmar = annualized_return / abs(max_drawdown) if max_drawdown else np.nan

    var_95 = -np.percentile(returns, 5)
    tail_losses = returns[returns <= np.percentile(returns, 5)]
    cvar_95 = -tail_losses.mean() if len(tail_losses) > 0 else np.nan

    return {
        "Cumulative Return": cumulative_return,
        "Annualized Return": annualized_return,
        "Annualized Risk (Std)": annualized_std,
        "Sharpe Ratio": sharpe,
        "Sortino Ratio": sortino,
        "Calmar Ratio": calmar,
        "Maximum Drawdown": max_drawdown,
        "Daily 95% VaR": var_95,
        "Daily 95% CVaR": cvar_95,
    }
