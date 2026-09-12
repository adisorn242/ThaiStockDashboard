"""Thai Stock (SET) Dashboard.

A Streamlit research tool with two top-level tabs:

- Stock Lookup: candlestick price chart with EMA overlays and volume, an
  Ichimoku Cloud view, RSI/MACD/Bollinger Bands/ADX indicator panels, and a
  key-stats fundamentals summary for any Thai (SET) ticker.
- SET50 Equal-Weighted Portfolio: an equal-weight, monthly-rebalanced
  backtest of the SET50 index vs. the TDEX (SET50 ETF) benchmark.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import streamlit as st

import a2c_strategy
import charts
import data
import indicators
import portfolio
import set50_data
import watchlist as wl

st.set_page_config(page_title="Thai Stock Dashboard", layout="wide", page_icon="📈")

PORTFOLIO_START_DATE = dt.date(2026, 1, 1)


FONT_SCALE_PX = {"Normal": 16, "Large": 18, "Extra Large": 21}


def init_ui_prefs():
    if "ui_font_scale" not in st.session_state:
        st.session_state.ui_font_scale = "Normal"


def is_dark() -> bool:
    """Charts automatically follow Streamlit's own active theme -- the
    same theme set via its native Settings > Theme switcher (or your
    OS/browser default). No separate control for this in the sidebar.

    The results table doesn't use this at all -- it's styled with
    Streamlit's own CSS theme variables directly, so it always matches
    the real page theme with no detection needed."""
    try:
        theme_type = st.context.theme.type
    except Exception:
        theme_type = None
    return theme_type == "dark"


def render_ui_controls():
    st.sidebar.markdown("##### Display")
    st.sidebar.selectbox("Text size", list(FONT_SCALE_PX.keys()), key="ui_font_scale")
    st.sidebar.divider()


def inject_global_css():
    base_px = FONT_SCALE_PX.get(st.session_state.get("ui_font_scale", "Normal"), 16)

    # Only font sizing here -- no color overrides. Streamlit's own theme
    # (switched via its native Settings menu) already colors every built-in
    # widget correctly; adding our own color CSS on top of that is exactly
    # what caused dark-on-dark, unreadable text before.
    st.markdown(
        f"""
        <style>
        html {{ font-size: {base_px}px; }}

        /* Bigger, bolder tab labels (top-level and nested sub-tabs) */
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {{
            font-size: 1.15rem;
            font-weight: 600;
        }}
        .stTabs [data-baseweb="tab"] {{
            padding-top: 10px;
            padding-bottom: 10px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def format_large_number(n) -> str:
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    for unit, div in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(n) >= div:
            return f"{n / div:.2f}{unit}"
    return f"{n:,.0f}"


def format_pct(n) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n) * 100:.2f}%"
    except (TypeError, ValueError):
        return "—"


def format_dividend_yield(n) -> str:
    if n is None:
        return "—"
    try:
        v = float(n)
    except (TypeError, ValueError):
        return "—"
    # yfinance has been observed returning this field both as a fraction
    # (0.076) and already as a percentage (7.6), depending on version/
    # ticker. Real dividend yields are well under 100%, so treat anything
    # >= 1 as already a percentage rather than multiplying it again.
    if v >= 1:
        return f"{v:.2f}%"
    return f"{v * 100:.2f}%"


def init_state():
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = wl.load_watchlist()
    if "current" not in st.session_state:
        st.session_state.current = st.session_state.watchlist[0] if st.session_state.watchlist else "PTT.BK"
    if "lookup_error" not in st.session_state:
        st.session_state.lookup_error = None
    if "add_message" not in st.session_state:
        st.session_state.add_message = None


def render_exit_control():
    st.sidebar.divider()
    with st.sidebar.expander("⚠️ Shut down"):
        st.caption("Stops the app server completely. Run `streamlit run app.py` again to restart it.")
        if st.button("🛑 Exit program", type="primary"):
            st.warning("Shutting down — you can close this browser tab now.")
            os._exit(0)


def render_sidebar():
    st.sidebar.title("⭐ Watchlist")
    st.sidebar.caption("Optional — save tickers you check often. You can view any Thai ticker without adding it here.")

    if not st.session_state.watchlist:
        st.sidebar.caption("Your watchlist is empty.")
    else:
        for symbol in list(st.session_state.watchlist):
            last_price, pct_change = data.fetch_last_price(symbol)
            price_str = f"{last_price:,.2f}" if last_price is not None else "—"
            pct_str = f"{pct_change:+.2f}%" if pct_change is not None else ""
            delta_color = "green" if (pct_change or 0) >= 0 else "red"

            row = st.sidebar.container()
            cols = row.columns([0.5, 0.28, 0.22])
            is_selected = symbol == st.session_state.current
            label = f"**{symbol}**" if is_selected else symbol
            if cols[0].button(label, key=f"select_{symbol}", use_container_width=True):
                st.session_state.current = symbol
                st.rerun()
            cols[1].markdown(
                f"<div style='text-align:right; padding-top:6px;'>{price_str}<br>"
                f"<span style='color:{delta_color}; font-size:0.8em;'>{pct_str}</span></div>",
                unsafe_allow_html=True,
            )
            if cols[2].button("🗑 Remove", key=f"remove_{symbol}", use_container_width=True, help=f"Remove {symbol} from watchlist"):
                st.session_state.watchlist = wl.remove_ticker(st.session_state.watchlist, symbol)
                if st.session_state.current == symbol:
                    st.session_state.current = st.session_state.watchlist[0] if st.session_state.watchlist else None
                st.rerun()

    st.sidebar.divider()
    st.sidebar.caption("This dashboard covers Thai (SET) stocks only.")


def render_lookup_bar():
    st.title("📈 Thai Stock Dashboard")
    st.caption("Look up any Thai (SET) stock — no need to add it to your watchlist first. Just type the symbol, e.g. PTT, AOT, CPALL.")

    col1, col2 = st.columns([0.75, 0.25])
    with col1:
        with st.form("lookup_form", clear_on_submit=False):
            raw = st.text_input("Ticker", value=st.session_state.current or "", placeholder="e.g. PTT or PTT.BK", label_visibility="collapsed")
            go_col, add_col = st.columns(2)
            look_up = go_col.form_submit_button("🔍 View", use_container_width=True)
            add_to_watchlist = add_col.form_submit_button("➕ Add to watchlist", use_container_width=True)

    if look_up or add_to_watchlist:
        symbol = data.normalize_thai_symbol(raw)
        if not symbol:
            st.session_state.lookup_error = "Please enter a ticker symbol."
        elif not data.validate_symbol(symbol):
            st.session_state.lookup_error = (
                f"'{symbol}' wasn't found as a Thai (SET) stock. "
                "This dashboard only supports Thai stocks — try just the symbol (e.g. PTT) "
                "and it will be looked up as PTT.BK."
            )
        else:
            st.session_state.lookup_error = None
            st.session_state.current = symbol
            if add_to_watchlist:
                if symbol in st.session_state.watchlist:
                    st.session_state.add_message = f"{symbol} is already in your watchlist."
                else:
                    st.session_state.watchlist = wl.add_ticker(st.session_state.watchlist, symbol)
                    st.session_state.add_message = f"Added {symbol} to your watchlist."
            st.rerun()

    if st.session_state.lookup_error:
        st.error(st.session_state.lookup_error)
    if st.session_state.add_message:
        st.success(st.session_state.add_message)
        st.session_state.add_message = None


def render_detail(symbol: str):
    st.subheader(symbol)

    range_key = st.radio(
        "Range", list(data.RANGE_OPTIONS.keys()), index=4, horizontal=True, label_visibility="collapsed"
    )

    with st.spinner(f"Loading data for {symbol}..."):
        df = data.fetch_history(symbol, range_key)
        info = data.fetch_info(symbol)

    if df.empty:
        st.error(f"No price data available for {symbol} over this range.")
        return

    df_ema = indicators.add_emas(df)

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else last_close
    change = last_close - prev_close
    pct_change = (change / prev_close * 100) if prev_close else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Last Close", f"{last_close:,.2f}", f"{change:+.2f} ({pct_change:+.2f}%)")
    m2.metric("Day High", f"{float(df['High'].iloc[-1]):,.2f}")
    m3.metric("Day Low", f"{float(df['Low'].iloc[-1]):,.2f}")
    m4.metric("Volume", format_large_number(float(df["Volume"].iloc[-1])))

    tab_chart, tab_ichimoku, tab_indicators, tab_fundamentals = st.tabs(
        ["Price Chart", "Ichimoku Cloud", "Indicators", "Fundamentals"]
    )

    with tab_chart:
        st.caption("EMA 13 / 21 / 34 / 55 / 89 / 200")
        st.plotly_chart(charts.price_volume_figure(df_ema, symbol, dark=is_dark()), use_container_width=True)

    with tab_ichimoku:
        ichimoku_df = indicators.ichimoku_cloud(df)
        st.plotly_chart(charts.ichimoku_figure(df, ichimoku_df, symbol, dark=is_dark()), use_container_width=True)

    with tab_indicators:
        col1, col2 = st.columns(2)
        with col1:
            st.caption("RSI (14)")
            rsi_series = indicators.rsi(df["Close"])
            st.plotly_chart(charts.rsi_figure(rsi_series, dark=is_dark()), use_container_width=True)
        with col2:
            st.caption("MACD (12, 26, 9)")
            macd_df = indicators.macd(df["Close"])
            st.plotly_chart(charts.macd_figure(macd_df, dark=is_dark()), use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            st.caption("Bollinger Bands (20, 2σ)")
            bb_df = indicators.bollinger_bands(df["Close"])
            st.plotly_chart(charts.bollinger_figure(df, bb_df, symbol, dark=is_dark()), use_container_width=True)
        with col4:
            st.caption("ADX / +DI / -DI (14)")
            adx_df = indicators.adx(df)
            st.plotly_chart(charts.adx_figure(adx_df, dark=is_dark()), use_container_width=True)

    with tab_fundamentals:
        if not info:
            st.info("No fundamentals data available for this ticker.")
        else:
            name = info.get("longName") or info.get("shortName") or symbol
            st.subheader(name)
            sector = info.get("sector", "—")
            industry = info.get("industry", "—")
            st.caption(f"{sector} · {industry}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Market Cap", format_large_number(info.get("marketCap")))
            c2.metric("P/E (TTM)", f"{info.get('trailingPE'):.2f}" if info.get("trailingPE") else "—")
            c3.metric("EPS (TTM)", f"{info.get('trailingEps'):.2f}" if info.get("trailingEps") else "—")
            c4.metric("Dividend Yield", format_dividend_yield(info.get("dividendYield")))

            c5, c6, c7, c8 = st.columns(4)
            c5.metric("52W High", f"{info.get('fiftyTwoWeekHigh'):,.2f}" if info.get("fiftyTwoWeekHigh") else "—")
            c6.metric("52W Low", f"{info.get('fiftyTwoWeekLow'):,.2f}" if info.get("fiftyTwoWeekLow") else "—")
            c7.metric("Beta", f"{info.get('beta'):.2f}" if info.get("beta") else "—")
            c8.metric("Avg Volume", format_large_number(info.get("averageVolume")))

            if info.get("longBusinessSummary"):
                with st.expander("Business summary"):
                    st.write(info["longBusinessSummary"])


def render_stock_lookup_tab():
    render_sidebar()
    render_lookup_bar()

    if not st.session_state.current:
        st.info("Enter a Thai stock ticker above to get started (e.g. PTT, AOT, CPALL).")
        return

    render_detail(st.session_state.current)


def render_set50_list_controls():
    with st.expander("SET50 constituent list source", expanded=False):
        for p in set50_data.all_periods():
            st.caption(f"**{p['start']} → {p['end']}** — {len(p['tickers'])} tickers — _{p['source']}_")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh SET50 list from SET", use_container_width=True):
                with st.spinner("Checking set.or.th for an updated SET50 list..."):
                    try:
                        new_period = set50_data.try_scrape_latest_period()
                        set50_data.add_period(new_period)
                        st.success(
                            f"Added {new_period['start']} → {new_period['end']} "
                            f"({len(new_period['tickers'])} tickers)."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(
                            f"Couldn't fetch an updated list automatically ({e}). "
                            "Please upload the official SET50 PDF instead using the button on the right."
                        )
        with col2:
            uploaded = st.file_uploader(
                "Upload a SET50/SET100 PDF", type="pdf", label_visibility="collapsed"
            )
            if uploaded is not None:
                try:
                    new_period = set50_data.parse_set50_pdf(uploaded)
                    set50_data.add_period(new_period)
                    st.success(
                        f"Added {new_period['start']} → {new_period['end']} "
                        f"({len(new_period['tickers'])} tickers)."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Couldn't parse this PDF: {e}")

        st.divider()
        if st.button("🗑 Force refresh price data (clear local cache)"):
            portfolio.force_refresh()
            st.success("Local price cache cleared — it will be fully re-fetched on the next load.")
            st.rerun()


def render_strategy_explanation():
    st.markdown(
        f"""
### Strategy: SET50 Equal-Weight, Monthly Rebalance

The portfolio holds every current SET50 constituent at **equal weight**
(1/N of portfolio value each). SET publishes the official SET50 list twice
a year (H1: Jan–Jun, H2: Jul–Dec) — whenever the list changes, the
portfolio switches to the new constituents at the next rebalance.

**Rebalancing.** On the **first trading day of every month**, the
portfolio is reset to equal weight across the current constituent list:
positions that grew are trimmed, positions that shrank (or new
constituents) are topped up, so every holding is back to exactly 1/N of
the portfolio's value. Trades (including the very first, initial
investment) execute at that day's **opening price**; the portfolio's
day-to-day value — and every performance metric — is marked using each
day's **closing price** (close-to-close returns). The backtest starts
**{PORTFOLIO_START_DATE.isoformat()}**.

**Benchmark.** Performance is compared against **TDEX** (`TDEX.BK`), the
ThaiDEX SET50 ETF, which tracks the SET50 index directly.

**Data.** Prices are end-of-day (EOD) closes/opens, cached locally so
repeated loads are fast. Data is refreshed once per weekday after
**18:00 (Asia/Bangkok)**. A day with no trading (weekend, market holiday)
is treated as a **0% return** for that day, rather than causing an error.

---

### Transaction Costs

Each monthly rebalance trades some value in and out of positions
(**turnover**). A cost is applied to that turnover, at the open price the
trade executes at:

- Brokerage fee: **{portfolio.FEE_BPS} bps** (0.{portfolio.FEE_BPS:02d}%) of value traded
- Plus **{portfolio.VAT_RATE*100:.0f}% VAT** on that fee
- Effective cost rate: {portfolio.FEE_BPS} bps × 1.{int(portfolio.VAT_RATE*100):02d} = **{portfolio.EFFECTIVE_COST_RATE*100:.4f}%** of value traded per rebalance

All performance figures shown are **net of these costs**.

---

### Performance Metrics

Computed from daily (close-to-close) returns, with a **risk-free rate (Rf)
of {portfolio.RF_ANNUAL*100:.0f}% per year**:

- **Cumulative Return** — total return over the selected period: `value_end / value_start − 1`
- **Annualized Return** — the cumulative return compounded to a yearly rate (CAGR): `(1 + cumulative return)^(252 / trading days) − 1`
- **Annualized Risk (Std)** — volatility of daily returns, annualized: `daily std × √252`
- **Sharpe Ratio** — return per unit of total risk: `(annualized return − Rf) / annualized std`
- **Sortino Ratio** — like Sharpe, but only penalizes downside volatility (days below the daily Rf rate): `(annualized return − Rf) / annualized downside std`
- **Calmar Ratio** — return relative to worst-case loss: `annualized return / |maximum drawdown|`
- **Maximum Drawdown** — the largest peak-to-trough decline in portfolio value over the period
- **Daily 95% VaR (Value at Risk)** — the daily loss that historically was not exceeded on 95% of days (5th percentile of daily returns)
- **Daily 95% CVaR (Conditional VaR / Expected Shortfall)** — the average daily loss on the worst 5% of days

Every metric (and the chart) can be windowed to a trailing period using
the selector on the Performance tab — the underlying rebalance schedule
above is unaffected; the window only changes what's measured and displayed.

---

### Strategy: A2C Reinforcement-Learning Portfolio

A Stable-Baselines3 **A2C** policy, trained separately (in Colab) on
monthly SET50 returns since 2016, picks a target weight for each stock
every month. This dashboard automatically fetches every trained model
from a shared Drive folder, and for each month uses the **most recently
trained model whose training data doesn't look into that month's
future** — so a newer model dropped into the same folder later is picked
up automatically, with no manual steps.

**Overlay rules** (applied in order, to each month's raw model weights —
**no redistribution**, whatever is trimmed or excluded simply becomes idle
cash for that month):

1. **SET50-membership restriction** — a ticker the model was trained on
   that has since left the current SET50 list is excluded.
2. **Floor** — any weight below **{a2c_strategy.MIN_WEIGHT:.0%}** is
   excluded (too small to be a meaningful position).
3. **Cap** — any weight above **{a2c_strategy.MAX_WEIGHT:.0%}** is trimmed
   down to {a2c_strategy.MAX_WEIGHT:.0%}.

**Cash.** Whatever weight is left unassigned after the three rules is held
as cash, earning **{a2c_strategy.CASH_RATE_GROSS_ANNUAL:.2%}/year gross**,
less **{a2c_strategy.WITHHOLDING_TAX_RATE:.0%} withholding tax**, i.e.
**{a2c_strategy.CASH_RATE_NET_ANNUAL:.4%}/year net** — accrued daily and
prorated by calendar days between rebalances.

Rebalancing, trade-at-open/value-at-close mechanics, and transaction costs
are otherwise identical to the Equal-Weight strategy above.
"""
    )


def style_metrics_table(display_df: pd.DataFrame):
    # st.dataframe() renders through Streamlit's own data-grid widget, which
    # ignores CSS text-align (and most other) styling from a pandas Styler --
    # only a narrow subset of Styler formatting is honored there. Rendering
    # the Styler's HTML directly (via st.markdown) instead gives full control
    # over alignment/color/font, which is what's needed here.
    #
    # Colors use Streamlit's own CSS theme variables instead of a computed
    # hex value -- these are set by Streamlit itself and always match
    # whatever theme is actually showing on the page (light or dark,
    # however it was switched), so the table can never end up mismatched
    # against the real background the way a separately-computed color did.
    text_color = "var(--text-color)"
    header_bg = "var(--secondary-background-color)"
    stripe_bg = "rgba(127, 140, 141, 0.10)"
    font_px = FONT_SCALE_PX.get(st.session_state.get("ui_font_scale", "Normal"), 16)
    table_font = f"{font_px * 1.05 / 16:.3f}rem"

    styler = (
        display_df.style
        .set_properties(**{"text-align": "center", "font-size": table_font, "color": text_color})
        .set_table_styles(
            [
                {"selector": "th", "props": [("font-weight", "700"), ("font-size", table_font), ("text-align", "center"), ("color", text_color), ("background-color", header_bg)]},
                {"selector": "th.col_heading", "props": [("text-align", "center")]},
                {"selector": "th.row_heading", "props": [("text-align", "center")]},
                {"selector": "td", "props": [("text-align", "center")]},
                {"selector": "table", "props": [("width", "100%"), ("border-collapse", "collapse")]},
                {"selector": "tbody tr:nth-child(even)", "props": [("background-color", stripe_bg)]},
            ]
        )
    )
    html = styler.to_html()
    return f'<div style="overflow-x:auto;">{html}</div>'


def render_portfolio_performance():
    end_date = portfolio.effective_data_date()
    all_tickers = sorted({t for p in set50_data.all_periods() for t in p["tickers"]})

    period_label = st.selectbox(
        "Performance window", list(portfolio.PERIOD_OPTIONS.keys()), index=0
    )

    with st.spinner("Loading SET50 constituent price data (only new days are fetched after the first load)..."):
        open_matrix, close_matrix, last_updated = portfolio.build_ohlc_matrices(
            all_tickers, PORTFOLIO_START_DATE, end_date
        )
        benchmark_full, benchmark_last_updated = portfolio.fetch_benchmark(PORTFOLIO_START_DATE, end_date)
        last_updated["TDEX (TDEX.BK)"] = benchmark_last_updated

    if close_matrix.empty:
        st.error("Couldn't load price data for SET50 constituents. Check your network connection and try again.")
        return

    result = portfolio.run_equal_weight_backtest(open_matrix, close_matrix, apply_costs=True)
    value_full = result["value"]

    if value_full.empty or value_full.dropna().empty:
        st.info("Not enough trading days yet to compute performance metrics.")
        return

    with st.spinner("Fetching and running the A2C strategy (this can take a moment on first load)..."):
        a2c_value_full, a2c_weights_by_date, a2c_warnings = a2c_strategy.run_a2c_backtest(open_matrix, close_matrix)
    st.session_state["_a2c_weights_by_date"] = a2c_weights_by_date  # for the A2C Weights tab
    for w in a2c_warnings:
        st.warning(w)

    value_windowed, value_clipped = portfolio.window_and_rebase(value_full, period_label)
    benchmark_windowed, bench_clipped = (
        portfolio.window_and_rebase(benchmark_full, period_label) if not benchmark_full.empty else (benchmark_full, False)
    )
    a2c_windowed, a2c_clipped = (
        portfolio.window_and_rebase(a2c_value_full, period_label) if not a2c_value_full.empty else (a2c_value_full, False)
    )
    if value_clipped or bench_clipped or a2c_clipped:
        st.caption(
            f"Only {(value_full.index[-1] - value_full.index[0]).days} days of history are available since "
            f"inception — showing the full history instead of '{period_label}'."
        )

    metrics_portfolio = portfolio.compute_metrics(value_windowed)
    metrics_bench = portfolio.compute_metrics(benchmark_windowed) if not benchmark_windowed.empty else {}
    metrics_a2c = portfolio.compute_metrics(a2c_windowed) if not a2c_windowed.empty else {}

    st.plotly_chart(
        charts.cumulative_return_figure(
            value_windowed, benchmark_windowed, benchmark_name="TDEX (TDEX.BK)",
            a2c=a2c_windowed if not a2c_windowed.empty else None,
            dark=is_dark(),
        ),
        use_container_width=True,
    )

    pct_rows = {
        "Cumulative Return", "Annualized Return", "Annualized Risk (Std)",
        "Maximum Drawdown", "Daily 95% VaR", "Daily 95% CVaR",
    }
    table_rows = []
    for metric_name in metrics_portfolio:
        row = {"Metric": metric_name}
        if metrics_a2c:
            row["A2C RL Strategy"] = metrics_a2c.get(metric_name, float("nan"))
        row["SET50 Equal-Weight Portfolio"] = metrics_portfolio.get(metric_name, float("nan"))
        row["TDEX (SET50 ETF)"] = metrics_bench.get(metric_name, float("nan"))
        table_rows.append(row)
    metrics_df = pd.DataFrame(table_rows).set_index("Metric")

    def fmt(val, is_pct):
        if pd.isna(val):
            return "—"
        return f"{val * 100:.2f}%" if is_pct else f"{val:.2f}"

    display_df = metrics_df.copy()
    for col in display_df.columns:
        display_df[col] = [fmt(v, name in pct_rows) for name, v in zip(metrics_df.index, metrics_df[col])]

    st.markdown(f"##### Performance ({period_label})")
    st.markdown(style_metrics_table(display_df), unsafe_allow_html=True)

    with st.expander("Rebalance log"):
        st.dataframe(pd.DataFrame(result["rebalance_log"]), use_container_width=True, hide_index=True)

    # Diagnostics: which tickers have stale/missing data, shown last per your request.
    if last_updated:
        newest = max((d for d in last_updated.values() if d), default=None)
        stale = {t: d for t, d in last_updated.items() if newest and (d is None or d < newest)}
        if stale:
            details = ", ".join(f"{t} (last: {d.isoformat() if d else 'no data'})" for t, d in sorted(stale.items()))
            st.warning(
                f"{len(stale)} ticker(s) have price data that stopped updating before the most recent "
                f"available date ({newest.isoformat()}) and were forward-filled in the meantime: {details}"
            )


def render_a2c_weights_tab():
    weights_by_date = st.session_state.get("_a2c_weights_by_date")
    if weights_by_date is None:
        st.info("Open the Performance tab first to load the A2C strategy's weights.")
        return

    latest_date, latest_weights = a2c_strategy.latest_weights_snapshot(weights_by_date)
    if latest_date is None:
        st.info("No A2C target weights available yet (no trained model old enough for this period, or the model couldn't be loaded — check the Performance tab for details).")
        return

    invested = sum(latest_weights.values())
    cash_weight = max(0.0, 1.0 - invested)

    rows = [{"Ticker": t, "Weight": w} for t, w in sorted(latest_weights.items(), key=lambda x: -x[1])]
    rows.append({"Ticker": "Cash", "Weight": cash_weight})
    weights_df = pd.DataFrame(rows)
    weights_df["Weight"] = weights_df["Weight"].map(lambda v: f"{v * 100:.2f}%")

    st.markdown(f"##### Most recent rebalance: {latest_date.date().isoformat()}")
    st.caption(
        f"Cash earns {a2c_strategy.CASH_RATE_NET_ANNUAL:.4%}/year net "
        f"({a2c_strategy.CASH_RATE_GROSS_ANNUAL:.2%} gross, less {a2c_strategy.WITHHOLDING_TAX_RATE:.0%} withholding tax)."
    )
    st.dataframe(weights_df, use_container_width=True, hide_index=True)


def render_portfolio_tab():
    st.title("💼 SET50 Equal-Weighted Portfolio")
    st.caption(
        f"Equal-weight portfolio of SET50 constituents, rebalanced monthly, tracked since "
        f"{PORTFOLIO_START_DATE.isoformat()} against TDEX (SET50 ETF)."
    )

    render_set50_list_controls()

    tab_performance, tab_a2c_weights, tab_strategy = st.tabs(
        ["📊 Performance", "🤖 A2C Weights", "📖 Strategy & Methodology"]
    )
    with tab_performance:
        render_portfolio_performance()
    with tab_a2c_weights:
        render_a2c_weights_tab()
    with tab_strategy:
        render_strategy_explanation()


def main():
    init_state()
    init_ui_prefs()
    render_ui_controls()
    inject_global_css()

    tab_lookup, tab_portfolio = st.tabs(["📊 Stock Lookup", "💼 SET50 Equal-Weighted Portfolio"])
    with tab_lookup:
        render_stock_lookup_tab()
    with tab_portfolio:
        render_portfolio_tab()

    render_exit_control()


if __name__ == "__main__":
    main()
