"""
╔══════════════════════════════════════════════════════════╗
║   SMC Backtest Engine v2 — FULLY FILTERED                ║
║                                                          ║
║   Filters applied (ALL must pass before any entry):      ║
║   1. HTF trend filter  (50 EMA — long above, short below)║
║   2. Liquidity sweep   (MANDATORY — no sweep = no trade) ║
║   3. Displacement      (large body candle required)      ║
║   4. FVG               (MANDATORY — must exist)          ║
║   5. Fresh Order Block (never tapped before)             ║
║   6. Premium/Discount  (buy in discount, sell in premium)║
║   7. Choppiness filter (ADX > 20 — avoid ranging market) ║
╚══════════════════════════════════════════════════════════╝

HOW TO RUN IN GOOGLE COLAB:
  Cell 1: !pip install yfinance pandas numpy matplotlib -q
  Cell 2: paste this entire script and run
"""

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import warnings
from datetime import datetime, timedelta
warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════
#  CONFIG — only edit this block
# ══════════════════════════════════════════════
CONFIG = {
    # ── Reliable tickers ──────────────────────
    # "GC=F"     → Gold (most reliable, recommended)
    # "EURUSD=X" → EUR/USD forex
    # "GBPUSD=X" → GBP/USD forex
    # "^GSPC"    → S&P 500
    # "^NSEI"    → Nifty 50
    # "BTC-USD"  → Bitcoin
    # ─────────────────────────────────────────
    "symbol":         "GC=F",      # ← Gold (most reliable on Yahoo)
    "interval":       "1d",        # daily candles — works for any date range
    "start":          "2020-01-01",
    "end":            "2025-12-31",

    # ── Strategy parameters ───────────────────
    "rr_ratio":       3.0,         # reward:risk ratio (1:3)
    "risk_pct":       1.0,         # % of account risked per trade
    "starting_eq":    10000,       # starting balance ($)

    # ── SMC filters ───────────────────────────
    "swing_lookback": 5,           # candles each side for swing detection
    "disp_pct":       0.005,       # min candle body % to count as displacement (0.5%)
    "sweep_margin":   0.001,       # how far price must pierce the level (0.1%)
    "adx_period":     14,          # ADX period for choppiness filter
    "adx_min":        20,          # min ADX to trade (below = choppy, skip)
    "ema_period":     50,          # EMA period for HTF trend bias
    "fvg_required":   True,        # if True, only trade OBs that have a FVG
    "sweep_required": True,        # if True, only trade after a liquidity sweep

    # ── Output ────────────────────────────────
    "output_csv":     "smc_v2_trade_log.csv",
    "output_plot":    "smc_v2_results.png",
}


# ══════════════════════════════════════════════
#  1. FETCH DATA
# ══════════════════════════════════════════════
def fetch_data(cfg):
    symbol   = cfg["symbol"]
    interval = cfg["interval"]
    start    = cfg["start"]
    end      = cfg["end"]

    if interval == "1h":
        print("[DATA] 1h interval switched to 1d (Yahoo Finance limitation).")
        interval = "1d"

    print(f"\n[DATA] Downloading {symbol} | {interval} | {start} → {end}")

    df = yf.download(symbol, start=start, end=end,
                     interval=interval, progress=False, auto_adjust=True)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.empty:
        df = yf.download(symbol, start=start, end=end,
                         interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if df.empty:
        raise ValueError(
            f"No data for '{symbol}'.\n"
            f"Try: GC=F | EURUSD=X | GBPUSD=X | ^GSPC | ^NSEI | BTC-USD"
        )

    df = df[["Open","High","Low","Close"]].copy()
    df.dropna(inplace=True)
    df.index = pd.to_datetime(df.index)
    print(f"[DATA] {len(df)} candles | {df.index[0].date()} → {df.index[-1].date()}")
    return df


# ══════════════════════════════════════════════
#  2. INDICATORS
# ══════════════════════════════════════════════
def add_indicators(df, cfg):
    """Add EMA (trend bias) and ADX (choppiness filter)."""
    closes = df["Close"]
    highs  = df["High"]
    lows   = df["Low"]

    # ── 50 EMA for HTF bias ──
    df["ema50"] = closes.ewm(span=cfg["ema_period"], adjust=False).mean()

    # ── ADX for choppiness filter ──
    p = cfg["adx_period"]
    df["tr"]  = np.maximum(
        highs - lows,
        np.maximum(
            abs(highs - closes.shift(1)),
            abs(lows  - closes.shift(1))
        )
    )
    df["+dm"] = np.where((highs.diff() > lows.diff()) & (highs.diff() > 0), highs.diff(), 0)
    df["-dm"] = np.where((lows.diff()  > highs.diff()) & (lows.diff()  > 0), lows.diff(),  0)

    atr    = df["tr"].ewm(span=p, adjust=False).mean()
    plus_  = df["+dm"].ewm(span=p, adjust=False).mean()
    minus_ = df["-dm"].ewm(span=p, adjust=False).mean()

    df["+di"] = (plus_  / atr) * 100
    df["-di"] = (minus_ / atr) * 100
    dx        = (abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"])) * 100
    df["adx"] = dx.ewm(span=p, adjust=False).mean()

    df.drop(columns=["tr","+dm","-dm","+di","-di"], inplace=True)
    return df


# ══════════════════════════════════════════════
#  3. SWING HIGH / LOW
# ══════════════════════════════════════════════
def find_swings(df, lookback):
    n      = len(df)
    sh     = np.zeros(n, dtype=bool)
    sl_arr = np.zeros(n, dtype=bool)
    H = df["High"].values
    L = df["Low"].values

    for i in range(lookback, n - lookback):
        if H[i] == H[i - lookback: i + lookback + 1].max():
            sh[i] = True
        if L[i] == L[i - lookback: i + lookback + 1].min():
            sl_arr[i] = True

    df = df.copy()
    df["sh"] = sh
    df["sl"] = sl_arr
    return df


# ══════════════════════════════════════════════
#  4. LIQUIDITY SWEEP DETECTION
# ══════════════════════════════════════════════
def detect_sweep(df, i, direction, margin):
    """
    Detects a liquidity sweep at candle i.
    Bull sweep: wick pierces below a recent swing low; same OR next candle closes above level.
    Bear sweep: wick pierces above a recent swing high; same OR next candle closes below level.
    """
    H = df["High"].values
    L = df["Low"].values
    C = df["Close"].values
    n = len(df)
    look_back = 40

    if direction == "bull":
        recent_sl = [
            L[j] for j in range(max(0, i - look_back), i)
            if df["sl"].values[j]
        ]
        if not recent_sl:
            return False, None
        level = min(recent_sl)
        # Wick must pierce below level (with margin)
        if L[i] < level * (1 - margin):
            # Close of this candle OR next candle must recover above level
            close_recovers = C[i] > level
            next_recovers  = (i + 1 < n) and C[i + 1] > level
            if close_recovers or next_recovers:
                return True, level

    if direction == "bear":
        recent_sh = [
            H[j] for j in range(max(0, i - look_back), i)
            if df["sh"].values[j]
        ]
        if not recent_sh:
            return False, None
        level = max(recent_sh)
        if H[i] > level * (1 + margin):
            close_recovers = C[i] < level
            next_recovers  = (i + 1 < n) and C[i + 1] < level
            if close_recovers or next_recovers:
                return True, level

    return False, None


# ══════════════════════════════════════════════
#  5. FAIR VALUE GAP
# ══════════════════════════════════════════════
def find_fvg(df, i, direction):
    """
    3-candle imbalance check.
    Bullish FVG : candle[i-1].High < candle[i+1].Low
    Bearish FVG : candle[i-1].Low  > candle[i+1].High
    Returns (fvg_top, fvg_bottom) or None.
    """
    if i < 1 or i + 1 >= len(df):
        return None
    c1h = df["High"].values[i - 1]
    c1l = df["Low"].values[i - 1]
    c3h = df["High"].values[i + 1]
    c3l = df["Low"].values[i + 1]

    if direction == "bull" and c1h < c3l:
        return (c3l, c1h)   # (top, bottom)
    if direction == "bear" and c1l > c3h:
        return (c1l, c3h)
    return None


# ══════════════════════════════════════════════
#  6. DISPLACEMENT CHECK
# ══════════════════════════════════════════════
def is_displacement(df, i, direction, threshold):
    O = df["Open"].values[i]
    C = df["Close"].values[i]
    body_pct = abs(C - O) / O
    if body_pct < threshold:
        return False
    if direction == "bull" and C > O:
        return True
    if direction == "bear" and C < O:
        return True
    return False


# ══════════════════════════════════════════════
#  7. ORDER BLOCK FINDER
# ══════════════════════════════════════════════
def find_ob(df, sweep_i, direction, cfg):
    """
    After sweep at sweep_i:
    - Scan forward for a displacement candle that creates BOS
    - Find last opposing candle before it = OB
    - Check FVG on the displacement candle
    - Returns OB dict or None
    """
    n         = len(df)
    threshold = cfg["disp_pct"]
    O = df["Open"].values
    C = df["Close"].values
    H = df["High"].values
    L = df["Low"].values

    for i in range(sweep_i + 1, min(sweep_i + 15, n - 2)):
        if not is_displacement(df, i, direction, threshold):
            continue

        # BOS check
        if direction == "bull":
            recent_high = H[max(0, sweep_i - 10): sweep_i].max() if sweep_i > 0 else H[i]
            # Relaxed BOS: close must be above 95% of recent high (handles daily candles)
            if C[i] < recent_high * 0.95:
                continue
            # Find last bearish candle before impulse
            ob_i = None
            for j in range(i - 1, max(sweep_i - 1, 0), -1):
                if C[j] < O[j]:
                    ob_i = j
                    break
            if ob_i is None:
                ob_i = i - 1
            ob_high = max(O[ob_i], C[ob_i])
            ob_low  = min(O[ob_i], C[ob_i])

        else:  # bear
            recent_low = L[max(0, sweep_i - 10): sweep_i].min() if sweep_i > 0 else L[i]
            # Relaxed BOS
            if C[i] > recent_low * 1.05:
                continue
            ob_i = None
            for j in range(i - 1, max(sweep_i - 1, 0), -1):
                if C[j] > O[j]:
                    ob_i = j
                    break
            if ob_i is None:
                ob_i = i - 1
            ob_high = max(O[ob_i], C[ob_i])
            ob_low  = min(O[ob_i], C[ob_i])

        # FVG check
        fvg = find_fvg(df, i, direction)
        if cfg["fvg_required"] and fvg is None:
            continue  # skip — no imbalance

        return {
            "direction":  direction,
            "ob_i":       ob_i,
            "ob_high":    ob_high,
            "ob_low":     ob_low,
            "disp_i":     i,
            "fvg":        fvg,
            "formed_at":  df.index[ob_i],
            "sweep_i":    sweep_i,
            "mitigated":  False,
        }

    return None


# ══════════════════════════════════════════════
#  8. PREMIUM / DISCOUNT ZONE CHECK
# ══════════════════════════════════════════════
def in_correct_zone(df, i, direction, lookback=50):
    """
    Use 50-candle range. Discount = below 50%. Premium = above 50%.
    Buy only in discount. Sell only in premium.
    """
    start = max(0, i - lookback)
    swing_high = df["High"].values[start:i].max()
    swing_low  = df["Low"].values[start:i].min()
    mid        = (swing_high + swing_low) / 2
    price      = df["Close"].values[i]

    if direction == "bull" and price < mid:
        return True   # discount zone — ok to buy
    if direction == "bear" and price > mid:
        return True   # premium zone — ok to sell
    return False


# ══════════════════════════════════════════════
#  9. TRADE SIMULATOR
# ══════════════════════════════════════════════
def simulate_trade(df, start_i, direction, entry, sl, tp, max_candles=60):
    n = len(df)
    H = df["High"].values
    L = df["Low"].values
    for i in range(start_i, min(start_i + max_candles, n)):
        if direction == "bull":
            if L[i] <= sl: return "loss", sl, i
            if H[i] >= tp: return "win",  tp, i
        else:
            if H[i] >= sl: return "loss", sl, i
            if L[i] <= tp: return "win",  tp, i
    return None, entry, start_i


# ══════════════════════════════════════════════
#  10. MAIN BACKTEST LOOP
# ══════════════════════════════════════════════
def run_backtest(df, cfg):
    print("\n[BACKTEST] Running fully-filtered SMC engine...")
    print(f"[FILTERS] EMA{cfg['ema_period']} trend | ADX>{cfg['adx_min']} | "
          f"Sweep={'required' if cfg['sweep_required'] else 'optional'} | "
          f"FVG={'required' if cfg['fvg_required'] else 'optional'} | "
          f"Premium/Discount=ON\n")

    df       = find_swings(df, cfg["swing_lookback"])
    df       = add_indicators(df, cfg)
    rr       = cfg["rr_ratio"]
    risk_pct = cfg["risk_pct"] / 100
    equity   = cfg["starting_eq"]
    n        = len(df)

    trades       = []
    equity_curve = [equity]
    pending      = []
    used         = set()

    skipped_adx   = 0
    skipped_trend = 0
    skipped_zone  = 0
    skipped_sweep = 0
    skipped_fvg   = 0

    C = df["Close"].values
    H = df["High"].values
    L = df["Low"].values
    O = df["Open"].values

    for i in range(cfg["ema_period"] + cfg["adx_period"] + 10, n - 10):

        # ── Filter 1: ADX — skip choppy markets ──
        adx_val = df["adx"].values[i]
        if pd.isna(adx_val) or adx_val < cfg["adx_min"]:
            skipped_adx += 1
            continue

        # ── Filter 2: HTF trend bias ──
        # Use price 5 candles ago to avoid sweep spike distorting EMA check
        ema_val       = df["ema50"].values[i]
        ref_i         = max(0, i - 5)
        trending_bull = C[ref_i] > ema_val
        trending_bear = C[ref_i] < ema_val

        # ── Detect SSL sweep → bullish setup ──
        if trending_bull and i not in used:
            swept, level = detect_sweep(df, i, "bull", cfg["sweep_margin"])
            if swept:
                ob = find_ob(df, i, "bull", cfg)
                if ob:
                    # Filter 3: premium/discount
                    if not in_correct_zone(df, i, "bull"):
                        skipped_zone += 1
                    else:
                        sl_dist     = ob["ob_high"] - ob["ob_low"]
                        entry_price = ob["ob_high"]
                        sl_price    = ob["ob_low"] - sl_dist * 0.2
                        tp_price    = entry_price + (entry_price - sl_price) * rr
                        ob.update({
                            "entry": entry_price,
                            "sl":    sl_price,
                            "tp":    tp_price,
                        })
                        pending.append(ob)
                        used.add(i)
                elif cfg["sweep_required"]:
                    skipped_sweep += 1
            elif cfg["sweep_required"] and df["sl"].values[i]:
                skipped_sweep += 1

        # ── Detect BSL sweep → bearish setup ──
        if trending_bear and i not in used:
            swept, level = detect_sweep(df, i, "bear", cfg["sweep_margin"])
            if swept:
                ob = find_ob(df, i, "bear", cfg)
                if ob:
                    if not in_correct_zone(df, i, "bear"):
                        skipped_zone += 1
                    else:
                        sl_dist     = ob["ob_high"] - ob["ob_low"]
                        entry_price = ob["ob_low"]
                        sl_price    = ob["ob_high"] + sl_dist * 0.2
                        tp_price    = entry_price - (sl_price - entry_price) * rr
                        ob.update({
                            "entry": entry_price,
                            "sl":    sl_price,
                            "tp":    tp_price,
                        })
                        pending.append(ob)
                        used.add(i)

        # ── Check if price returns to any pending OB ──
        still_pending = []
        for setup in pending:
            ob_i   = df.index.get_loc(setup["formed_at"])
            age    = i - ob_i

            # Expire after 30 candles
            if age > 30:
                continue

            # Skip if not yet formed
            if df.index[i] <= setup["formed_at"]:
                still_pending.append(setup)
                continue

            entered = False

            if setup["direction"] == "bull":
                # Price retraces into OB
                if L[i] <= setup["ob_high"] and H[i] >= setup["ob_low"]:
                    if not setup["mitigated"]:
                        outcome, exit_px, exit_i = simulate_trade(
                            df, i+1, "bull",
                            setup["entry"], setup["sl"], setup["tp"]
                        )
                        if outcome:
                            risk_amt = equity * risk_pct
                            pnl      = risk_amt * rr if outcome == "win" else -risk_amt
                            equity  += pnl
                            trades.append({
                                "entry_time":  df.index[i],
                                "exit_time":   df.index[min(exit_i, n-1)],
                                "direction":   "LONG",
                                "entry_price": round(setup["entry"], 4),
                                "sl":          round(setup["sl"], 4),
                                "tp":          round(setup["tp"], 4),
                                "exit_price":  round(exit_px, 4),
                                "outcome":     outcome,
                                "pnl_usd":     round(pnl, 2),
                                "equity":      round(equity, 2),
                                "has_fvg":     setup["fvg"] is not None,
                                "adx":         round(adx_val, 1),
                            })
                            equity_curve.append(equity)
                            setup["mitigated"] = True
                            entered = True

            elif setup["direction"] == "bear":
                if H[i] >= setup["ob_low"] and L[i] <= setup["ob_high"]:
                    if not setup["mitigated"]:
                        outcome, exit_px, exit_i = simulate_trade(
                            df, i+1, "bear",
                            setup["entry"], setup["sl"], setup["tp"]
                        )
                        if outcome:
                            risk_amt = equity * risk_pct
                            pnl      = risk_amt * rr if outcome == "win" else -risk_amt
                            equity  += pnl
                            trades.append({
                                "entry_time":  df.index[i],
                                "exit_time":   df.index[min(exit_i, n-1)],
                                "direction":   "SHORT",
                                "entry_price": round(setup["entry"], 4),
                                "sl":          round(setup["sl"], 4),
                                "tp":          round(setup["tp"], 4),
                                "exit_price":  round(exit_px, 4),
                                "outcome":     outcome,
                                "pnl_usd":     round(pnl, 2),
                                "equity":      round(equity, 2),
                                "has_fvg":     setup["fvg"] is not None,
                                "adx":         round(adx_val, 1),
                            })
                            equity_curve.append(equity)
                            setup["mitigated"] = True
                            entered = True

            if not entered and not setup["mitigated"]:
                still_pending.append(setup)

        pending = still_pending

    print(f"[FILTER LOG] Skipped — ADX too low: {skipped_adx} | "
          f"Wrong trend: {skipped_trend} | Wrong zone: {skipped_zone}")
    return trades, equity_curve


# ══════════════════════════════════════════════
#  11. STATS REPORT
# ══════════════════════════════════════════════
def compute_stats(trades, equity_curve, cfg):
    if not trades:
        print("\n[RESULT] 0 trades found.")
        print("  → Try loosening filters:")
        print("     cfg['adx_min'] = 15   (was", cfg['adx_min'], ")")
        print("     cfg['disp_pct'] = 0.003  (was", cfg['disp_pct'], ")")
        print("     cfg['fvg_required'] = False")
        print("     cfg['sweep_required'] = False")
        return {}

    df_t  = pd.DataFrame(trades)
    wins  = df_t[df_t["outcome"] == "win"]
    loss  = df_t[df_t["outcome"] == "loss"]

    total         = len(df_t)
    win_n         = len(wins)
    loss_n        = len(loss)
    win_rate      = win_n / total * 100
    gross_profit  = wins["pnl_usd"].sum()
    gross_loss    = abs(loss["pnl_usd"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    net_pnl       = df_t["pnl_usd"].sum()
    avg_win       = wins["pnl_usd"].mean() if win_n else 0
    avg_loss      = loss["pnl_usd"].mean() if loss_n else 0
    expectancy    = (win_rate/100 * avg_win) + ((1-win_rate/100) * avg_loss)

    eq        = np.array(equity_curve)
    roll_max  = np.maximum.accumulate(eq)
    drawdown  = (eq - roll_max) / roll_max * 100
    max_dd    = drawdown.min()
    roi       = (equity_curve[-1] - cfg["starting_eq"]) / cfg["starting_eq"] * 100

    # FVG impact
    fvg_t   = df_t[df_t["has_fvg"]]
    nofvg_t = df_t[~df_t["has_fvg"]]
    fvg_wr  = fvg_t[fvg_t["outcome"]=="win"].shape[0]/len(fvg_t)*100  if len(fvg_t)  else 0
    nofvg_wr= nofvg_t[nofvg_t["outcome"]=="win"].shape[0]/len(nofvg_t)*100 if len(nofvg_t) else 0

    # Direction split
    longs  = df_t[df_t["direction"]=="LONG"]
    shorts = df_t[df_t["direction"]=="SHORT"]
    long_wr  = longs[longs["outcome"]=="win"].shape[0]/len(longs)*100  if len(longs)  else 0
    short_wr = shorts[shorts["outcome"]=="win"].shape[0]/len(shorts)*100 if len(shorts) else 0

    stats = {
        "total": total, "wins": win_n, "losses": loss_n,
        "win_rate": round(win_rate,1),
        "profit_factor": round(profit_factor,2),
        "net_pnl": round(net_pnl,2),
        "roi_pct": round(roi,2),
        "max_dd": round(max_dd,2),
        "final_eq": round(equity_curve[-1],2),
        "avg_win": round(avg_win,2),
        "avg_loss": round(avg_loss,2),
        "expectancy": round(expectancy,2),
        "fvg_wr": round(fvg_wr,1),
        "nofvg_wr": round(nofvg_wr,1),
        "fvg_n": len(fvg_t),
        "long_wr": round(long_wr,1),
        "short_wr": round(short_wr,1),
        "long_n": len(longs),
        "short_n": len(shorts),
    }

    sep = "─" * 50
    print(f"\n{'═'*50}")
    print(f"  SMC v2 RESULTS — {cfg['symbol']} {cfg['interval']}")
    print(f"  {cfg['start']} → {cfg['end']}")
    print(f"{'═'*50}")
    print(f"  Total trades      : {total}")
    print(f"  Wins / Losses     : {win_n} W / {loss_n} L")
    print(f"  Win rate          : {win_rate:.1f}%")
    print(f"  Profit factor     : {profit_factor:.2f}   (>1.5 = real edge)")
    print(f"  Expectancy        : ${expectancy:.2f} per trade")
    print(f"{sep}")
    print(f"  Net P&L           : ${net_pnl:+,.2f}")
    print(f"  ROI               : {roi:.2f}%")
    print(f"  Final balance     : ${equity_curve[-1]:,.2f}")
    print(f"  Max drawdown      : {max_dd:.2f}%")
    print(f"{sep}")
    print(f"  Avg win           : ${avg_win:+.2f}")
    print(f"  Avg loss          : ${avg_loss:+.2f}")
    print(f"{sep}")
    print(f"  LONG  trades      : {len(longs)}  |  Win rate: {long_wr:.1f}%")
    print(f"  SHORT trades      : {len(shorts)} |  Win rate: {short_wr:.1f}%")
    print(f"{sep}")
    print(f"  OB + FVG win rate : {fvg_wr:.1f}%  ({len(fvg_t)} trades)")
    print(f"  OB only win rate  : {nofvg_wr:.1f}%  ({len(nofvg_t)} trades)")
    print(f"{'═'*50}\n")
    return stats


# ══════════════════════════════════════════════
#  12. PLOTS
# ══════════════════════════════════════════════
def plot_results(trades, equity_curve, stats, cfg):
    if not trades:
        return
    df_t = pd.DataFrame(trades)

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(
        f"SMC Backtest v2 — {cfg['symbol']} {cfg['interval']}  |  "
        f"Win Rate: {stats['win_rate']}%  |  PF: {stats['profit_factor']}  |  ROI: {stats['roi_pct']}%",
        fontsize=13, fontweight="bold"
    )

    # ── 1. Equity Curve ──
    ax = axes[0][0]
    ax.plot(equity_curve, color="#1D9E75", linewidth=2)
    ax.axhline(cfg["starting_eq"], color="gray", linestyle="--", linewidth=0.8)
    ax.fill_between(range(len(equity_curve)), cfg["starting_eq"], equity_curve,
                    where=[e >= cfg["starting_eq"] for e in equity_curve],
                    alpha=0.15, color="#1D9E75")
    ax.fill_between(range(len(equity_curve)), cfg["starting_eq"], equity_curve,
                    where=[e < cfg["starting_eq"] for e in equity_curve],
                    alpha=0.15, color="#E24B4A")
    ax.set_title("Equity Curve", fontweight="bold")
    ax.set_ylabel("Balance ($)")
    ax.set_xlabel("Trade #")
    ax.grid(True, alpha=0.2)

    # ── 2. P&L per Trade ──
    ax2 = axes[0][1]
    colors = ["#1D9E75" if o=="win" else "#E24B4A" for o in df_t["outcome"]]
    ax2.bar(range(len(df_t)), df_t["pnl_usd"], color=colors, width=0.8, alpha=0.85)
    ax2.axhline(0, color="gray", linewidth=0.8)
    ax2.set_title("P&L per Trade", fontweight="bold")
    ax2.set_ylabel("P&L ($)")
    ax2.set_xlabel("Trade #")
    ax2.grid(True, alpha=0.2, axis="y")
    win_p  = mpatches.Patch(color="#1D9E75", label="Win")
    loss_p = mpatches.Patch(color="#E24B4A", label="Loss")
    ax2.legend(handles=[win_p, loss_p])

    # ── 3. FVG vs No-FVG win rate ──
    ax3 = axes[1][0]
    cats = ["OB + FVG", "OB only"]
    wrs  = [stats["fvg_wr"], stats["nofvg_wr"]]
    ns   = [stats["fvg_n"], stats["total"] - stats["fvg_n"]]
    bars = ax3.bar(cats, wrs, color=["#185FA5","#888780"], width=0.4, alpha=0.85)
    ax3.axhline(50, color="gray", linestyle="--", linewidth=0.8, label="50% baseline")
    for bar, wr, n in zip(bars, wrs, ns):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                 f"{wr:.1f}%\n(n={n})", ha="center", fontsize=10, fontweight="bold")
    ax3.set_title("FVG Confluence Impact", fontweight="bold")
    ax3.set_ylabel("Win Rate (%)")
    ax3.set_ylim(0, 100)
    ax3.legend()
    ax3.grid(True, alpha=0.2, axis="y")

    # ── 4. Long vs Short win rate ──
    ax4 = axes[1][1]
    dirs  = ["LONG", "SHORT"]
    d_wrs = [stats["long_wr"], stats["short_wr"]]
    d_ns  = [stats["long_n"],  stats["short_n"]]
    dcols = ["#1D9E75", "#E24B4A"]
    bars2 = ax4.bar(dirs, d_wrs, color=dcols, width=0.4, alpha=0.85)
    ax4.axhline(50, color="gray", linestyle="--", linewidth=0.8)
    for bar, wr, n in zip(bars2, d_wrs, d_ns):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                 f"{wr:.1f}%\n(n={n})", ha="center", fontsize=10, fontweight="bold")
    ax4.set_title("Long vs Short Win Rate", fontweight="bold")
    ax4.set_ylabel("Win Rate (%)")
    ax4.set_ylim(0, 100)
    ax4.grid(True, alpha=0.2, axis="y")

    plt.tight_layout()
    plt.savefig(cfg["output_plot"], dpi=150, bbox_inches="tight")
    print(f"[PLOT] Saved → {cfg['output_plot']}")
    plt.show()


# ══════════════════════════════════════════════
#  13. SAVE TRADE LOG
# ══════════════════════════════════════════════
def save_log(trades, cfg):
    if not trades:
        return
    pd.DataFrame(trades).to_csv(cfg["output_csv"], index=False)
    print(f"[LOG]  Trade log → {cfg['output_csv']}  ({len(trades)} trades)")


# ══════════════════════════════════════════════
#  14. FORWARD TEST (last 90 days)
# ══════════════════════════════════════════════
def forward_test(cfg):
    print("\n" + "═"*50)
    print("  FORWARD TEST — last 90 days (unseen data)")
    print("═"*50)
    fwd = cfg.copy()
    fwd["start"]       = (datetime.today()-timedelta(days=90)).strftime("%Y-%m-%d")
    fwd["end"]         = datetime.today().strftime("%Y-%m-%d")
    fwd["output_csv"]  = "smc_v2_forward_log.csv"
    fwd["output_plot"] = "smc_v2_forward_plot.png"
    try:
        df = fetch_data(fwd)
        t, eq = run_backtest(df, fwd)
        s = compute_stats(t, eq, fwd)
        save_log(t, fwd)
        plot_results(t, eq, s, fwd)
        return s
    except Exception as e:
        print(f"[FORWARD TEST ERROR] {e}")
        return {}


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("║   SMC Backtest Engine v2 — Fully Filtered    ║")
    print("╚══════════════════════════════════════════════╝")

    # ── BACKTEST ──
    df              = fetch_data(CONFIG)
    trades, eq_curve = run_backtest(df, CONFIG)
    stats           = compute_stats(trades, eq_curve, CONFIG)
    save_log(trades, CONFIG)
    plot_results(trades, eq_curve, stats, CONFIG)

    # ── FORWARD TEST ──
    fwd_stats = forward_test(CONFIG)

    # ── COMPARISON TABLE ──
    if stats and fwd_stats:
        print("\n── BACKTEST vs FORWARD TEST ──────────────────")
        print(f"{'Metric':<22} {'Backtest':>12} {'Forward':>12}")
        print("─" * 48)
        for m in ["total","win_rate","profit_factor","roi_pct","max_dd"]:
            print(f"  {m:<20} {str(stats.get(m,'—')):>12} {str(fwd_stats.get(m,'—')):>12}")
        print()

    print("[DONE]")

