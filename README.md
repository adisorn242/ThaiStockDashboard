# Thai Stock (SET) Dashboard — Versions

This folder holds dated snapshots of the dashboard. Each dated subfolder
(e.g. `20260912`) is a complete, self-contained version — ready to upload
to GitHub as-is, or run locally — with nothing outside that folder
needed to use it.

## How versioning works here

Each time the dashboard is meaningfully updated, a new dated folder is
added alongside the existing ones (named by date, e.g. `20261015`),
containing the full, current set of files. Older dated folders are left
untouched, so any previous version can always be gone back to. This file
is updated with a short summary each time a new version folder is added.

## Versions

### 20260912 (current / latest)

- Thai (SET) stock lookup: candlestick + EMA chart, Ichimoku Cloud,
  RSI/MACD/Bollinger/ADX indicators, fundamentals panel, optional
  watchlist.
- SET50 Equal-Weighted Portfolio: monthly-rebalanced backtest vs. the
  TDEX benchmark, with transaction costs and a full performance metrics
  table.
- A2C RL Strategy: fully automatic — downloads trained models from a
  shared Google Drive folder, runs inference, applies overlay rules
  (SET50 membership / weight floor+cap), and accrues cash interest.
  Computed monthly weights are cached locally (`a2c_weights_cache.db`)
  so only new months are recomputed after the first run, and the model
  download itself is skipped if it already ran earlier the same day.
- Charts and the results table automatically match Streamlit's own
  light/dark theme setting — no separate switch needed.
- Adjustable text size (sidebar).
- Windows one-click setup: `Install.bat` (one-time) sets up the app and
  adds a Desktop shortcut; `Run Dashboard.vbs` launches it with no
  console window in the way. An "Exit program" button in the sidebar
  shuts the app down cleanly.
