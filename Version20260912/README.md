# Thai Stock (SET) Dashboard

A Streamlit dashboard for researching **Thai stocks (SET)** using live data
from `yfinance`.

> This dashboard only supports Thai (SET) stocks — tickers like `PTT`,
> `AOT`, `CPALL`. It does not support US stocks, crypto, forex, or other
> exchanges.

## Setup (easiest way — Windows, no typing commands)

1. **Double-click `Install.bat`** in this folder. A window will open and
   set everything up automatically (this can take a few minutes the first
   time). When it says "Setup complete!", press any key to close it.
2. A shortcut called **"Thai Stock Dashboard"** now appears on your
   Desktop. **Double-click it any time to start the app** — your browser
   opens automatically.
3. **To stop the app**, either close the browser tab and open the sidebar
   in the app before closing it, or scroll to the bottom of the sidebar,
   open **"⚠️ Shut down"**, and click **"🛑 Exit program"**.
4. If something looks wrong, a small taskbar window is running quietly in
   the background — click it to see what it's doing.

You only need to run `Install.bat` once (run it again if you ever want to
reinstall or update the packages). After that, the Desktop shortcut is
all you need.

## Setup (step by step, for beginners — manual/command-line way)

Use this if `Install.bat` doesn't work for you, if you're on Mac/Linux, or
if you just prefer to see what's happening.

These steps use a **virtual environment** (a private, self-contained copy
of Python just for this project) so it doesn't mix with anything else on
your computer.

1. **Open the project folder in VS Code.**
   File → Open Folder → select the `Dashboard` folder.

2. **Open a terminal in VS Code.**
   Menu bar → Terminal → New Terminal. A terminal panel opens at the
   bottom, already pointed at this folder.

3. **Create the virtual environment.** Type this and press Enter:
   ```
   python -m venv venv
   ```
   This creates a new folder called `venv` inside the project — that's
   your private Python environment. You only need to do this once.

4. **Activate the virtual environment.**
   - On **Windows**, type:
     ```
     venv\Scripts\activate
     ```
   - On **Mac/Linux**, type:
     ```
     source venv/bin/activate
     ```
   You'll know it worked because you'll see `(venv)` appear at the start
   of the terminal line. **Do this every time** you open a new terminal to
   work on this project.

5. **Install the required packages.** With the environment activated, type:
   ```
   pip install -r requirements.txt
   ```
   This installs Streamlit, yfinance, Plotly, pandas, and numpy inside
   `venv` only.

6. **Run the app.** Still with `(venv)` showing, type:
   ```
   streamlit run app.py
   ```
   Your browser should open automatically to `http://localhost:8501`. If
   it doesn't, copy that address from the terminal into your browser.

7. **To stop the app**, click into the terminal and press `Ctrl+C`.

8. **Next time you come back**, you don't need to redo steps 3 and 5 — just
   open the folder, open a terminal, activate the environment (step 4),
   and run the app (step 6).

### If `python` or `pip` isn't recognized

Try `python3`/`pip3` instead, or make sure Python is installed and added
to your system PATH (search "Add Python to PATH" for your OS if unsure).

## Features

- **Look up any Thai ticker** directly — you don't need to add it to a
  watchlist first. Just type the symbol (e.g. `PTT`) and it's automatically
  resolved as a SET stock (`PTT.BK`).
- **Watchlist** (sidebar, optional): a shortcut for tickers you check
  often. Clear "➕ Add to watchlist" and "🗑 Remove" buttons. Saved to
  `watchlist.json` so it persists between runs, seeded with a few example
  SET tickers (PTT.BK, AOT.BK, CPALL.BK) on first launch.
- **Price chart**: candlestick chart with EMA(13, 21, 34, 55, 89, 200)
  overlays and a volume subplot. Selectable date range (1M/3M/6M/YTD/1Y/2Y/5Y).
- **Ichimoku Cloud**: Tenkan-sen, Kijun-sen, Senkou Span A/B (shaded cloud),
  and Chikou Span.
- **Indicators**: RSI(14), MACD(12,26,9) with bold histogram bars,
  Bollinger Bands(20, 2σ), and ADX/+DI/-DI(14).
- **Fundamentals**: market cap, P/E, EPS, dividend yield, 52-week range,
  beta, average volume, and business summary.
- **💼 SET50 Equal-Weighted Portfolio** (a top-level tab next to Stock
  Lookup): an equal-weight backtest of the SET50 index, rebalanced on the
  first trading day of every month, tracked since 1 Jan 2026 against
  TDEX (`TDEX.BK`), the ThaiDEX SET50 ETF. Includes:
  - A "📊 Performance" tab (shown first) with a performance-window selector
    (Since Inception / Last Month / Last 3 Months / Last 6 Months / Last
    Year), a cumulative return chart (portfolio net of costs vs. TDEX),
    and a metrics table: Cumulative Return, Annualized Return,
    Annualized Risk (Std), Sharpe Ratio, Sortino Ratio, Calmar Ratio,
    Maximum Drawdown, Daily 95% VaR, and Daily 95% CVaR (Rf = 1%/year),
    all shown to 2 decimal places. Any tickers whose price data stopped
    updating are flagged in a warning at the bottom of this tab.
  - A "📖 Strategy & Methodology" tab explaining the strategy, rebalancing
    (trades execute at each day's **open** price; daily value and all
    metrics use each day's **close** price), transaction cost
    calculation, and every performance metric formula.
  - Transaction costs: 15 bps brokerage fee + 7% VAT on that fee (≈0.1605%
    effective) applied to the value traded at each rebalance. All figures
    shown are net of these costs.
  - The SET50 constituent list ships built-in for H1 2026 (Jan–Jun) and H2
    2026 (Jul–Dec). A "🔄 Refresh SET50 list from SET" button attempts to
    fetch a newer list automatically from set.or.th; if that fails (e.g.
    the site structure changes, or the network can't reach it), upload the
    official SET50/SET100 PDF instead using the upload button next to it —
    the exact same PDF format SET publishes on their constituents page.
  - Price data is cached locally in a SQLite file (`set50_prices.db`): the
    first load fetches full history, every load after that only fetches
    the days since the last sync, and a "🗑 Force refresh price data"
    button clears the cache if you ever want a clean re-fetch. Data
    updates once per weekday after 18:00 (Asia/Bangkok); days with no
    trading (weekends, market holidays) count as a 0% return rather than
    an error.
  - **🤖 A2C RL Strategy**: shown alongside Equal-Weight and TDEX on the
    same Performance chart and metrics table (shown first), and its own
    "🤖 A2C Weights" tab with the most recent rebalance's per-ticker
    weights. Fully automatic — no notebook to run, no file to upload, no
    setting to configure. On load (refreshed at most once a day), the
    dashboard downloads every trained model from a shared Drive folder,
    and for each month uses the most recently trained model whose
    training data doesn't look into that month's future (so a newer
    model added to the folder later is picked up automatically). Three
    overlay rules apply to the model's raw weights each month, with no
    redistribution (trimmed/excluded weight becomes idle cash): restrict
    to current SET50 members, floor weights below 1%, cap weights above
    10%. Idle cash earns 0.25%/year gross, less 15% withholding tax
    (0.2125%/year net), accrued daily. Each model's computed weights for
    months that have already fully closed are cached locally in
    `a2c_weights_cache.db`, so after the first run, later runs only
    replay the model forward for the months since the last one cached
    (the current, still-open month is always recomputed fresh) instead
    of redoing the full history every time.

## Project structure

- `Install.bat` — Windows, one-time setup: creates the virtual environment, installs packages, and adds a Desktop shortcut
- `Run Dashboard.vbs` — Windows, double-click to start the app with no console window in your face (what the Desktop shortcut points to)
- `run_dashboard.bat` — the actual launch command `Run Dashboard.vbs` runs in the background; you can also double-click this directly if you want to see the console output
- `app.py` — Streamlit UI and page layout (Stock Lookup tab + SET50 Equal-Weighted Portfolio tab)
- `data.py` — yfinance data fetching and Thai-ticker normalization, with caching (15 min TTL)
- `indicators.py` — EMA/RSI/MACD/Bollinger/Ichimoku/ADX calculations (pure pandas)
- `charts.py` — Plotly figure builders
- `watchlist.py` — local JSON watchlist persistence
- `set50_data.py` — SET50 constituent lists (built-in + scraped/uploaded), PDF parsing, best-effort scraper
- `set50_db.py` — SQLite-backed local price cache (incremental sync)
- `portfolio.py` — OHLC price matrix building, equal-weight and generic weighted rebalancing backtests, transaction costs, performance metrics, period windowing
- `a2c_strategy.py` — auto-downloads trained A2C models from a shared Drive folder, runs inference, applies the overlay rules (membership/floor/cap) and cash-interest handling
- `a2c_weights_db.py` — SQLite-backed cache of each A2C model's computed monthly weights, so only new months are replayed after the first run

## Notes

Data fetching requires network access to Yahoo Finance (and, for the SET50
list scraper, to set.or.th) from wherever you run `streamlit run app.py`.
Indicator math, the portfolio backtest engine (including the SQLite
incremental sync and a simulated stale-ticker scenario), chart building,
PDF parsing, and watchlist/list persistence have all been verified against
synthetic and real (provided PDF) data; run the app locally to confirm
live data end-to-end. If a SET50 constituent's price ever looks
suspiciously flat for an extended period, check the warning at the bottom
of the Performance tab first — it's designed to catch exactly that.
