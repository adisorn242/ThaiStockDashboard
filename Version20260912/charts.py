"""Plotly figure builders for the price/volume/indicator panels."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

EMA_COLORS = {
    13: "#f2a900",
    21: "#00a3ff",
    34: "#ff5c5c",
    55: "#8e44ad",
    89: "#16a085",
    200: "#7f8c8d",
}


def price_volume_figure(df: pd.DataFrame, symbol: str, ema_windows=(13, 21, 34, 55, 89, 200), dark: bool = False) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.03,
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=symbol,
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    for w in ema_windows:
        col = f"EMA{w}"
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[col],
                    name=col,
                    line=dict(width=1.3, color=EMA_COLORS.get(w)),
                ),
                row=1,
                col=1,
            )

    colors = [
        "#2ecc71" if c >= o else "#e74c3c"
        for o, c in zip(df["Open"], df["Close"])
    ]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color=colors, showlegend=False),
        row=2,
        col=1,
    )

    fig.update_layout(
        height=600,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        template="plotly_dark" if dark else "plotly_white",
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig


def rsi_figure(rsi_series: pd.Series, dark: bool = False) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rsi_series.index, y=rsi_series, name="RSI", line=dict(color="#8e44ad")))
    fig.add_hline(y=70, line_dash="dash", line_color="#e74c3c", opacity=0.6)
    fig.add_hline(y=30, line_dash="dash", line_color="#2ecc71", opacity=0.6)
    fig.update_yaxes(range=[0, 100], title_text="RSI")
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=20, b=10), template="plotly_dark" if dark else "plotly_white")
    return fig


def macd_figure(macd_df: pd.DataFrame, dark: bool = False) -> go.Figure:
    fig = go.Figure()
    colors = ["#1e8449" if v >= 0 else "#a93226" for v in macd_df["Histogram"]]
    fig.add_trace(
        go.Bar(
            x=macd_df.index,
            y=macd_df["Histogram"],
            name="Histogram",
            marker_color=colors,
            marker_line_color=colors,
            marker_line_width=1.5,
            opacity=1.0,
        )
    )
    fig.add_trace(go.Scatter(x=macd_df.index, y=macd_df["MACD"], name="MACD", line=dict(color="#00a3ff", width=1.8)))
    fig.add_trace(go.Scatter(x=macd_df.index, y=macd_df["Signal"], name="Signal", line=dict(color="#f2a900", width=1.8)))
    fig.update_layout(
        height=220,
        margin=dict(l=10, r=10, t=20, b=10),
        template="plotly_dark" if dark else "plotly_white",
        bargap=0.05,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
    )
    return fig


def bollinger_figure(df: pd.DataFrame, bb_df: pd.DataFrame, symbol: str, dark: bool = False) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=bb_df.index, y=bb_df["BB_Upper"], name="Upper", line=dict(color="#bdc3c7", width=1),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=bb_df.index,
            y=bb_df["BB_Lower"],
            name="Lower",
            line=dict(color="#bdc3c7", width=1),
            fill="tonexty",
            fillcolor="rgba(189, 195, 199, 0.2)",
        )
    )
    fig.add_trace(go.Scatter(x=bb_df.index, y=bb_df["BB_Mid"], name="Mid (SMA20)", line=dict(color="#f2a900", width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name=symbol, line=dict(color="#00a3ff", width=1.5)))
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=20, b=10), template="plotly_dark" if dark else "plotly_white")
    return fig


def ichimoku_figure(df: pd.DataFrame, ichimoku_df: pd.DataFrame, symbol: str, dark: bool = False) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=symbol,
            showlegend=False,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=ichimoku_df.index,
            y=ichimoku_df["SenkouA"],
            name="Senkou Span A",
            line=dict(color="rgba(46, 204, 113, 0.5)", width=1),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ichimoku_df.index,
            y=ichimoku_df["SenkouB"],
            name="Senkou Span B",
            line=dict(color="rgba(231, 76, 60, 0.5)", width=1),
            fill="tonexty",
            fillcolor="rgba(120, 120, 120, 0.15)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ichimoku_df.index,
            y=ichimoku_df["Tenkan"],
            name="Tenkan-sen (9)",
            line=dict(color="#00a3ff", width=1.3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ichimoku_df.index,
            y=ichimoku_df["Kijun"],
            name="Kijun-sen (26)",
            line=dict(color="#e74c3c", width=1.3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ichimoku_df.index,
            y=ichimoku_df["Chikou"],
            name="Chikou Span",
            line=dict(color="#f2a900", width=1.3, dash="dot"),
        )
    )

    fig.update_layout(
        height=560,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        template="plotly_dark" if dark else "plotly_white",
    )
    fig.update_yaxes(title_text="Price")
    return fig


def cumulative_return_figure(
    portfolio: pd.Series,
    benchmark: pd.Series,
    benchmark_name: str = "TDEX (SET50 ETF)",
    a2c: pd.Series | None = None,
    a2c_name: str = "A2C RL Strategy",
    dark: bool = False,
) -> go.Figure:
    """A2C strategy (if provided), then equal-weight portfolio (net of
    costs), then benchmark -- all indexed to 100 at start. A2C is drawn
    first since it's shown before Equal-Weight throughout the app."""
    fig = go.Figure()
    if a2c is not None and not a2c.empty:
        fig.add_trace(
            go.Scatter(x=a2c.index, y=a2c, name=a2c_name, line=dict(color="#d35400", width=2))
        )
    fig.add_trace(
        go.Scatter(x=portfolio.index, y=portfolio, name="SET50 Equal-Weight Portfolio", line=dict(color="#1e8449", width=2))
    )
    if not benchmark.empty:
        fig.add_trace(
            go.Scatter(x=benchmark.index, y=benchmark, name=benchmark_name, line=dict(color="#7f8c8d", width=1.5))
        )
    fig.update_layout(
        height=460,
        margin=dict(l=10, r=10, t=30, b=10),
        template="plotly_dark" if dark else "plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
    )
    fig.update_yaxes(title_text="Value (start = 100)")
    return fig


def adx_figure(adx_df: pd.DataFrame, dark: bool = False) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=adx_df.index, y=adx_df["ADX"], name="ADX", line=dict(color="#2c3e50", width=2)))
    fig.add_trace(go.Scatter(x=adx_df.index, y=adx_df["PlusDI"], name="+DI", line=dict(color="#1e8449", width=1.3)))
    fig.add_trace(go.Scatter(x=adx_df.index, y=adx_df["MinusDI"], name="-DI", line=dict(color="#a93226", width=1.3)))
    fig.add_hline(y=25, line_dash="dash", line_color="#95a5a6", opacity=0.6)
    fig.update_yaxes(title_text="ADX / DI")
    fig.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=20, b=10),
        template="plotly_dark" if dark else "plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
    )
    return fig
