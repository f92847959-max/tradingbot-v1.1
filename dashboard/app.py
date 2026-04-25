"""Enhanced Streamlit application for the Gold Trader Dashboard."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta
from dotenv import load_dotenv
import os
import sys
import time as _time
from typing import Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

# Ensure absolute imports like `database.*` and local `utils.py` work regardless of CWD.
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# Ensure local dashboard utils.py is imported (avoid accidental module shadowing).
from utils import DataBridge, run_async  # noqa: E402

# Load environment variables from project root (.env beside folders like dashboard/, database/).
load_dotenv(dotenv_path=os.path.join(_PROJECT_ROOT, ".env"), override=False)

# --- Configuration ---
st.set_page_config(
    page_title="Gold Trader Dashboard",
    page_icon="ðŸ’°",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for dark theme and styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700&display=swap');
    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
        font-family: 'Barlow', sans-serif;
    }
    .metric-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #D4AF37;
        margin-bottom: 20px;
    }
    .stMetric {
        background-color: #1E1E1E;
        padding: 15px;
        border-radius: 8px;
    }
    .status-online { color: #27AE60; font-weight: bold; }
    .status-offline { color: #C0392B; font-weight: bold; }
    .log-container {
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.8rem;
        background-color: #0E1117;
        padding: 10px;
        border-radius: 5px;
        color: #D4AF37;
        overflow-y: scroll;
        height: 500px;
    }
</style>
""", unsafe_allow_html=True)

# --- Initialization ---

def get_data_bridge():
    """Create a fresh DataBridge to avoid stale Streamlit cache after code changes."""
    return DataBridge()

bridge = get_data_bridge()

# --- Sidebar ---

def _has_real_env_value(key: str) -> bool:
    value = (os.getenv(key) or "").strip()
    if not value:
        return False
    return not (
        value.startswith("your-")
        or value.endswith("@example.com")
        or value == "sk-your-api-key-here"
    )


with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/gold-bars.png", width=80)
    st.title("Gold Trader v2.0")
    st.markdown("---")
    
    # Navigation
    page = st.radio("Navigation", ["Dashboard", "Trade History", "AI Signals", "System Logs"])
    
    st.markdown("---")
    st.subheader("Global Settings")
    timeframe = st.selectbox("Chart Timeframe", ["1m", "5m", "15m", "1h"], index=1)
    candle_count = st.slider("Candles", 100, 500, 240, 20)
    refresh_rate = st.slider("Auto-Refresh (s)", 10, 60, 30)
    show_trade_overlays = st.checkbox("Show Trade Overlays (SL/TP)", value=True)
    max_overlay_trades = st.slider("Max Trades On Chart", 1, 30, 10)
    tv_style = st.checkbox("TradingView Look", value=True)
    show_session_lines = st.checkbox("Session Lines (UTC)", value=True)
    show_last_price_line = st.checkbox("Last Price Line", value=True)

    broker_ready = all(
        _has_real_env_value(k)
        for k in ("CAPITAL_EMAIL", "CAPITAL_PASSWORD", "CAPITAL_API_KEY")
    )
    if not broker_ready:
        st.warning("Broker-Credentials fehlen in .env (CAPITAL_EMAIL/PASSWORD/API_KEY).")
    
    st.markdown("---")

    # Data Fetching for Sidebar
    risk = run_async(bridge.fetch_risk_status())

    # System Status & Risk
    st.markdown("**Risk Monitor**")
    status_color = "status-offline" if risk.get("kill_switch") else "status-online"
    status_text = "KILL SWITCH ACTIVE" if risk.get("kill_switch") else "TRADING ACTIVE"
    st.markdown(f"Status: <span class='{status_color}'>{status_text}</span>", unsafe_allow_html=True)
    
    drawdown = risk.get("drawdown", 0.0)
    st.progress(min(drawdown / 20.0, 1.0), text=f"Drawdown: {drawdown:.1f}%")
    st.write(f"Consecutive Losses: {risk.get('consecutive_losses', 0)}")
    
    if st.button("TRIGGER KILL SWITCH", type="primary", use_container_width=True, disabled=risk.get("kill_switch")):
        if run_async(bridge.trigger_kill_switch()):
            st.success("Kill switch activated in DB!")
            st.rerun()

    st.markdown("---")

    # Trading Mode Display
    trading_mode = os.getenv("TRADING_MODE", "auto")
    mode_label = "VOLL-AUTOMATISCH" if trading_mode == "auto" else "HALB-AUTOMATISCH"
    mode_color = "#27AE60" if trading_mode == "auto" else "#F39C12"
    st.markdown(f"**Trading-Modus:** <span style='color:{mode_color}'>{mode_label}</span>",
                unsafe_allow_html=True)
    if trading_mode == "semi_auto":
        st.info("Bot fragt per WhatsApp vor jedem Trade")

# --- Data Fetching ---

def _to_float_or_none(value) -> Optional[float]:
    try:
        if value is None:
            return None
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _add_trade_overlays(fig, candles_df: pd.DataFrame, trades_df: pd.DataFrame, max_trades: int) -> None:
    """Draw entry/exit markers and SL/TP lines similar to TradingView overlays."""
    if candles_df.empty or trades_df.empty:
        return
    if not isinstance(candles_df.index, pd.DatetimeIndex):
        return

    chart_start = pd.to_datetime(candles_df.index.min(), utc=True, errors="coerce")
    chart_end = pd.to_datetime(candles_df.index.max(), utc=True, errors="coerce")
    if pd.isna(chart_start) or pd.isna(chart_end):
        return

    if "Opened At" not in trades_df.columns:
        return

    overlay = trades_df.copy()
    overlay["Opened At"] = pd.to_datetime(overlay["Opened At"], utc=True, errors="coerce")
    overlay["Closed At"] = pd.to_datetime(overlay.get("Closed At"), utc=True, errors="coerce")
    overlay = overlay.dropna(subset=["Opened At"]).copy()
    if overlay.empty:
        return

    line_end = overlay["Closed At"].fillna(chart_end)
    visible = (overlay["Opened At"] <= chart_end) & (line_end >= chart_start)
    overlay = overlay.loc[visible].copy()
    if overlay.empty:
        return

    overlay = overlay.sort_values("Opened At", ascending=False).head(int(max_trades))

    legend_shown = {
        "entry_marker": False,
        "exit_marker": False,
        "entry_line": False,
        "sl_line": False,
        "tp_line": False,
    }

    for _, trade in overlay.iterrows():
        direction = str(trade.get("Direction", "")).upper()
        if direction not in {"BUY", "SELL"}:
            continue

        entry = _to_float_or_none(trade.get("Entry"))
        stop_loss = _to_float_or_none(trade.get("SL"))
        take_profit = _to_float_or_none(trade.get("TP"))
        exit_price = _to_float_or_none(trade.get("Exit"))

        opened_at = pd.to_datetime(trade.get("Opened At"), utc=True, errors="coerce")
        closed_at = pd.to_datetime(trade.get("Closed At"), utc=True, errors="coerce")
        if pd.isna(opened_at) or entry is None:
            continue

        segment_start = max(opened_at, chart_start)
        segment_end = closed_at if pd.notna(closed_at) else chart_end
        segment_end = min(segment_end, chart_end)
        if segment_start > segment_end:
            continue

        deal_id = str(trade.get("Deal ID") or f"trade-{trade.get('ID', '')}")
        color = "#26A69A" if direction == "BUY" else "#EF5350"
        marker_symbol = "triangle-up" if direction == "BUY" else "triangle-down"

        if chart_start <= opened_at <= chart_end:
            fig.add_trace(
                go.Scatter(
                    x=[opened_at],
                    y=[entry],
                    mode="markers",
                    name="Trade Entry",
                    showlegend=not legend_shown["entry_marker"],
                    marker=dict(symbol=marker_symbol, size=12, color=color, line=dict(color="#FFFFFF", width=1)),
                    hovertemplate=f"{deal_id}<br>{direction} Entry: %{{y:.2f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )
            legend_shown["entry_marker"] = True

        fig.add_trace(
            go.Scatter(
                x=[segment_start, segment_end],
                y=[entry, entry],
                mode="lines",
                name="Entry Line",
                showlegend=not legend_shown["entry_line"],
                line=dict(color=color, width=1, dash="dash"),
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )
        legend_shown["entry_line"] = True

        if stop_loss is not None:
            fig.add_trace(
                go.Scatter(
                    x=[segment_start, segment_end],
                    y=[stop_loss, stop_loss],
                    mode="lines",
                    name="Stop Loss",
                    showlegend=not legend_shown["sl_line"],
                    line=dict(color="#FF5252", width=1, dash="dot"),
                    hovertemplate=f"{deal_id}<br>SL: %{{y:.2f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )
            legend_shown["sl_line"] = True

        if take_profit is not None:
            fig.add_trace(
                go.Scatter(
                    x=[segment_start, segment_end],
                    y=[take_profit, take_profit],
                    mode="lines",
                    name="Take Profit",
                    showlegend=not legend_shown["tp_line"],
                    line=dict(color="#66BB6A", width=1, dash="dot"),
                    hovertemplate=f"{deal_id}<br>TP: %{{y:.2f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )
            legend_shown["tp_line"] = True

        if pd.notna(closed_at) and exit_price is not None and chart_start <= closed_at <= chart_end:
            fig.add_trace(
                go.Scatter(
                    x=[closed_at],
                    y=[exit_price],
                    mode="markers",
                    name="Trade Exit",
                    showlegend=not legend_shown["exit_marker"],
                    marker=dict(symbol="x", size=10, color="#F5F5F5", line=dict(color="#111111", width=1)),
                    hovertemplate=f"{deal_id}<br>Exit: %{{y:.2f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )
            legend_shown["exit_marker"] = True


def _format_ohlc_header(candles_df: pd.DataFrame, timeframe: str) -> tuple[str, str]:
    if candles_df.empty:
        return f"XAUUSD  {timeframe.upper()}  No Data", "#D1D4DC"

    last = candles_df.iloc[-1]
    prev_close = float(candles_df["close"].iloc[-2]) if len(candles_df) > 1 else float(last["close"])
    close = float(last["close"])
    change = close - prev_close
    change_pct = (change / prev_close * 100.0) if prev_close else 0.0
    color = "#26A69A" if change >= 0 else "#EF5350"
    header = (
        f"XAUUSD  {timeframe.upper()}   "
        f"O {float(last['open']):.2f}  "
        f"H {float(last['high']):.2f}  "
        f"L {float(last['low']):.2f}  "
        f"C {close:.2f}  "
        f"{change:+.2f} ({change_pct:+.2f}%)"
    )
    return header, color


def _add_last_price_line(fig, candles_df: pd.DataFrame) -> None:
    if candles_df.empty:
        return
    close = float(candles_df["close"].iloc[-1])
    prev_close = float(candles_df["close"].iloc[-2]) if len(candles_df) > 1 else close
    color = "#26A69A" if close >= prev_close else "#EF5350"
    fig.add_hline(
        y=close,
        row=1,
        col=1,
        line_width=1,
        line_dash="dot",
        line_color=color,
        annotation_text=f"{close:.2f}",
        annotation_position="right",
        annotation_font_color=color,
    )


def _add_session_lines(fig, candles_df: pd.DataFrame) -> None:
    if candles_df.empty or not isinstance(candles_df.index, pd.DatetimeIndex):
        return

    idx_utc = pd.to_datetime(candles_df.index, utc=True, errors="coerce")
    if idx_utc.isna().all():
        return

    start_ts = idx_utc.min()
    end_ts = idx_utc.max()
    if pd.isna(start_ts) or pd.isna(end_ts):
        return

    day = start_ts.normalize()
    end_day = end_ts.normalize()
    while day <= end_day:
        for hour, minute, color in (
            (8, 0, "rgba(61, 139, 255, 0.50)"),   # London open (UTC)
            (13, 30, "rgba(255, 152, 0, 0.50)"),  # New York open (UTC)
        ):
            ts = day + timedelta(hours=hour, minutes=minute)
            if start_ts <= ts <= end_ts:
                fig.add_shape(
                    type="line",
                    x0=ts,
                    x1=ts,
                    y0=0,
                    y1=1,
                    xref="x",
                    yref="paper",
                    line=dict(color=color, width=1, dash="dash"),
                )
        day += timedelta(days=1)


def _add_chart_watermark(fig, timeframe: str) -> None:
    fig.add_annotation(
        x=0.01,
        y=0.98,
        xref="paper",
        yref="paper",
        showarrow=False,
        text=f"XAUUSD  {timeframe.upper()}",
        font=dict(size=26, color="rgba(209, 212, 220, 0.14)"),
        xanchor="left",
        yanchor="top",
    )


def fetch_all_data():
    account = run_async(bridge.fetch_account_info())
    trades_df = run_async(bridge.fetch_recent_trades(limit=50))
    signals_df = run_async(bridge.fetch_recent_signals(limit=20))
    candles_df = run_async(bridge.fetch_candles(timeframe=timeframe, count=candle_count))
    return account, trades_df, signals_df, candles_df

account, trades_df, signals_df, candles_df = fetch_all_data()
data_status = bridge.get_data_status() if hasattr(bridge, "get_data_status") else {}
data_errors = bridge.get_data_errors() if hasattr(bridge, "get_data_errors") else {}

# --- Main Dashboard ---

if page == "Dashboard":
    if data_status.get("trades") == "broker_fallback":
        st.info("PostgreSQL nicht erreichbar: Trades kommen aktuell direkt vom Broker (nur offene Positionen).")
    elif data_status.get("trades") == "unavailable":
        st.warning("Keine Trade-Daten verfuegbar (DB und Broker aktuell nicht erreichbar).")

    if data_status.get("candles") == "synthetic":
        st.warning("Live-Marktdaten nicht verfuegbar: Chart zeigt derzeit synthetische Kerzen.")
    elif data_status.get("candles") == "unavailable":
        st.error("Keine Chartdaten verfuegbar.")

    if data_status.get("signals") == "unavailable":
        st.info("Signal-Historie derzeit nicht verfuegbar (DB offline).")

    if data_errors:
        with st.expander("Diagnose", expanded=False):
            for key, msg in data_errors.items():
                st.code(f"{key}: {msg}")

    # 1. Top Metrics
    st.subheader("Account Overview")
    m1, m2, m3, m4 = st.columns(4)
    
    m1.metric("Balance", f"{account.get('balance', 0.0):.2f} {account.get('currency', 'USD')}")
    m2.metric("Equity", f"{account.get('equity', 0.0):.2f} {account.get('currency', 'USD')}")
    m3.metric("Available Margin", f"{account.get('available', 0.0):.2f}")
    
    daily_pnl = risk.get("daily_pnl", 0.0)
    pnl_pct = (daily_pnl / account.get('balance', 1)) * 100 if account.get('balance', 0) > 0 else 0
    m4.metric("Daily P&L", f"{daily_pnl:+.2f} USD", delta=f"{pnl_pct:+.2f}%")
    
    st.markdown("---")
    
    # 2. Chart & Recent Signals
    col_chart, col_signals = st.columns([2, 1])
    
    with col_chart:
        if not candles_df.empty:
            from plotly.subplots import make_subplots
            ohlc_header, header_color = _format_ohlc_header(candles_df, timeframe)
            if tv_style:
                st.markdown(
                    (
                        "<div style='font-size:0.95rem; font-weight:600; margin-bottom:6px; color:"
                        f"{header_color};'>{ohlc_header}</div>"
                    ),
                    unsafe_allow_html=True,
                )

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                vertical_spacing=0.03, subplot_titles=(None, "RSI 14"),
                                row_heights=[0.8, 0.2])
            
            fig.add_trace(go.Candlestick(
                x=candles_df.index, open=candles_df['open'], high=candles_df['high'],
                low=candles_df['low'], close=candles_df['close'], name="Gold",
                increasing_line_color="#26A69A", decreasing_line_color="#EF5350",
                increasing_fillcolor="#26A69A", decreasing_fillcolor="#EF5350",
            ), row=1, col=1)
            
            for ema, color in [('ema_9', '#FF9800'), ('ema_21', '#2196F3'), 
                               ('ema_50', '#9C27B0'), ('ema_200', '#F44336')]:
                if ema in candles_df.columns:
                    fig.add_trace(go.Scatter(
                        x=candles_df.index, y=candles_df[ema], mode='lines', name=ema, line=dict(width=1, color=color)
                    ), row=1, col=1)
            
            if 'bb_upper' in candles_df.columns:
                fig.add_trace(go.Scatter(x=candles_df.index, y=candles_df['bb_upper'], line=dict(width=0.5, dash='dash', color='grey'), name='BB Upper'), row=1, col=1)
                fig.add_trace(go.Scatter(x=candles_df.index, y=candles_df['bb_lower'], line=dict(width=0.5, dash='dash', color='grey'), name='BB Lower', fill='tonexty'), row=1, col=1)
            
            if 'rsi_14' in candles_df.columns:
                fig.add_trace(go.Scatter(x=candles_df.index, y=candles_df['rsi_14'], line=dict(color='#FFD700'), name='RSI'), row=2, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

            if show_trade_overlays:
                _add_trade_overlays(
                    fig=fig,
                    candles_df=candles_df,
                    trades_df=trades_df,
                    max_trades=max_overlay_trades,
                )

            if tv_style:
                _add_chart_watermark(fig, timeframe)
            if show_session_lines:
                _add_session_lines(fig, candles_df)
            if show_last_price_line:
                _add_last_price_line(fig, candles_df)
            
            fig.update_layout(
                template="plotly_dark",
                height=640 if tv_style else 600,
                xaxis_rangeslider_visible=False,
                margin=dict(l=10, r=10, t=30, b=10),
                plot_bgcolor="#131722",
                paper_bgcolor="#131722",
                font=dict(color="#D1D4DC"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                hovermode="x",
                dragmode="pan",
                hoverdistance=100,
                spikedistance=-1,
            )
            fig.update_xaxes(
                showgrid=True,
                gridcolor="#1F2937",
                showline=True,
                linecolor="#3A3F4B",
                showspikes=True,
                spikemode="across",
                spikesnap="cursor",
                spikecolor="#8A8F98",
                spikethickness=1,
            )
            fig.update_yaxes(
                showgrid=True,
                gridcolor="#1F2937",
                zeroline=False,
                showline=True,
                linecolor="#3A3F4B",
                side="right",
                showspikes=True,
                spikecolor="#8A8F98",
                spikethickness=1,
            )
            fig.update_yaxes(range=[0, 100], row=2, col=1)

            if tv_style:
                fig.update_xaxes(
                    rangeselector=dict(
                        buttons=[
                            dict(count=1, label="1D", step="day", stepmode="backward"),
                            dict(count=7, label="1W", step="day", stepmode="backward"),
                            dict(count=1, label="1M", step="month", stepmode="backward"),
                            dict(step="all", label="All"),
                        ],
                        bgcolor="#131722",
                        activecolor="#2A2E39",
                        font=dict(color="#D1D4DC"),
                    ),
                    row=1,
                    col=1,
                )

            st.plotly_chart(
                fig,
                width="stretch",
                config={
                    "displaylogo": False,
                    "scrollZoom": True,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                },
            )
        else:
            st.warning("No candle data available.")

    with col_signals:
        st.subheader("Live Signals")
        if not signals_df.empty:
            def fmt_action(a): return "ðŸŸ¢ BUY" if a == "BUY" else "ðŸ”´ SELL" if a == "SELL" else "âšª HOLD"
            display_signals = signals_df[["Timestamp", "Action", "Confidence", "Status"]].copy()
            display_signals["Action"] = display_signals["Action"].apply(fmt_action)
            st.dataframe(display_signals, width="stretch", hide_index=True)
        else:
            st.info("No signals.")

    st.markdown("---")

    # 3. Active Positions with Manual Close
    st.subheader("Active Positions")
    if not trades_df.empty:
        open_trades = trades_df[trades_df["Status"] == "OPEN"]
        if not open_trades.empty:
            # Using data_editor for "Close" functionality simulation
            # Streamlit 1.23+ ButtonColumn is ideal, but let's use selectbox for now
            # as it's more compatible across versions
            for idx, row in open_trades.iterrows():
                c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([1, 1, 1, 1, 1, 1, 1, 1])
                c1.write(f"**{row['Direction']}**")
                c2.write(f"{row['Lot Size']} lots")
                c3.write(f"Entry: {row['Entry']}")
                sl_txt = f"{row['SL']:.2f}" if pd.notna(row.get("SL")) else "-"
                tp_txt = f"{row['TP']:.2f}" if pd.notna(row.get("TP")) else "-"
                c4.write(f"SL: {sl_txt}")
                c5.write(f"TP: {tp_txt}")
                c6.write(f"P&L: **{row['P&L']:+.2f}**")
                c7.write(f"ID: {row['Deal ID']}")
                close_key = row["Deal ID"] if pd.notna(row.get("Deal ID")) else f"id_{row['ID']}"
                if c8.button("Close x", key=f"close_{close_key}"):
                    if pd.isna(row.get("Deal ID")):
                        st.warning("No broker deal ID for this trade.")
                    elif run_async(bridge.close_position(row["Deal ID"])):
                        st.success(f"Closing {row['Deal ID']}...")
                        st.rerun()
        else:
            st.info("No active positions.")

elif page == "Trade History":
    st.subheader("Trade Performance")
    if not trades_df.empty:
        history_df = trades_df[trades_df["Status"] != "OPEN"]
        if not history_df.empty:
            wins = (history_df["P&L"] > 0).sum()
            losses = (history_df["P&L"] < 0).sum()
            win_rate = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0
            
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Win Rate", f"{win_rate:.1f}%")
            s2.metric("Profit Factor", f"{(history_df[history_df['P&L']>0]['P&L'].sum() / abs(history_df[history_df['P&L']<0]['P&L'].sum() or 1)):.2f}")
            s3.metric("Total Trades", f"{len(history_df)}")
            s4.metric("Net P&L", f"{history_df['P&L'].sum():+.2f} USD")
            
            st.dataframe(history_df, width="stretch", hide_index=True)
    else:
        st.info("No history.")

elif page == "AI Signals":
    st.subheader("AI Decision Deep-Dive")
    if not signals_df.empty:
        for idx, row in signals_df.iterrows():
            with st.expander(f"{row['Timestamp']} - {row['Action']} ({row['Confidence']})"):
                st.write("**Reasoning:**")
                st.json(row["Reasoning"])
                st.write(f"**Execution Price:** {row['Price']}")
                st.write(f"**Timeframe:** {row.get('Timeframe', '5m')}")

elif page == "System Logs":
    st.subheader("Real-time Trading Logs")
    if st.button("Refresh Logs"):
        st.rerun()
    
    logs = bridge.get_latest_logs(100)
    log_text = "".join(logs)
    st.markdown(f'<div class="log-container"><pre>{log_text}</pre></div>', unsafe_allow_html=True)

# --- Auto Refresh ---
if refresh_rate > 0:
    _time.sleep(refresh_rate)
    st.rerun()

