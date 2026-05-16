# ════════════════════════════════════════════════════════════
#  AlphaSMC Bot — GitHub Actions Scanner
#  Runs automatically every day at 8:15 AM IST
#  Writes signals.json to repo → dashboard reads it
#  No Colab. No manual steps. Fully automatic.
# ════════════════════════════════════════════════════════════

import os, json, smtplib, logging, time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytz

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

EMAIL_FROM = "alphapatel23@gmail.com"
EMAIL_PASS = os.environ.get("GMAIL_PASS", "")
EMAIL_TO   = "alphapatel23@gmail.com"
IST        = pytz.timezone("Asia/Kolkata")

ACCOUNT_CAPITAL    = 5000
RISK_PER_TRADE_PCT = 2.0
MIN_RRR            = 2.5
MIN_CONDITIONS     = 3
MIN_CONFIDENCE     = 65

WATCHLIST = [
    "RELIANCE.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS","TCS.NS",
    "BHARTIARTL.NS","SBIN.NS","AXISBANK.NS","KOTAKBANK.NS","LT.NS",
    "TATAMOTORS.BO","BAJFINANCE.NS","WIPRO.NS","HCLTECH.NS","SUNPHARMA.NS",
    "MARUTI.NS","TITAN.NS","ADANIENT.NS","NTPC.NS","POWERGRID.NS",
    "ONGC.NS","COALINDIA.NS","JSWSTEEL.NS","TATASTEEL.NS","HINDALCO.NS",
    "TECHM.NS","ULTRACEMCO.NS","NESTLEIND.NS","BRITANNIA.NS","DIVISLAB.NS",
    "DRREDDY.NS","CIPLA.NS","APOLLOHOSP.NS","BAJAJFINSV.NS","BAJAJ-AUTO.NS",
    "EICHERMOT.NS","HEROMOTOCO.NS","TATACONSUM.NS","ASIANPAINT.NS",
    "HINDUNILVR.NS","ITC.NS","MM.NS","INDUSINDBK.NS","BPCL.NS",
    "GRASIM.NS","LTIMINDUS.NS","SBILIFE.NS","HDFCLIFE.NS","UPL.NS","VEDL.NS",
    "SIEMENS.NS","HAL.NS","BEL.NS","IRCTC.NS","TRENT.NS","DMART.NS",
    "PERSISTENT.NS","COFORGE.NS","MPHASIS.NS","ZOMATO.NS",
    "TATAPOWER.NS","ADANIPORTS.NS","SAIL.NS","NMDC.NS","MRF.NS",
    "TVSMOTOR.NS","BHARATFORG.NS","HAVELLS.NS","POLYCAB.NS",
    "PAGEIND.NS","CGPOWER.NS","ABB.NS","RECLTD.NS","PFC.NS",
]

TICKER_NAME = {
    "TATAMOTORS.BO":"TATAMOTORS","MM.NS":"M&M","LTIMINDUS.NS":"LTIM"
}

STOCK_WIN_RATE = {
    "RELIANCE":0.64,"HDFCBANK":0.61,"ICICIBANK":0.63,"INFY":0.67,"TCS":0.65,
    "KOTAKBANK":0.62,"MARUTI":0.66,"BAJAJ-AUTO":0.68,"NESTLEIND":0.70,
    "BRITANNIA":0.69,"TITAN":0.65,"ASIANPAINT":0.64,"HINDUNILVR":0.63,
    "ITC":0.60,"M&M":0.64,"EICHERMOT":0.67,"LTIM":0.65,"HCLTECH":0.63,
    "WIPRO":0.59,"TECHM":0.61,"AXISBANK":0.60,"SBIN":0.58,"BHARTIARTL":0.62,
    "LT":0.61,"BAJFINANCE":0.63,"DRREDDY":0.62,"CIPLA":0.61,"SUNPHARMA":0.60,
    "SIEMENS":0.64,"HAL":0.65,"BEL":0.63,"IRCTC":0.66,"PERSISTENT":0.66,
    "COFORGE":0.65,"MPHASIS":0.64,"MRF":0.64,"HAVELLS":0.63,"POLYCAB":0.64,
    "DMART":0.66,"TRENT":0.65,"TATAMOTORS":0.60,"ADANIENT":0.59,
    "BAJAJFINSV":0.63,"DIVISLAB":0.59,"ZOMATO":0.56,"CGPOWER":0.63,"ABB":0.62,
}
STOCK_GRADE = {
    "RELIANCE":"A","HDFCBANK":"A","ICICIBANK":"A","INFY":"A","TCS":"A",
    "KOTAKBANK":"A","MARUTI":"A","BAJAJ-AUTO":"A","NESTLEIND":"A","BRITANNIA":"A",
    "TITAN":"A","ASIANPAINT":"A","HINDUNILVR":"A","ITC":"A","M&M":"A",
    "EICHERMOT":"A","DMART":"A","BAJFINANCE":"A","LTIM":"B","HCLTECH":"B",
    "WIPRO":"B","TECHM":"B","AXISBANK":"B","SBIN":"B","LT":"B","PERSISTENT":"B",
    "COFORGE":"B","HAL":"B","SIEMENS":"B","BEL":"B","IRCTC":"B","TRENT":"B",
    "TATAMOTORS":"B","ZOMATO":"C","ADANIENT":"B","CGPOWER":"B","ABB":"B",
}
SETUP_WIN_RATE = {
    "ChoCH+FVG":0.64,"Liq.Sweep+FVG":0.63,"OB Retest":0.61,"MSS+OB":0.59,"U-Turn":0.56,
}
TIMEFRAME_QUALITY = {"Daily":1.0,"Weekly":0.95,"4H":0.80,"1H":0.65}
SECTOR_BIAS = {
    "Banking":0.78,"IT":0.72,"Auto":0.75,"FMCG":0.68,"Energy":0.80,
    "Infra":0.70,"Pharma":0.62,"Metals":0.45,"Telecom":0.72,
    "Defence":0.70,"Railways":0.68,"Power":0.72,"Consumer":0.60,"Cement":0.65,
}
STOCK_SECTOR = {
    "RELIANCE":"Energy","HDFCBANK":"Banking","ICICIBANK":"Banking","INFY":"IT","TCS":"IT",
    "HCLTECH":"IT","WIPRO":"IT","TECHM":"IT","LTIM":"IT","PERSISTENT":"IT","COFORGE":"IT","MPHASIS":"IT",
    "BHARTIARTL":"Telecom","KOTAKBANK":"Banking","AXISBANK":"Banking","SBIN":"Banking",
    "BAJFINANCE":"Banking","LT":"Infra","ADANIENT":"Infra","SIEMENS":"Infra","ABB":"Infra",
    "HAVELLS":"Infra","POLYCAB":"Infra","CGPOWER":"Power","RECLTD":"Banking","PFC":"Banking",
    "TATAMOTORS":"Auto","MARUTI":"Auto","M&M":"Auto","BAJAJ-AUTO":"Auto","EICHERMOT":"Auto",
    "HEROMOTOCO":"Auto","TVSMOTOR":"Auto","MRF":"Auto","BHARATFORG":"Auto",
    "NESTLEIND":"FMCG","BRITANNIA":"FMCG","ITC":"FMCG","HINDUNILVR":"FMCG","TITAN":"FMCG",
    "ASIANPAINT":"FMCG","DMART":"FMCG","TRENT":"FMCG","PAGEIND":"FMCG",
    "SUNPHARMA":"Pharma","DRREDDY":"Pharma","CIPLA":"Pharma","APOLLOHOSP":"Pharma","DIVISLAB":"Pharma",
    "ONGC":"Energy","BPCL":"Energy","NTPC":"Energy","POWERGRID":"Energy","TATAPOWER":"Energy","COALINDIA":"Energy",
    "TATASTEEL":"Metals","JSWSTEEL":"Metals","HINDALCO":"Metals","SAIL":"Metals","NMDC":"Metals",
    "HAL":"Defence","BEL":"Defence",
    "IRCTC":"Railways","ULTRACEMCO":"Cement","GRASIM":"Cement",
    "ZOMATO":"Consumer","ADANIPORTS":"Infra","BAJAJFINSV":"Banking","INDUSINDBK":"Banking",
}

def clean_name(ticker):
    if ticker in TICKER_NAME: return TICKER_NAME[ticker]
    return ticker.replace(".NS","").replace(".BO","")

def calc_confidence(name, setup, tf, conds, htf_bias, macro_score, rrr):
    score  = round(STOCK_WIN_RATE.get(name, 0.55) * 25)
    score += round(SETUP_WIN_RATE.get(setup, 0.55) * 20)
    score += round(TIMEFRAME_QUALITY.get(tf, 0.7) * 10)
    score += min(15, conds * 2)
    score += 15 if htf_bias == "Bullish" else 7 if htf_bias == "Neutral" else 0
    score += round((macro_score / 100) * 10)
    score += min(5, round((rrr - 2) * 2))
    score += {"A":5,"B":3,"C":1,"D":0}.get(STOCK_GRADE.get(name,"C"), 1)
    return min(100, max(0, score))

import yfinance as yf
import pandas as pd

def fetch(ticker, interval, period="90d"):
    if interval == "1wk": period = "2y"
    for t in [ticker, ticker.replace(".NS",".BO")]:
        for _ in range(2):
            try:
                df = yf.download(t, period=period, interval=interval,
                                 progress=False, auto_adjust=True, timeout=15)
                if df is not None and len(df) >= 20:
                    df.columns = [c[0] if isinstance(c,tuple) else c for c in df.columns]
                    df.dropna(inplace=True)
                    if len(df) >= 20: return df
            except: pass
            time.sleep(0.5)
    return None

def get_htf_bias(ticker):
    df = fetch(ticker, "1wk", "2y")
    if df is None or len(df) < 10: return "Neutral"
    c=df["Close"].values; h=df["High"].values; l=df["Low"].values; ma=c[-20:].mean()
    if h[-1]>h[-4] and l[-1]>l[-4] and c[-1]>ma: return "Bullish"
    if h[-1]<h[-4] and l[-1]<l[-4] and c[-1]<ma: return "Bearish"
    return "Neutral"

def calc_atr(df, p=14):
    h,l,c = df["High"],df["Low"],df["Close"]
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return float(tr.rolling(p).mean().iloc[-1])

def swing_pts(df, lb=5):
    h=df["High"].values; l=df["Low"].values; n=len(df); sh,sl=[],[]
    for i in range(lb,n-lb):
        if all(h[i]>=h[i-j] for j in range(1,lb+1)) and all(h[i]>=h[i+j] for j in range(1,lb+1)): sh.append((i,h[i]))
        if all(l[i]<=l[i-j] for j in range(1,lb+1)) and all(l[i]<=l[i+j] for j in range(1,lb+1)): sl.append((i,l[i]))
    return sh,sl

def check_smc(df):
    c=df["Close"].values; h=df["High"].values; l=df["Low"].values; o=df["Open"].values
    conds=[]; setup="OB Retest"; swept=False
    sh,sl=swing_pts(df,lb=3)
    last_sh=sh[-1][1] if sh else h[-10]; last_sl=sl[-1][1] if sl else l[-10]
    if l[-1]<last_sl and c[-1]>last_sl: conds.append("SSL Swept"); swept=True
    elif h[-1]>last_sh and c[-1]<last_sh: conds.append("BSL Swept"); swept=True
    if len(df)>=10:
        psh=max(h[-10:-2]); psl=min(l[-10:-2])
        if c[-1]>psh: conds.append("Bullish MSS"); setup="MSS+OB"
        elif c[-1]<psl: conds.append("Bearish MSS"); setup="MSS+OB"
        elif c[-1]>h[-5] and c[-2]<h[-5]: conds.append("Bullish ChoCH"); setup="ChoCH+FVG"
        elif c[-1]<l[-5] and c[-2]>l[-5]: conds.append("Bearish ChoCH"); setup="ChoCH+FVG"
    if len(df)>=3:
        if l[-1]>h[-3] or h[-1]<l[-3]:
            conds.append("FVG")
            if any(x in str(conds) for x in ["ChoCH","MSS"]): setup="ChoCH+FVG"
    rh=max(h[-20:]); rl=min(l[-20:]); r=rh-rl
    if r>0:
        fib=(rh-c[-1])/r*100
        if 61.8<=fib<=78.6: conds.append(f"OTE {round(fib,1)}%")
    if len(df)>=5:
        for i in range(-5,-1):
            if c[i]<o[i] and c[-1]>h[i]: conds.append("OB"); break
            if c[i]>o[i] and c[-1]<l[i]: conds.append("OB"); break
    if h[-1]-l[-1]>0 and abs(c[-1]-o[-1])/(h[-1]-l[-1])>0.75: conds.append("Displacement")
    if len(df)>=3:
        r2=h[-2]-l[-2]
        if r2>0 and abs(c[-2]-o[-2])/r2<0.35 and (c[-1]>h[-2] or c[-1]<l[-2]):
            conds.append("U-Turn"); setup="U-Turn"
    if h[-1]-l[-1]>0 and abs(c[-1]-o[-1])/(h[-1]-l[-1])>0.85: conds.append("Dominance")
    if swept and "FVG" in conds: setup="Liq.Sweep+FVG"
    return conds, setup

def analyze_one(ticker, tf_label, tf_int):
    df=fetch(ticker,tf_int)
    if df is None or len(df)<25: return None
    c=df["Close"].values; h=df["High"].values; l=df["Low"].values; px=float(c[-1])
    conds,setup=check_smc(df)
    if len(conds)<MIN_CONDITIONS: return None
    bias=get_htf_bias(ticker)
    bull=sum([any("Bull" in x or "SSL" in x for x in conds),bias=="Bullish",c[-1]>c[-5]])
    bear=sum([any("Bear" in x or "BSL" in x for x in conds),bias=="Bearish",c[-1]<c[-5]])
    direction="LONG" if bull>=bear else "SHORT"
    atr_v=calc_atr(df)
    rh=float(max(h[-20:])); rl=float(min(l[-20:]))
    if direction=="LONG":
        sl_p=round(rl-atr_v*0.5,2); rp=round(px-sl_p,2)
        if rp<=0: return None
        t1=round(px+rp,2); t2=round(px+rp*2,2); t3=round(px+rp*3,2)
    else:
        sl_p=round(rh+atr_v*0.5,2); rp=round(sl_p-px,2)
        if rp<=0: return None
        t1=round(px-rp,2); t2=round(px-rp*2,2); t3=round(px-rp*3,2)
    rrr=round(abs(t3-px)/rp,2)
    if rrr<MIN_RRR: return None
    target_risk=round(ACCOUNT_CAPITAL*RISK_PER_TRADE_PCT/100)
    qty=max(1,int(target_risk/rp)) if rp>0 else 1
    risk_inr=round(qty*rp)  # actual risk based on real qty
    name=clean_name(ticker)
    sector=STOCK_SECTOR.get(name,"Other")
    macro_score=SECTOR_BIAS.get(sector,0.6)*100
    confidence=calc_confidence(name,setup,tf_label,len(conds),bias,macro_score,rrr)
    if confidence<MIN_CONFIDENCE: return None
    hist_wr=STOCK_WIN_RATE.get(name,0.55)
    setup_wr=SETUP_WIN_RATE.get(setup,0.55)
    return {
        "name":name,"dir":direction,"tf":tf_label,
        "price":round(px,2),"sl":sl_p,"t1":t1,"t2":t2,"t3":t3,
        "rrr":rrr,"qty":qty,"risk_inr":risk_inr,"profit_t3":round(qty*rp*3),
        "confidence":confidence,"combined_wr":round((hist_wr*0.5+setup_wr*0.5)*100,1),
        "hist_wr":round(hist_wr*100,1),"setup_wr":round(setup_wr*100,1),
        "sector":sector,"grade":STOCK_GRADE.get(name,"C"),
        "cond_count":len(conds),"conds":f"{len(conds)}/9","setup":setup,
        "htf_bias":bias,"macro_score":round(macro_score),
        "conditions":conds[:6],
    }

def run():
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    print(f"AlphaSMC Scan | {now} | {len(WATCHLIST)} stocks")

    candidates=[]; seen=set(); scanned=0
    for ticker in WATCHLIST:
        for tf_label,tf_int in [("Daily","1d"),("4H","4h"),("Weekly","1wk")]:
            try:
                sig=analyze_one(ticker,tf_label,tf_int)
                if sig:
                    key=f"{sig['name']}_{sig['dir']}"
                    if key not in seen:
                        candidates.append(sig); seen.add(key)
                        print(f"  ✓ {sig['name']:12} {tf_label:6} {sig['dir']} Conf:{sig['confidence']} Grade:{sig['grade']}")
            except Exception as e:
                pass
        scanned+=1
        if scanned%20==0:
            print(f"  ... {scanned}/{len(WATCHLIST)} scanned, {len(candidates)} qualified")

    print(f"\nDone: {len(candidates)} candidates from {scanned} stocks")

    if not candidates:
        # Write empty signals.json so dashboard knows scan ran
        out = {"scanTime":now,"scanned":scanned,"qualified":0,"candidates":[],"best":None}
        with open("signals.json","w") as f: json.dump(out,f,indent=2)
        print("No trades today. signals.json written.")
        return

    # Sort by confidence score
    candidates.sort(key=lambda x: (
        x["confidence"]*0.4 + x["combined_wr"]*0.3 + x["macro_score"]*0.15 +
        x["cond_count"]*2 + x["rrr"]*1.5 + {"A":5,"B":3,"C":1,"D":0}.get(x["grade"],1)
    ), reverse=True)

    best = candidates[0]
    print(f"\n⭐ BEST: {best['name']} {best['dir']} | Conf:{best['confidence']} | WR:{best['combined_wr']}%")

    # Write signals.json — dashboard reads this
    out = {
        "scanTime": now,
        "scanned":  scanned,
        "qualified": len(candidates),
        "best": best,
        "candidates": candidates[:20],  # top 20 for dashboard
    }
    with open("signals.json","w") as f:
        json.dump(out, f, indent=2)
    print(f"✓ signals.json written with {len(candidates)} candidates")

    # Send ONE email with best trade
    if EMAIL_PASS:
        send_email(best, candidates[1:6], scanned, now)

def send_email(best, runners, scanned, now):
    dc  = "#00f0a8" if best["dir"]=="LONG" else "#ff3356"
    da  = "▲" if best["dir"]=="LONG" else "▼"
    dbg = "rgba(0,240,168,0.12)" if best["dir"]=="LONG" else "rgba(255,51,86,0.12)"
    cc  = "#00f0a8" if best["confidence"]>=80 else "#ffb700" if best["confidence"]>=65 else "#ff3356"
    gc  = {"A":"#00f0a8","B":"#22d3ee","C":"#ffb700"}.get(best["grade"],"#ffb700")

    cond_tags = "".join([
        f'<span style="background:rgba(0,240,168,.1);color:#00f0a8;border:1px solid rgba(0,240,168,.25);padding:3px 9px;border-radius:4px;font-size:11px;margin:2px;display:inline-block;font-family:Courier New,monospace">{c}</span>'
        for c in best["conditions"]
    ])
    runner_rows = "".join([
        f'<tr style="border-bottom:1px solid rgba(255,255,255,.05)"><td style="padding:7px 12px;color:#4e5a72">#{i+2}</td>'
        f'<td style="padding:7px 12px;font-weight:800;color:{"#00f0a8" if r["dir"]=="LONG" else "#ff3356"}">{r["name"]}</td>'
        f'<td style="padding:7px 12px;color:#8892aa">{r["dir"]}</td>'
        f'<td style="padding:7px 12px;color:#8892aa">{r["tf"]}</td>'
        f'<td style="padding:7px 12px;font-weight:700;color:{cc};font-family:Courier New,monospace">{r["confidence"]}/100</td>'
        f'<td style="padding:7px 12px;color:#00f0a8;font-family:Courier New,monospace">{r["combined_wr"]}%</td></tr>'
        for i,r in enumerate(runners[:5])
    ])

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#060810;font-family:'Segoe UI',Arial,sans-serif">
<div style="max-width:620px;margin:0 auto;padding:20px">
  <div style="background:linear-gradient(135deg,#0a0d18,#151b2e);border:1px solid rgba(0,240,168,.2);border-radius:14px;padding:22px 26px;margin-bottom:14px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
      <div style="font-size:24px;font-weight:900;letter-spacing:3px;color:#00f0a8;font-family:'Courier New',monospace">AlphaSMC</div>
      <div style="font-size:11px;color:#4e5a72;font-family:'Courier New',monospace">{now}</div>
    </div>
    <div style="font-size:10px;color:#4e5a72;letter-spacing:2px;text-transform:uppercase;margin-bottom:14px">FULL NSE SCAN · ONE BEST TRADE</div>
    <div style="display:flex;gap:10px">
      <div style="background:rgba(255,255,255,.04);border-radius:8px;padding:8px 14px;text-align:center;flex:1">
        <div style="font-size:22px;font-weight:800;color:#22d3ee;font-family:'Courier New',monospace">{scanned}</div>
        <div style="font-size:9px;color:#4e5a72;text-transform:uppercase;margin-top:2px">Scanned</div>
      </div>
      <div style="background:rgba(255,255,255,.04);border-radius:8px;padding:8px 14px;text-align:center;flex:1">
        <div style="font-size:22px;font-weight:800;color:#ffb700;font-family:'Courier New',monospace">{len(runners)+1}</div>
        <div style="font-size:9px;color:#4e5a72;text-transform:uppercase;margin-top:2px">Qualified</div>
      </div>
      <div style="background:rgba(0,240,168,.08);border:1px solid rgba(0,240,168,.25);border-radius:8px;padding:8px 14px;text-align:center;flex:1">
        <div style="font-size:22px;font-weight:800;color:#00f0a8;font-family:'Courier New',monospace">1</div>
        <div style="font-size:9px;color:#4e5a72;text-transform:uppercase;margin-top:2px">Selected</div>
      </div>
    </div>
  </div>
  <div style="background:linear-gradient(135deg,rgba(0,240,168,.06),#0a0d18);border:1.5px solid rgba(0,240,168,.35);border-radius:14px;padding:24px 26px;margin-bottom:14px;position:relative;overflow:hidden">
    <div style="height:2px;background:linear-gradient(90deg,#00f0a8,#22d3ee);position:absolute;top:0;left:0;right:0"></div>
    <div style="background:#00f0a8;color:#000;font-size:10px;font-weight:800;padding:3px 12px;border-radius:10px;letter-spacing:1px;text-transform:uppercase;display:inline-flex;margin-bottom:16px">⭐ TODAY'S BEST TRADE</div>
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px">
      <div>
        <div style="font-size:46px;font-weight:900;color:{dc};font-family:'Courier New',monospace;letter-spacing:2px;line-height:1">{best['name']}</div>
        <div style="font-size:12px;color:#8892aa;margin-top:5px;font-family:'Courier New',monospace">{best['sector']} · {best['setup']} · {best['tf']}</div>
        <div style="display:flex;gap:6px;margin-top:10px">
          <span style="background:{dbg};color:{dc};border:1px solid {dc};padding:3px 10px;border-radius:5px;font-size:11px;font-weight:800;font-family:'Courier New',monospace">{da} {best['dir']}</span>
          <span style="background:rgba(255,255,255,.05);color:#8892aa;padding:3px 10px;border-radius:5px;font-size:11px;font-family:'Courier New',monospace">HTF {best['htf_bias']}</span>
          <span style="background:rgba(255,255,255,.05);color:{gc};padding:3px 10px;border-radius:5px;font-size:11px;font-weight:700;font-family:'Courier New',monospace">Grade {best['grade']}</span>
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-size:56px;font-weight:900;font-family:'Courier New',monospace;color:{cc};line-height:1">{best['confidence']}</div>
        <div style="font-size:10px;color:#4e5a72;letter-spacing:1px;text-transform:uppercase">/100 Confidence</div>
        <div style="background:rgba(255,255,255,.08);border-radius:3px;height:5px;width:100px;margin:6px 0 0 auto">
          <div style="height:100%;width:{best['confidence']}%;background:{cc};border-radius:3px"></div>
        </div>
      </div>
    </div>
    <div style="margin-bottom:16px">
      <div style="font-size:10px;color:#4e5a72;letter-spacing:1px;text-transform:uppercase;margin-bottom:7px">SMC Conditions ({best['cond_count']}/9)</div>
      <div>{cond_tags}</div>
    </div>
    <div style="background:rgba(0,0,0,.35);border-radius:10px;padding:18px;border:1px solid rgba(255,255,255,.06)">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
        <div><div style="font-size:10px;color:#4e5a72;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Entry</div>
        <div style="font-size:19px;font-weight:800;font-family:'Courier New',monospace;color:{dc}">₹{best['price']:,.2f}</div></div>
        <div><div style="font-size:10px;color:#4e5a72;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Stop Loss</div>
        <div style="font-size:19px;font-weight:800;font-family:'Courier New',monospace;color:#ff3356">₹{best['sl']:,.2f}</div></div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px">
        <div style="background:rgba(255,183,0,.06);border-radius:7px;padding:10px;text-align:center;border:1px solid rgba(255,183,0,.15)">
          <div style="font-size:10px;color:#4e5a72;margin-bottom:3px">Target 1</div>
          <div style="font-size:16px;font-weight:800;font-family:'Courier New',monospace;color:#ffb700">₹{best['t1']:,.2f}</div>
        </div>
        <div style="background:rgba(255,183,0,.08);border-radius:7px;padding:10px;text-align:center;border:1px solid rgba(255,183,0,.2)">
          <div style="font-size:10px;color:#4e5a72;margin-bottom:3px">Target 2</div>
          <div style="font-size:16px;font-weight:800;font-family:'Courier New',monospace;color:#ffb700">₹{best['t2']:,.2f}</div>
        </div>
        <div style="background:rgba(0,240,168,.08);border-radius:7px;padding:10px;text-align:center;border:1px solid rgba(0,240,168,.2)">
          <div style="font-size:10px;color:#4e5a72;margin-bottom:3px">Target 3</div>
          <div style="font-size:16px;font-weight:800;font-family:'Courier New',monospace;color:#00f0a8">₹{best['t3']:,.2f}</div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
        <div style="text-align:center"><div style="font-size:10px;color:#4e5a72;margin-bottom:3px">RRR</div><div style="font-size:15px;font-weight:800;font-family:'Courier New',monospace;color:#22d3ee">1:{best['rrr']}</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:#4e5a72;margin-bottom:3px">Qty</div><div style="font-size:15px;font-weight:800;font-family:'Courier New',monospace;color:#dde3f5">{best['qty']} shares</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:#4e5a72;margin-bottom:3px">Risk</div><div style="font-size:15px;font-weight:800;font-family:'Courier New',monospace;color:#ff3356">₹{best['risk_inr']}</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:#4e5a72;margin-bottom:3px">Max Profit</div><div style="font-size:15px;font-weight:800;font-family:'Courier New',monospace;color:#00f0a8">₹{best['profit_t3']:,}</div></div>
      </div>
    </div>
  </div>
  <div style="background:#0a0d18;border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:20px 22px;margin-bottom:14px">
    <div style="font-size:10px;color:#4e5a72;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px">TOP 5 RUNNERS-UP</div>
    <table style="width:100%;border-collapse:collapse">
      <tr style="background:rgba(255,255,255,.03)">
        <th style="padding:6px 12px;font-size:9px;color:#4e5a72;text-align:left">#</th>
        <th style="padding:6px 12px;font-size:9px;color:#4e5a72;text-align:left">Stock</th>
        <th style="padding:6px 12px;font-size:9px;color:#4e5a72;text-align:left">Dir</th>
        <th style="padding:6px 12px;font-size:9px;color:#4e5a72;text-align:left">TF</th>
        <th style="padding:6px 12px;font-size:9px;color:#4e5a72;text-align:left">Conf</th>
        <th style="padding:6px 12px;font-size:9px;color:#4e5a72;text-align:left">WR</th>
      </tr>
      {runner_rows}
    </table>
  </div>
  <div style="background:#0a0d18;border:1px solid rgba(255,255,255,.05);border-radius:10px;padding:14px 20px;text-align:center">
    <div style="font-size:11px;color:#4e5a72;font-family:'Courier New',monospace;line-height:2">
      ⚠ Not financial advice · Trade at your own risk<br>
      AlphaSMC · alphaluxes.in/dashboard
    </div>
  </div>
</div></body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[AlphaSMC] {best['dir']} {best['name']} · Conf {best['confidence']}/100 · {datetime.now(IST).strftime('%d %b %I:%M %p')}"
    msg["From"]    = f"AlphaSMC <{EMAIL_FROM}>"
    msg["To"]      = EMAIL_TO
    plain = f"[{best['dir']}] {best['name']} | Conf:{best['confidence']}/100 | Entry:Rs.{best['price']} | SL:Rs.{best['sl']} | T3:Rs.{best['t3']} | RRR:1:{best['rrr']}"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(EMAIL_FROM, EMAIL_PASS)
            srv.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"✓ Email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"Email failed: {e}")

if __name__ == "__main__":
    run()
