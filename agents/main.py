"""
SnipBot — Hybrid AI Agents Engine v12.3 FINAL
8 Real AI Agents + Weighted Consensus + KuCoin->Binance failover
"""

import os, logging, time, threading, requests
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import ta.momentum, ta.trend, ta.volatility

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
log = logging.getLogger("SnipBot.Agents")

PORT       = int(os.environ.get("PORT", 8080))
PROXY_URL  = os.environ.get("PROXY_URL", "https://snipbot-proxy.up.railway.app")
PAIRS      = [p.strip() for p in os.environ.get("PAIRS","ADA/USDT,XRP/USDT,BTC/USDT,ETH/USDT").split(",")]
INTERVAL   = int(os.environ.get("SCAN_INTERVAL", "300"))
TF         = os.environ.get("TIMEFRAME", "1h")
MIN_SIGNAL = float(os.environ.get("MIN_SIGNAL", "75"))
MIN_CONF   = float(os.environ.get("MIN_CONFIDENCE", "80"))

app = Flask(__name__)
CORS(app)

_latest_evaluations = {}
_scan_count = 0
_last_scan_time = None

AGENTS_REGISTRY = {
    "smart_dca":         {"name":"Smart DCA Agent",           "type":"Accumulation & Support Sniper", "weight":1.2,"enabled":True},
    "momentum_breakout": {"name":"Technical Momentum Agent",  "type":"Breakout & Divergence Engine",  "weight":1.3,"enabled":True},
    "trend_follower":    {"name":"Trend Follower Agent",      "type":"EMA Trend & Trailing",          "weight":1.1,"enabled":True},
    "grid_sniper":       {"name":"Grid Sniper Agent",         "type":"Volatility Range Grid",         "weight":1.0,"enabled":True},
    "liquidity_sweep":   {"name":"Liquidity Sweep Agent",     "type":"Orderbook & Wick Sniper",       "weight":1.4,"enabled":True},
    "micro_scalper":     {"name":"Micro-Scalper Agent",       "type":"High-Frequency Spread",         "weight":0.9,"enabled":True},
    "sentiment_ai":      {"name":"Sentiment AI Agent",        "type":"Fear & Greed + Momentum",       "weight":1.1,"enabled":True},
    "risk_governor":     {"name":"Risk & Portfolio Governor", "type":"Master Safety Engine",          "weight":1.5,"enabled":True},
}

def analyze_smart_dca(df):
    try:
        c=df["close"]; p=c.iloc[-1]
        ma=ta.trend.SMAIndicator(c,window=min(50,len(c)-1)).sma_indicator().iloc[-1]
        rsi=ta.momentum.RSIIndicator(c,window=14).rsi().iloc[-1]
        ema200=ta.trend.EMAIndicator(c,window=min(200,max(1,len(c)//2))).ema_indicator().iloc[-1]
        pct=(p-ma)/ma*100; up=p>ema200
        if pct<=-4 and rsi>25 and up:
            return {"signal":min(70+abs(pct)*5,95),"confidence":min(75+abs(pct)*3,90),"reason":f"DCA dip {pct:.1f}% below MA50 · RSI={rsi:.0f}"}
        elif pct>=3:
            return {"signal":max(30-pct*5,5),"confidence":75,"reason":f"DCA recovery {pct:.1f}% above MA50"}
        return {"signal":50,"confidence":60,"reason":f"DCA standby {pct:+.1f}% vs MA50 · RSI={rsi:.0f}"}
    except Exception as e:
        return {"signal":50,"confidence":50,"reason":f"Error:{e}"}

def analyze_momentum_breakout(df):
    try:
        c=df["close"]; rsi_v=ta.momentum.RSIIndicator(c,window=14).rsi().iloc[-1]
        mo=ta.trend.MACD(c,window_fast=12,window_slow=26,window_sign=9)
        m=mo.macd(); ms=mo.macd_signal()
        e20=ta.trend.EMAIndicator(c,window=20).ema_indicator()
        e50=ta.trend.EMAIndicator(c,window=min(50,len(c)-1)).ema_indicator()
        mb=m.iloc[-1]>ms.iloc[-1]; mc=mb and m.iloc[-2]<=ms.iloc[-2]
        eb=e20.iloc[-1]>e50.iloc[-1]; rb=45<rsi_v<65
        sc=sum([mb,mc,eb,rb])
        if sc>=3:
            return {"signal":min(75+sc*5+(10 if mc else 0),95),"confidence":min(80+(10 if mc else 0),95),"reason":f"Bullish · RSI={rsi_v:.0f} · MACD={'CROSS ▲' if mc else 'BULL'}"}
        elif sc<=1:
            return {"signal":max(30-(2-sc)*10,5),"confidence":70,"reason":f"Weak · RSI={rsi_v:.0f} · score={sc}/4"}
        return {"signal":50,"confidence":60,"reason":f"Neutral · RSI={rsi_v:.0f} · score={sc}/4"}
    except Exception as e:
        return {"signal":50,"confidence":50,"reason":f"Error:{e}"}

def analyze_trend_follower(df):
    try:
        c=df["close"]; h=df["high"]; l=df["low"]
        e20=ta.trend.EMAIndicator(c,window=20).ema_indicator()
        e50=ta.trend.EMAIndicator(c,window=min(50,len(c)-1)).ema_indicator()
        adx=ta.trend.ADXIndicator(h,l,c,window=14).adx().iloc[-1]
        gold=e20.iloc[-1]>e50.iloc[-1] and e20.iloc[-2]<=e50.iloc[-2]
        dead=e20.iloc[-1]<e50.iloc[-1] and e20.iloc[-2]>=e50.iloc[-2]
        up=e20.iloc[-1]>e50.iloc[-1]; strong=adx>25
        if up and strong:
            return {"signal":80+(10 if gold else 0),"confidence":82+(8 if strong else 0),"reason":f"{'Golden Cross ▲' if gold else 'Uptrend'} · ADX={adx:.0f}"}
        elif not up and strong:
            return {"signal":20-(10 if dead else 0),"confidence":80,"reason":f"{'Death Cross ▼' if dead else 'Downtrend'} · ADX={adx:.0f}"}
        return {"signal":50,"confidence":55,"reason":f"Sideways · ADX={adx:.0f}"}
    except Exception as e:
        return {"signal":50,"confidence":50,"reason":f"Error:{e}"}

def analyze_grid_sniper(df):
    try:
        c=df["close"]; p=c.iloc[-1]
        bb=ta.volatility.BollingerBands(c,window=20,window_dev=2)
        u=bb.bollinger_hband().iloc[-1]; lo=bb.bollinger_lband().iloc[-1]; mid=bb.bollinger_mavg().iloc[-1]
        w=(u-lo)/mid*100 if mid>0 else 0; pct=(p-lo)/(u-lo) if (u-lo)>0 else 0.5
        if w<3: return {"signal":70,"confidence":75,"reason":f"BB Squeeze · Width={w:.1f}%"}
        elif pct<0.2: return {"signal":75,"confidence":78,"reason":f"Near BB lower · {pct*100:.0f}%"}
        elif pct>0.8: return {"signal":30,"confidence":73,"reason":f"Near BB upper · {pct*100:.0f}%"}
        return {"signal":50,"confidence":60,"reason":f"Mid-band · {pct*100:.0f}% · W={w:.1f}%"}
    except Exception as e:
        return {"signal":50,"confidence":50,"reason":f"Error:{e}"}

def analyze_liquidity_sweep(df):
    try:
        l=df.iloc[-1]; wl=l["open"]-l["low"]; sz=l["high"]-l["low"]
        r=wl/sz if sz>0 else 0; bull=r>0.6 and l["close"]>l["open"]
        av=df["volume"].iloc[-10:-1].mean() if len(df)>10 else df["volume"].mean()
        sp=l["volume"]>av*1.5
        if bull and sp: return {"signal":88,"confidence":85,"reason":f"Bullish sweep · Ratio={r:.0%} · Vol spike"}
        elif bull: return {"signal":75,"confidence":75,"reason":f"Wick sweep · Ratio={r:.0%}"}
        elif r<0.2 and l["close"]<l["open"]: return {"signal":35,"confidence":68,"reason":"Bearish · No sweep"}
        return {"signal":52,"confidence":58,"reason":f"No sweep · Ratio={r:.0%}"}
    except Exception as e:
        return {"signal":50,"confidence":50,"reason":f"Error:{e}"}

def analyze_micro_scalper(df):
    try:
        c=df["close"]
        r3=ta.momentum.RSIIndicator(c,window=3).rsi().iloc[-1]
        r14=ta.momentum.RSIIndicator(c,window=14).rsi().iloc[-1]
        n=min(5,len(c)-1); m5=(c.iloc[-1]-c.iloc[-n])/c.iloc[-n]*100
        if r3<30 and m5<-1: return {"signal":78,"confidence":72,"reason":f"Micro oversold · RSI3={r3:.0f} · mom={m5:.2f}%"}
        elif r3>70 and m5>1: return {"signal":28,"confidence":70,"reason":f"Micro overbought · RSI3={r3:.0f} · mom={m5:.2f}%"}
        return {"signal":50,"confidence":55,"reason":f"Scalp standby · RSI3={r3:.0f} · RSI14={r14:.0f}"}
    except Exception as e:
        return {"signal":50,"confidence":50,"reason":f"Error:{e}"}

def analyze_sentiment_ai(df):
    try:
        c=df["close"]; v=df["volume"]; lb=min(24,len(c)-1)
        tr=(c.iloc[-1]-c.iloc[-lb])/c.iloc[-lb]*100
        rv=v.iloc[-5:].mean() if len(v)>=5 else v.mean()
        ov=v.iloc[-min(20,len(v)):-5].mean() if len(v)>=20 else v.mean()
        vt=(rv-ov)/ov*100 if ov>0 else 0
        rsi=ta.momentum.RSIIndicator(c,window=14).rsi().iloc[-1]
        if tr>2 and vt>10: return {"signal":85,"confidence":80,"reason":f"Bullish · 24h={tr:+.1f}% · Vol={vt:+.0f}%"}
        elif tr>0 and rsi>50: return {"signal":65,"confidence":70,"reason":f"Mildly bullish · 24h={tr:+.1f}% · RSI={rsi:.0f}"}
        elif tr<-2: return {"signal":30,"confidence":72,"reason":f"Bearish · 24h={tr:+.1f}%"}
        return {"signal":50,"confidence":58,"reason":f"Neutral · 24h={tr:+.1f}%"}
    except Exception as e:
        return {"signal":50,"confidence":50,"reason":f"Error:{e}"}

def analyze_risk_governor(df):
    try:
        c=df["close"]; h=df["high"]; l=df["low"]; p=c.iloc[-1]
        atr=ta.volatility.AverageTrueRange(h,l,c,window=14).average_true_range().iloc[-1]
        ap=atr/p*100 if p>0 else 0
        h20=h.iloc[-min(20,len(h)):].max(); dd=(p-h20)/h20*100 if h20>0 else 0
        if dd<-8: return {"signal":20,"confidence":90,"reason":f"RISK ALERT: DD={dd:.1f}% · ATR={ap:.1f}%"}
        elif dd<-5: return {"signal":40,"confidence":85,"reason":f"Moderate risk: DD={dd:.1f}% · ATR={ap:.1f}%"}
        elif ap>5: return {"signal":45,"confidence":80,"reason":f"High volatility: ATR={ap:.1f}%"}
        return {"signal":85,"confidence":88,"reason":f"Portfolio safe: DD={dd:.1f}% · ATR={ap:.1f}%"}
    except Exception as e:
        return {"signal":50,"confidence":50,"reason":f"Error:{e}"}

AGENT_FUNCTIONS = {
    "smart_dca":analyze_smart_dca,"momentum_breakout":analyze_momentum_breakout,
    "trend_follower":analyze_trend_follower,"grid_sniper":analyze_grid_sniper,
    "liquidity_sweep":analyze_liquidity_sweep,"micro_scalper":analyze_micro_scalper,
    "sentiment_ai":analyze_sentiment_ai,"risk_governor":analyze_risk_governor,
}

def run_consensus(pair, df):
    results={}; tw=ws=wc=0.0
    for aid,cfg in AGENTS_REGISTRY.items():
        if not cfg["enabled"]: continue
        fn=AGENT_FUNCTIONS.get(aid)
        r=fn(df) if fn else {"signal":50,"confidence":50,"reason":"No fn"}
        w=cfg["weight"]
        results[aid]={"id":aid,"name":cfg["name"],"type":cfg["type"],"weight":w,
                      "signal":r["signal"],"confidence":r["confidence"],"reason":r["reason"],
                      "status":"TRIGGERED" if r["signal"]>=MIN_SIGNAL else "SCANNING"}
        ws+=r["signal"]*w; wc+=r["confidence"]*w; tw+=w
    ns=round(ws/tw,2) if tw>0 else 50
    nc=round(wc/tw,2) if tw>0 else 50
    if ns>=MIN_SIGNAL and nc>=MIN_CONF: action="FIRE_BUY"
    elif ns<=(100-MIN_SIGNAL) and nc>=MIN_CONF: action="FIRE_SELL"
    else: action="HOLD_AND_SCAN"
    return {"pair":pair,"timestamp":datetime.now(timezone.utc).isoformat(),
            "consensus":{"action":action,"net_signal":ns,"net_confidence":nc,
                         "threshold_signal":MIN_SIGNAL,"threshold_conf":MIN_CONF},"agents":results}

def fetch_ohlcv_sync(pair, timeframe="1h", limit=200):
    import ccxt
    for eid in ["kucoin","binance"]:
        try:
            ex=getattr(ccxt,eid)({"enableRateLimit":True,"options":{"defaultType":"spot"}})
            raw=ex.fetch_ohlcv(pair,timeframe,limit=limit)
            if raw and len(raw)>=15:
                df=pd.DataFrame(raw,columns=["timestamp","open","high","low","close","volume"])
                df["timestamp"]=pd.to_datetime(df["timestamp"],unit="ms")
                df.set_index("timestamp",inplace=True)
                log.info(f"[OHLCV] {pair} from {eid} ({len(df)} candles)")
                return df.astype(float)
        except Exception as e:
            log.warning(f"[OHLCV] {eid} failed for {pair}: {e}")
    return None

def push_to_proxy(data):
    try:
        r=requests.post(f"{PROXY_URL}/api/agents/update",json=data,timeout=5)
        log.info(f"🔎 [Proxy]: Agent Radar updated → {r.status_code}")
    except Exception as e:
        log.warning(f"[Proxy]: push failed — {e}")

def scan_loop():
    global _scan_count,_last_scan_time,_latest_evaluations
    time.sleep(5)
    while True:
        _scan_count+=1; _last_scan_time=datetime.now(timezone.utc).isoformat()
        log.info(f"🔎 [Sniper Engine]: Scan #{_scan_count} on {PAIRS}...")
        proxy_agents=[]; active_sigs=[]
        for pair in PAIRS:
            df=fetch_ohlcv_sync(pair,TF)
            if df is None: log.warning(f"◎ No data for {pair}"); continue
            result=run_consensus(pair,df); _latest_evaluations[pair]=result
            action=result["consensus"]["action"]
            ns=result["consensus"]["net_signal"]; nc=result["consensus"]["net_confidence"]
            for aid,ag in result["agents"].items():
                proxy_agents.append({"name":ag["name"],"pair":pair,"strategy":ag["name"],
                    "action":"BUY" if ag["signal"]>=MIN_SIGNAL else ("SELL" if ag["signal"]<=(100-MIN_SIGNAL) else "HOLD"),
                    "confidence":ag["confidence"],"reason":ag["reason"]})
            if action=="FIRE_BUY":
                active_sigs.append({"pair":pair,"action":"BUY","confidence":nc})
                log.info(f"🎯 {pair} → FIRE_BUY · ns={ns} nc={nc}")
            elif action=="FIRE_SELL":
                active_sigs.append({"pair":pair,"action":"SELL","confidence":nc})
                log.info(f"⚡ {pair} → FIRE_SELL · ns={ns} nc={nc}")
            else:
                log.info(f"◎ {pair} → HOLD · ns={ns:.1f}")
        push_to_proxy({"timestamp":_last_scan_time,"scan_count":_scan_count,
                       "strategies":proxy_agents,"signals":active_sigs,"symbols":PAIRS})
        log.info(f"◎ Sleeping {INTERVAL}s..."); time.sleep(INTERVAL)

@app.route("/")
@app.route("/health")
def health():
    return jsonify({"status":"ONLINE","service":"snipbot-agents-v12.3",
                    "agents":len(AGENTS_REGISTRY),"pairs":PAIRS,
                    "scan_count":_scan_count,"last_scan":_last_scan_time}),200

@app.route("/api/agents/status")
def agents_status():
    latest={}
    if _latest_evaluations:
        latest=list(_latest_evaluations.values())[0].get("agents",{})
    enriched=[]
    for aid,cfg in AGENTS_REGISTRY.items():
        ev=latest.get(aid,{}); sig=ev.get("signal",50); conf=ev.get("confidence",75)
        act="BUY" if sig>=MIN_SIGNAL else ("SELL" if sig<=(100-MIN_SIGNAL) else "HOLD")
        enriched.append({"id":aid,"name":cfg["name"],"type":cfg["type"],"weight":cfg["weight"],
                         "enabled":cfg["enabled"],"status":act,"action":act,"signal":sig,
                         "confidence":conf,"reason":ev.get("reason","Active scanning")})
    return jsonify({"status":"success","total_agents":len(enriched),"agents":enriched,
                    "scan_count":_scan_count,"last_scan":_last_scan_time,
                    "pairs":list(_latest_evaluations.keys())}),200

@app.route("/api/agents/evaluate")
def evaluate_pair():
    pair=request.args.get("pair",PAIRS[0] if PAIRS else "ADA/USDT")
    tf=request.args.get("timeframe",TF)
    if pair in _latest_evaluations:
        cached=_latest_evaluations[pair]; ts=cached.get("timestamp","")
        if ts:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(ts)).total_seconds()
            if age<300: return jsonify({"status":"success","source":"cache",**cached}),200
    df=fetch_ohlcv_sync(pair,tf)
    if df is None:
        if _latest_evaluations:
            fb=list(_latest_evaluations.values())[0]
            return jsonify({"status":"success","source":"fallback",**fb}),200
        return jsonify({"status":"error","error":f"No data for {pair}"}),503
    result=run_consensus(pair,df); _latest_evaluations[pair]=result
    return jsonify({"status":"success","source":"live",**result}),200

@app.route("/api/agents/config",methods=["GET","POST"])
def agents_config():
    if request.method=="GET":
        return jsonify({"status":"success","config":{
            aid:{"name":cfg["name"],"weight":cfg["weight"],"enabled":cfg["enabled"]}
            for aid,cfg in AGENTS_REGISTRY.items()}}),200
    body=request.get_json(silent=True) or {}
    for aid,upd in body.items():
        if aid in AGENTS_REGISTRY:
            if "weight"  in upd: AGENTS_REGISTRY[aid]["weight"]=float(upd["weight"])
            if "enabled" in upd: AGENTS_REGISTRY[aid]["enabled"]=bool(upd["enabled"])
    return jsonify({"status":"updated"}),200

@app.route("/api/agents/pairs")
def latest_by_pair():
    return jsonify({"status":"success","evaluations":_latest_evaluations}),200

if __name__=="__main__":
    log.info(f"🎯 [SnipBot Agents v12.3]: {len(AGENTS_REGISTRY)} agents · {PAIRS}")
    threading.Thread(target=scan_loop,daemon=True).start()
    log.info(f"🔎 Scan loop started · interval={INTERVAL}s · port={PORT}")
    app.run(host="0.0.0.0",port=PORT,debug=False,use_reloader=False)
