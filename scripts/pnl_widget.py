"""Floating desktop P&L widget — Apple-Stocks-style card (pywebview).

A small, frameless, always-on-top card showing live total P&L and a gradient
line chart. Reads the log written by the daemon (`run_options_daemon.py`).

    uv run scripts/pnl_widget.py      # drag anywhere; ⌘Q or close to quit
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

import webview

from config.settings import STATE_DIR

LOG = STATE_DIR / "pnl_log.jsonl"
POSITION = STATE_DIR / "options_paper.json"


def read_data(limit: int = 300) -> dict:
    if not LOG.exists():
        return {"empty": True}
    lines = [l for l in LOG.read_text().splitlines() if l.strip()]
    if not lines:
        return {"empty": True}
    recs = [json.loads(l) for l in lines[-limit:]]
    last = recs[-1]
    pos = None
    if POSITION.exists():
        pos = json.loads(POSITION.read_text()).get("position")
    maxp = round(pos["premium"] * 75) if pos else 0
    total = last["total"]
    return {
        "empty": False,
        "total": total,
        "realized": last["realized"],
        "maxp": maxp,
        "pct": round(total / maxp * 100, 1) if maxp else 0.0,
        "market_open": bool(last.get("market_open")),
        "note": last.get("note", ""),
        "series": [r["total"] for r in recs],
        "ce": pos["ce_strike"] if pos else None,
        "pe": pos["pe_strike"] if pos else None,
        "expiry": pos["expiry"] if pos else None,
    }


HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;background:transparent;overflow:hidden;
    font-family:-apple-system,"SF Pro Display","Helvetica Neue",sans-serif;-webkit-user-select:none;cursor:default}
  .card{position:fixed;inset:8px;border-radius:24px;background:#0a0a0c;
    border:1px solid rgba(255,255,255,.07);box-shadow:0 18px 50px rgba(0,0,0,.55);
    padding:18px 22px 8px;display:flex;flex-direction:column;color:#fff}
  .top{display:flex;justify-content:space-between;align-items:flex-start}
  .left{display:flex;align-items:center;gap:13px}
  .badge{width:44px;height:44px;border-radius:12px;display:grid;place-items:center;
    background:linear-gradient(150deg,#2c2c2e,#1c1c1e);font-size:20px;font-weight:800;
    color:#0a84ff;border:1px solid rgba(255,255,255,.08)}
  .tk{font-size:15px;color:#8a8a8e;font-weight:600;letter-spacing:.02em}
  .nm{font-size:20px;font-weight:750;letter-spacing:-.01em;margin-top:1px}
  .right{text-align:right}
  .price{font-size:26px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
  .chg{font-size:15px;font-weight:700;margin-top:2px;font-variant-numeric:tabular-nums}
  .up{color:#30d158}.down{color:#ff453a}
  .chart{flex:1;position:relative;margin-top:6px;min-height:82px}
  svg{width:100%;height:100%;display:block}
  .foot{font-size:11px;color:#6a6a6e;display:flex;justify-content:space-between;padding:4px 1px 2px}
  .tip{position:absolute;transform:translate(-50%,-150%);background:#2c2c2e;color:#fff;
    font-size:12px;font-weight:700;padding:4px 9px;border-radius:8px;pointer-events:none;
    opacity:0;transition:opacity .08s;white-space:nowrap;font-variant-numeric:tabular-nums}
  .dot{position:absolute}
</style></head><body>
<div class="card">
  <div class="top">
    <div class="left">
      <div class="badge">N</div>
      <div><div class="tk" id="tk">NIFTY</div><div class="nm" id="nm">Short Strangle</div></div>
    </div>
    <div class="right"><div class="price" id="price">₹0</div><div class="chg up" id="chg">+0%</div></div>
  </div>
  <div class="chart" id="chart"><div class="tip" id="tip"></div></div>
  <div class="foot"><span id="f1">paper · waiting for daemon</span><span id="f2"></span></div>
</div>
<script>
let SERIES=[], MAXP=0;
const el=id=>document.getElementById(id);
const rup=n=>(n<0?"−":"")+"₹"+Math.abs(Math.round(n)).toLocaleString("en-IN");

window.render=function(d){
  if(d.empty){el("f1").textContent="no data — start the daemon";return;}
  SERIES=d.series; MAXP=d.maxp;
  const up=d.total>=0;
  el("price").textContent=(up?"+":"−")+"₹"+Math.abs(Math.round(d.total)).toLocaleString("en-IN");
  const chg=el("chg"); chg.textContent=(d.pct>=0?"+":"−")+Math.abs(d.pct).toFixed(1)+"%";
  chg.className="chg "+(up?"up":"down");
  el("nm").textContent = d.ce ? "Short Strangle" : "Flat";
  el("f1").textContent = (d.market_open?"🟢 live":"🔴 market closed")+" · "+(d.note||"");
  el("f2").textContent = d.ce ? (d.ce+"CE / "+d.pe+"PE · exp "+d.expiry) : ("realized "+rup(d.realized));
  draw();
};

function draw(){
  const box=el("chart"), W=box.clientWidth, H=box.clientHeight;
  if(!W||SERIES.length<2){return;}
  const up=SERIES[SERIES.length-1]>=0, col=up?"#30d158":"#ff453a";
  const lo=Math.min(0,...SERIES), hi=Math.max(0,...SERIES), pad=(hi-lo)*.14||1;
  const y0=lo-pad,y1=hi+pad;
  const X=i=>i/(SERIES.length-1)*W, Y=v=>H-(v-y0)/(y1-y0)*H;
  const pts=SERIES.map((v,i)=>X(i).toFixed(1)+","+Y(v).toFixed(1)).join(" ");
  const area=`0,${H} `+pts+` ${W},${H}`;
  const zeroY=Y(0).toFixed(1);
  const svg=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${col}" stop-opacity="0.30"/>
      <stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <polygon points="${area}" fill="url(#g)"/>
    <line x1="0" y1="${zeroY}" x2="${W}" y2="${zeroY}" stroke="#ffffff" stroke-opacity="0.28"
      stroke-width="1" stroke-dasharray="5 4"/>
    <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2.4"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${X(SERIES.length-1).toFixed(1)}" cy="${Y(SERIES[SERIES.length-1]).toFixed(1)}"
      r="3.6" fill="${col}"/></svg>`;
  const tip=el("tip");
  box.querySelectorAll("svg").forEach(s=>s.remove());
  box.insertAdjacentHTML("afterbegin", svg);
  box.onmousemove=e=>{
    const r=box.getBoundingClientRect(); const x=e.clientX-r.left;
    let i=Math.round(x/W*(SERIES.length-1)); i=Math.max(0,Math.min(SERIES.length-1,i));
    tip.style.opacity=1; tip.style.left=X(i)+"px"; tip.style.top=Y(SERIES[i])+"px";
    tip.textContent=rup(SERIES[i]);
  };
  box.onmouseleave=()=>{tip.style.opacity=0;};
}
window.addEventListener("resize",draw);
</script></body></html>"""


def _updater(window):
    while True:
        try:
            window.evaluate_js(f"window.render({json.dumps(read_data())})")
        except Exception:
            pass
        time.sleep(3)


def main() -> None:
    window = webview.create_window(
        "Strangle P&L", html=HTML, width=420, height=230,
        frameless=True, easy_drag=True, on_top=True, transparent=True,
    )
    threading.Thread(target=_updater, args=(window,), daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()
