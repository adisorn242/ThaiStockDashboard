"""A2C reinforcement-learning portfolio strategy: fully automatic.

On each dashboard load (refreshed once per day), this module:

1. Downloads every model (.zip) + metadata (.json) pair from a shared
   Google Drive folder (DRIVE_FOLDER_URL below -- set once, not
   user-configured) and pairs them up by filename.
2. For each month, picks the most recently trained model whose training
   data doesn't look into that month's future (point-in-time correct) --
   so a newer model you drop into the same Drive folder later is picked
   up automatically, with no period-name matching or manual switching.
3. Replays each model's policy forward from its own training cutoff to
   get raw monthly target weights (same math as training: softmax
   action -> weights, drift with realized returns between decisions).
4. Applies three overlay rules to the raw weights every month, with NO
   redistribution -- trimmed/excluded weight simply becomes idle cash:
   restrict to current SET50 members, floor weights below MIN_WEIGHT,
   cap weights above MAX_WEIGHT. Cash earns CASH_RATE_NET_ANNUAL (simple
   interest, prorated by calendar days) until the next rebalance.

Nothing here needs the user to run a notebook, upload a file, or paste a
URL -- the dashboard just shows the result.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

import a2c_weights_db
import portfolio
import set50_data

DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1pYcgc8kozR1NCcXuo-OsrcLgB3PAJjXe?usp=sharing"
MODEL_CACHE_DIR = Path(__file__).parent / "a2c_model_cache"

MIN_WEIGHT = 0.01  # floor: weights below 1% are excluded, not redistributed
MAX_WEIGHT = 0.10  # cap: weights above 10% are trimmed, excess is not redistributed

CASH_RATE_GROSS_ANNUAL = 0.0025   # 0.25% / year
WITHHOLDING_TAX_RATE = 0.15       # 15% withholding tax on the interest
CASH_RATE_NET_ANNUAL = CASH_RATE_GROSS_ANNUAL * (1 - WITHHOLDING_TAX_RATE)  # 0.2125% / year

STRATEGY_NAME = "A2C RL Strategy"


# ---------------------------------------------------------------------------
# Model discovery / loading (Drive folder -> paired, loaded models)
# ---------------------------------------------------------------------------

SYNC_MARKER_PATH = MODEL_CACHE_DIR / ".last_synced"


def _already_synced_today(today_iso: str) -> bool:
    try:
        return SYNC_MARKER_PATH.read_text().strip() == today_iso
    except FileNotFoundError:
        return False


def _mark_synced(today_iso: str) -> None:
    try:
        SYNC_MARKER_PATH.write_text(today_iso)
    except OSError:
        pass


def _download_models(today_iso: str) -> None:
    """Only hits Drive if today's sync hasn't already happened -- this
    marker file is what lets a fresh `streamlit run` restart skip the
    download entirely (not just a same-process Streamlit cache hit) when
    it already ran once today."""
    import gdown

    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    if _already_synced_today(today_iso) and any(MODEL_CACHE_DIR.glob("*.zip")):
        return
    gdown.download_folder(DRIVE_FOLDER_URL, output=str(MODEL_CACHE_DIR), quiet=True, use_cookies=False)
    _mark_synced(today_iso)


def _stem_suffix(path: Path, markers: tuple[str, ...]) -> str:
    name = path.stem
    for marker in markers:
        idx = name.find(marker)
        if idx != -1:
            return name[idx + len(marker):]
    return name


def _discover_and_load_models() -> list[dict]:
    """Pair every *_model_<suffix>.zip with its *_metadata_<suffix>.json in
    MODEL_CACHE_DIR (whatever is currently cached, even from a previous
    run) and load each. Unpaired or unreadable files are skipped, not
    fatal."""
    from stable_baselines3 import A2C

    if not MODEL_CACHE_DIR.exists():
        return []

    zip_files = sorted(MODEL_CACHE_DIR.glob("*.zip"))
    json_files = sorted(MODEL_CACHE_DIR.glob("*.json"))
    json_by_suffix = {_stem_suffix(p, ("metadata_", "metadata")): p for p in json_files}

    models = []
    for zip_path in zip_files:
        suffix = _stem_suffix(zip_path, ("model_", "model"))
        json_path = json_by_suffix.get(suffix)
        if json_path is None:
            continue
        try:
            metadata = json.loads(json_path.read_text())
            model = A2C.load(str(zip_path))
        except Exception:
            continue
        models.append(
            {
                "name": suffix or zip_path.stem,
                "model": model,
                "tickers": metadata["tickers"],
                "lookback": metadata["lookback"],
                "train_start_date": metadata["train_start_date"],
                "train_end_date": metadata["train_end_date"],
            }
        )
    return models


@st.cache_resource(show_spinner="Fetching A2C models...")
def _load_models_cached(_cache_bust: str) -> tuple[list[dict], list[str]]:
    """`_cache_bust` (the effective data date) changes once per day, so
    within a single running server process this only re-executes at most
    once a day. On top of that, `_download_models` checks a marker file
    on disk (not just Streamlit's in-memory cache), so restarting the app
    later the same day skips the Drive download too -- not just a rerun
    within the same process. If the Drive refresh itself fails, whatever's
    already cached locally from a previous successful run is still used."""
    warnings: list[str] = []
    try:
        _download_models(_cache_bust)
    except Exception as e:
        warnings.append(f"Couldn't refresh A2C models from Drive ({e}) — using the last successfully downloaded copy, if any.")
    models = _discover_and_load_models()
    if not models:
        warnings.append("No A2C model/metadata pairs found.")
    return models, warnings


def get_models() -> tuple[list[dict], list[str]]:
    cache_bust = portfolio.effective_data_date().isoformat()
    return _load_models_cached(cache_bust)


# ---------------------------------------------------------------------------
# Per-model inference (price fetch + policy replay -> raw monthly weights)
# ---------------------------------------------------------------------------

def _fetch_prices_for_universe(tickers: list[str], start: dt.date, end: dt.date) -> tuple[pd.DataFrame, pd.DataFrame]:
    open_records, close_records = {}, {}
    for base in tickers:
        yft = f"{base}.BK"
        try:
            hist = yf.Ticker(yft).history(start=start, end=end + dt.timedelta(days=1), auto_adjust=False)
            hist = hist[["Open", "Close"]].dropna()
        except Exception:
            hist = pd.DataFrame()
        if not hist.empty:
            hist.index = pd.to_datetime(hist.index.date)
            open_records[base] = hist["Open"]
            close_records[base] = hist["Close"]

    open_df = pd.DataFrame(open_records).sort_index()
    close_df = pd.DataFrame(close_records).sort_index()

    # Keep the model's full trained universe even if a ticker's fetch failed
    # entirely -- fill it flat (0% return) rather than breaking the fixed
    # observation-vector shape the model expects.
    for t in tickers:
        if t not in close_df.columns:
            close_df[t] = 1.0
            open_df[t] = 1.0
    open_df = open_df.reindex(columns=tickers)
    close_df = close_df.reindex(columns=tickers)

    business_days = pd.bdate_range(start, end)
    close_df = close_df.reindex(business_days).ffill().bfill()
    open_df = open_df.reindex(business_days).ffill().bfill()
    return open_df, close_df


@st.cache_data(show_spinner="Computing A2C model weights...")
def _weights_sequence_for_model(
    model_name: str,
    _model,
    tickers: tuple[str, ...],
    lookback: int,
    train_start_date: str,
    train_end_date: str,
    as_of: str,
) -> pd.DataFrame:
    """Replays `_model`'s policy forward from `train_end_date` through
    `as_of`, returning a DataFrame indexed by month (the month each row's
    allocation is FOR), columns = tickers, values = raw (pre-overlay)
    model weights. Empty if fewer than `lookback` months of post-training
    data are available yet.

    Months that have already fully closed are persisted to
    `a2c_weights_cache.db` (see a2c_weights_db.py) the first time they're
    computed. On later calls, only the months after the last cached one
    are replayed -- and only a small trailing window of price history
    (just enough to seed the lookback observation) is fetched, not the
    model's entire history since its training cutoff. The current,
    still-open month is always recomputed fresh (cheap: one extra step)
    since its trailing return data can still shift while the month is
    open.
    """
    tickers = list(tickers)
    as_of_date = dt.date.fromisoformat(as_of)
    current_month_start = as_of_date.replace(day=1)
    train_start = dt.date.fromisoformat(train_start_date)
    train_end_ts = pd.Timestamp(train_end_date)

    conn = a2c_weights_db.get_connection()
    try:
        cached = a2c_weights_db.load_closed_weights(conn, model_name, tickers, current_month_start)
        resume_date = a2c_weights_db.last_closed_date(conn, model_name, current_month_start)

        def replay(first_predict_pos, weights, returns_df):
            records = []
            for t in range(first_predict_pos, len(returns_df) + 1):
                obs_window = returns_df.iloc[t - lookback:t].values.astype(np.float32)
                obs = np.concatenate([obs_window.flatten(), weights]).astype(np.float32)

                action, _ = _model.predict(obs, deterministic=True)
                logits = np.clip(action, -5, 5)
                exp = np.exp(logits - np.max(logits))
                target_weights = exp / np.sum(exp)

                target_date = returns_df.index[t] if t < len(returns_df) else returns_df.index[-1] + pd.DateOffset(months=1)
                target_dict = dict(zip(tickers, target_weights.tolist()))
                records.append({"date": target_date, **target_dict})

                # Only persist months that have fully closed by `as_of` --
                # the current, still-forming month's trailing return can
                # still shift, so it's left to be recomputed next time.
                if target_date.date().replace(day=1) < current_month_start:
                    a2c_weights_db.upsert_weights(conn, model_name, target_date, target_dict)

                if t < len(returns_df):
                    day_returns = returns_df.iloc[t].values
                    drifted = target_weights * (1 + day_returns)
                    total = drifted.sum()
                    weights = (drifted / total).astype(np.float32) if total > 0 else target_weights.astype(np.float32)
            return records

        if resume_date is not None:
            # Resume from the last cached closed month: fetch only a small
            # trailing window (enough months back to fill one lookback
            # window before it), not the model's full history.
            fetch_start = (pd.Timestamp(resume_date).replace(day=1) - pd.DateOffset(months=lookback + 2)).date()
            fetch_start = max(fetch_start, train_start)
            open_df, close_df = _fetch_prices_for_universe(tickers, fetch_start, as_of_date)
            monthly_open = open_df.resample("ME").first()
            monthly_close = close_df.resample("ME").last()
            returns_df = (monthly_close / monthly_open - 1).dropna()

            resume_ts = pd.Timestamp(resume_date)
            if resume_ts in returns_df.index and resume_ts in cached.index:
                last_weights_row = cached.loc[resume_ts].reindex(tickers).fillna(0.0).values.astype(np.float32)
                day_returns = returns_df.loc[resume_ts].values
                drifted = last_weights_row * (1 + day_returns)
                total = drifted.sum()
                weights = (drifted / total).astype(np.float32) if total > 0 else last_weights_row
                first_predict_pos = returns_df.index.get_loc(resume_ts) + 1

                records = replay(first_predict_pos, weights, returns_df)
                new_df = pd.DataFrame(records).set_index("date")
                combined = pd.concat([cached, new_df]) if records else cached
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                return combined
            # Fetched window didn't line up with the cache (shouldn't
            # normally happen) -- fall through to a full recompute below.

        # First run for this model (no cache yet), or a resume fallback:
        # full replay from the training cutoff, same as the original
        # (pre-caching) behavior.
        open_df, close_df = _fetch_prices_for_universe(tickers, train_start, as_of_date)
        monthly_open = open_df.resample("ME").first()
        monthly_close = close_df.resample("ME").last()
        returns_df = (monthly_close / monthly_open - 1).dropna()

        # The lookback window feeding a prediction may span the tail end of
        # the training period itself -- the model just consumes "the last
        # `lookback` months of returns" regardless of whether they were seen
        # during training, so predictions can start right after the cutoff
        # instead of waiting a full extra `lookback` months of purely
        # post-cutoff data.
        post_cutoff = returns_df.index[returns_df.index > train_end_ts]
        if post_cutoff.empty:
            return cached if not cached.empty else pd.DataFrame(columns=tickers)
        first_predict_pos = returns_df.index.get_loc(post_cutoff[0])
        if first_predict_pos < lookback:
            return cached if not cached.empty else pd.DataFrame(columns=tickers)

        n_assets = len(tickers)
        weights = np.ones(n_assets, dtype=np.float32) / n_assets
        records = replay(first_predict_pos, weights, returns_df)
        new_df = pd.DataFrame(records).set_index("date")
        if cached.empty:
            return new_df
        combined = pd.concat([cached, new_df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        return combined
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Overlay rules + model selection + weights-by-rebalance-date
# ---------------------------------------------------------------------------

def apply_overlay_rules(raw_weights: dict[str, float], target_date: dt.date) -> dict[str, float]:
    """No redistribution -- excluded/trimmed weight becomes cash."""
    current_members, _ = set50_data.constituents_for_date(target_date)
    current_members = set(current_members)

    out: dict[str, float] = {}
    for ticker, weight in raw_weights.items():
        if ticker not in current_members:
            continue
        if weight < MIN_WEIGHT:
            continue
        out[ticker] = min(weight, MAX_WEIGHT)
    return out


def compute_a2c_weights_by_date(
    rebalance_dates: list[pd.Timestamp],
) -> tuple[dict[pd.Timestamp, dict[str, float]], list[str]]:
    """For each rebalance date, pick the most recently trained model whose
    train_end_date is before that date (point-in-time correct), take that
    model's raw weight row for that calendar month (if it has one yet),
    and apply the overlay rules. A date with no eligible model yet, or
    whose chosen model hasn't produced a row that far out, is omitted
    (the backtest holds cash for that period)."""
    models, warnings = get_models()
    if not models:
        return {}, warnings

    models_sorted = sorted(models, key=lambda m: m["train_end_date"])
    as_of = portfolio.effective_data_date().isoformat()

    weight_sequences: dict[str, pd.DataFrame] = {}
    for m in models_sorted:
        try:
            seq = _weights_sequence_for_model(
                m["name"], m["model"], tuple(m["tickers"]), m["lookback"],
                m["train_start_date"], m["train_end_date"], as_of,
            )
        except Exception as e:
            warnings.append(f"{m['name']}: inference failed ({e})")
            continue
        weight_sequences[m["name"]] = seq
        if seq.empty:
            warnings.append(
                f"{m['name']}: no predictions yet — not enough price history available "
                f"since its {m['train_end_date']} training cutoff."
            )

    weights_by_date: dict[pd.Timestamp, dict[str, float]] = {}
    for date in rebalance_dates:
        date_iso = date.date().isoformat()
        eligible = [m for m in models_sorted if m["train_end_date"] < date_iso and m["name"] in weight_sequences]
        if not eligible:
            continue
        chosen = eligible[-1]  # most recently trained eligible model
        seq = weight_sequences[chosen["name"]]
        if seq.empty:
            continue
        matching = seq[(seq.index.year == date.year) & (seq.index.month == date.month)]
        if matching.empty:
            continue
        raw = {t: float(w) for t, w in matching.iloc[0].dropna().items() if w and w > 0}
        weights_by_date[date] = apply_overlay_rules(raw, date.date())

    return weights_by_date, warnings


def run_a2c_backtest(
    open_matrix: pd.DataFrame, close_matrix: pd.DataFrame
) -> tuple[pd.Series, dict[pd.Timestamp, dict[str, float]], list[str]]:
    """Full pipeline: model selection -> inference -> overlay -> backtest.
    Returns (value_series, weights_by_date, warnings). value_series is
    empty if no models are available at all."""
    rebalance_dates = portfolio._month_start_rebalance_dates(close_matrix.index)
    weights_by_date, warnings = compute_a2c_weights_by_date(rebalance_dates)
    if not weights_by_date:
        return pd.Series(dtype=float), {}, warnings

    result = portfolio.run_weighted_backtest(
        open_matrix, close_matrix, weights_by_date,
        apply_costs=True, cash_rate_annual=CASH_RATE_NET_ANNUAL,
    )
    return result["value"], weights_by_date, warnings


def latest_weights_snapshot(
    weights_by_date: dict[pd.Timestamp, dict[str, float]]
) -> tuple[pd.Timestamp | None, dict[str, float]]:
    if not weights_by_date:
        return None, {}
    latest_date = max(weights_by_date.keys())
    return latest_date, weights_by_date[latest_date]
