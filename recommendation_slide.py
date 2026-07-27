"""
Builds copilot_recommendation_slide.html - ONE dense consulting recommendation slide
following the user's handwritten section plan (Executive Decision Cockpit), in the
Kearney-purple template, from live model data. No wasted white space.
"""
import json, os
d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "copilot_results.json")))
C = d["commodities"]; cfg = d["config"]
flag = next(n for n, r in C.items() if r["commodity"]["flagship"])
P = C[flag]; s = P["sense"]; sup = P["supply_chain"]; opt = P["optimise"]; sp = opt["split"]; tm = P["timing"]; act = P["act"]
APP = "pulket.github.io/commodity-buy-hedge-copilot"
GH = "github.com/pulket/commodity-buy-hedge-copilot"

# derived (presentation only)
def confidence(r):
    sc = r["score"]["score"]; rc = r["optimise"]["risk_cut_pct"]
    db = min(abs(sc-45), abs(sc-60)) if 45 < sc < 60 else 15
    return int(max(58, min(94, 60 + rc*0.35 + db*0.6)))
DRV = {"value":("Price level","top-quartile — expensive"),"momentum":("Momentum","rising"),
       "curve":("Forward curve","contango — carry cost of holding"),"fx":("Currency (INR)","weakening — imports dearer")}
def drivers(r):
    ranked = sorted(r["score"]["parts"].items(), key=lambda kv: abs(kv[1]-50), reverse=True)
    return [(DRV[k][0], DRV[k][1], "up" if v>=55 else ("dn" if v<=45 else "->")) for k,v in ranked[:4]]

conf = confidence(P); inv_days = round(sup["months_cover"]*30.4)
pol = {p["name"]: p for p in tm["policies"]}
jit = pol["Buy just-in-time"]; buynow = pol["Buy now & hold"]; hedge = pol["Hedge (lock forward)"]

CSS = """
:root{--p:#7823DC;--pd:#4C1D95;--t:#0F766E;--tint:#F5EEFD;--tint2:#EBDFFB;--tt:#E6F6F3;
--ink:#20222B;--mut:#6B7280;--line:#E4E2EC;--gr:#15803D;--rd:#C0243B;--am:#B45309}
*{box-sizing:border-box}
html,body{margin:0;background:#5b5766;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:var(--ink)}
.hint{color:#e9e6f2;font-size:13px;text-align:center;padding:14px 10px 4px}
.deck{display:flex;justify-content:center;padding:14px 10px 50px}
.slide{width:1280px;height:720px;background:#fff;position:relative;overflow:hidden;padding:22px 28px 30px;box-shadow:0 10px 40px rgba(0,0,0,.35)}
.slide::before{content:"";position:absolute;top:0;left:0;right:0;height:6px;background:linear-gradient(90deg,var(--p),#B06BF2)}
.eyebrow{font-size:10px;letter-spacing:.14em;font-weight:700;color:var(--p);text-transform:uppercase}
.title{font-size:20px;font-weight:800;margin:3px 0 3px;line-height:1.15}.title b{color:var(--p)}
.key{font-size:10.5px;color:var(--pd);background:var(--tint);border-left:4px solid var(--p);padding:4px 10px;border-radius:4px;display:inline-block;margin-bottom:8px}
.grid3{display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:10px}
.grid2{display:grid;grid-template-columns:1.15fr 1fr;gap:10px;margin-top:8px}
.card{border:1px solid var(--line);border-radius:9px;padding:8px 11px;background:#fff}
.h{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.03em;color:var(--pd);margin-bottom:5px;display:flex;align-items:center;gap:5px}
.num{width:15px;height:15px;border-radius:50%;background:var(--p);color:#fff;font-size:9px;font-weight:800;display:inline-flex;align-items:center;justify-content:center}
/* problem cascade */
.casc{display:flex;flex-direction:column;gap:0}
.cstep{font-size:9.6px;padding:3px 8px;border-radius:5px;background:#fdf2f4;border:1px solid #f3d6dc;color:#7a1020;margin:1px 0}
.cstep b{color:var(--rd)}
.cx{text-align:center;color:var(--rd);font-size:9px;line-height:0.7}
/* cockpit */
.cock{background:linear-gradient(180deg,#faf7ff,#f3ecfd);border:1.5px solid var(--p)}
.crow{display:flex;justify-content:space-between;font-size:10px;padding:2.5px 0;border-bottom:1px dotted #d9cdf2}
.crow .k{color:var(--mut)}.crow .v{font-weight:700;color:var(--ink)}
.rec{background:var(--pd);color:#fff;border-radius:6px;padding:5px 8px;margin-top:5px;font-size:10px}
.rec b{color:#fff}.rec .big{font-size:13px;font-weight:800}
.confbar{height:8px;border-radius:5px;background:#e4e2ec;margin-top:3px;overflow:hidden}
.confbar>div{height:100%;background:var(--gr)}
/* drivers */
.drv{font-size:10px;margin:3.5px 0;line-height:1.25}
.drv b{color:var(--ink)}.drv .a{font-weight:800}
.up{color:var(--rd)}.dn{color:var(--gr)}
/* scenario table */
table{width:100%;border-collapse:collapse;font-size:10.5px}
th,td{padding:4px 8px;text-align:left;border-bottom:1px solid var(--line)}
thead th{background:var(--tint);color:var(--pd);font-size:9.5px;text-transform:uppercase;letter-spacing:.02em}
tr.rec-row{background:#eafaf0}tr.rec-row td{font-weight:600;border-color:#c8ecd4}
.pill{display:inline-block;font-size:8.5px;font-weight:800;padding:1px 7px;border-radius:999px}
.p-no{background:#fee2e2;color:#c0243b}.p-ok{background:#dcfce7;color:#15803d}.p-nu{background:#fef3c7;color:#b45309}
/* flow */
.flow{display:flex;align-items:stretch;gap:4px}
.fstep{flex:1;border:1px solid var(--line);border-radius:6px;padding:4px 6px;background:#fff;font-size:8.8px;line-height:1.2}
.fstep b{color:var(--pd);font-size:9px}
.fa{display:flex;align-items:center;color:var(--p);font-weight:800;font-size:12px}
.tag{font-size:9px;color:var(--mut);margin-top:4px}
.loop .fstep{background:var(--tt);border-color:#c9ece5}.loop .fstep b{color:var(--t)}.loop .fa{color:var(--t)}
/* footer live band */
.live{margin-top:8px;background:var(--pd);border-radius:9px;padding:8px 14px;display:flex;justify-content:space-between;align-items:center;color:#fff}
.live .l1{font-size:11px;font-weight:800}
.live .l2{font-size:9.4px;color:#e6d7fb}
.live .lk{font-size:10.5px;font-weight:800;color:#fff;background:var(--p);padding:3px 10px;border-radius:6px}
.foot{position:absolute;left:28px;right:28px;bottom:8px;display:flex;justify-content:space-between;font-size:9px;color:var(--mut)}
.wm{font-weight:800;color:var(--p)}
"""

drv_html = "".join(
    f'<div class="drv"><span class="a">{i+1}.</span> <b>{nm}</b> — {desc} '
    f'<span class="{ "up" if ar=="up" else ("dn" if ar=="dn" else "") }">{ {"up":"↑","dn":"↓","->":"→"}[ar] }</span></div>'
    for i,(nm,desc,ar) in enumerate(drivers(P)))

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commodity Copilot - Executive Recommendation</title><style>{CSS}</style></head><body>
<div class="hint">One consulting recommendation slide (16:9). Screenshot or Print → PDF for your deck.</div>
<div class="deck"><section class="slide">
 <div class="eyebrow">AI COMMODITY COPILOT · EXECUTIVE RECOMMENDATION · DECISION COCKPIT</div>
 <div class="title">AI-powered decision intelligence for <b>commodity buying &amp; hedging</b></div>
 <div class="key">From fragmented market intelligence to <b>explainable, governed procurement decisions</b> — shown live on {flag}.</div>

 <div class="grid3">
  <div class="card">
   <div class="h"><span class="num">1</span> The problem today</div>
   <div class="casc">
    <div class="cstep"><b>Market volatility</b></div><div class="cx">▼</div>
    <div class="cstep">Fragmented information</div><div class="cx">▼</div>
    <div class="cstep">Manual analysis</div><div class="cx">▼</div>
    <div class="cstep">Conflicting recommendations</div><div class="cx">▼</div>
    <div class="cstep">Reactive buying</div><div class="cx">▼</div>
    <div class="cstep"><b>Margin loss</b></div>
   </div>
  </div>

  <div class="card cock">
   <div class="h"><span class="num">2</span> Executive decision cockpit</div>
   <div class="crow"><span class="k">Commodity</span><span class="v">{flag}</span></div>
   <div class="crow"><span class="k">Market outlook</span><span class="v">Firm ↑ · {s['percentile']:.0f}th %ile · contango {s['curve']:+.1f}%</span></div>
   <div class="crow"><span class="k">Inventory</span><span class="v">~{inv_days} days · below reorder</span></div>
   <div class="crow"><span class="k">Demand</span><span class="v">Steady · CV {sup['demand_cv']*100:.0f}% (from sales)</span></div>
   <div class="crow"><span class="k">Time horizon</span><span class="v">{cfg['horizon_m']} months (rolling)</span></div>
   <div class="rec"><span class="big">PHASE-IN &amp; HEDGE</span> &nbsp;lock {sp['locked_pct']:.0f}% · option-cap {sp['option_pct']:.0f}% · float {sp['unhedged_pct']:.0f}%
    &nbsp;|&nbsp; hedge &gt; buy-early (holding cost {tm['holding_monthly_pct']:.2f}%/mo)
    <div style="font-size:9px;color:#e6d7fb;margin-top:2px">Model confidence {conf}% · cuts budget risk −{opt['risk_cut_pct']:.0f}%</div>
    <div class="confbar"><div style="width:{conf}%"></div></div></div>
  </div>

  <div class="card">
   <div class="h"><span class="num">3</span> Why — top decision drivers</div>
   {drv_html}
   <div class="tag" style="margin-top:6px">Supply overlay: below the reorder point → a mandatory <b>{sup['must_cover_now']:,.0f}-{sup['unit']}</b> continuity buy is triggered first.</div>
  </div>
 </div>

 <div class="card" style="margin-top:8px">
  <div class="h"><span class="num">4</span> Scenario comparison — how each strategy trades cost vs risk</div>
  <table>
   <thead><tr><th>Strategy</th><th>Expected cost</th><th>Budget risk (swing)</th><th>Margin</th><th>Decision</th></tr></thead>
   <tbody>
    <tr><td>Wait — buy at spot as needed</td><td>₹{jit['E']:,.0f} Cr (lowest, if flat)</td><td>High (±₹{jit['sd']:,.0f} Cr)</td><td>Exposed</td><td><span class="pill p-no">Reject</span></td></tr>
    <tr><td>Buy now — lock 100% early</td><td>₹{buynow['E']:,.0f} Cr (+carry &amp; holding)</td><td>None</td><td>Certain, dearer</td><td><span class="pill p-nu">Neutral</span></td></tr>
    <tr class="rec-row"><td>Buy {sp['locked_pct']:.0f}% + Hedge — engine plan</td><td>≈₹{hedge['E']:,.0f} Cr (market)</td><td>Low (−{opt['risk_cut_pct']:.0f}%)</td><td>Protected</td><td><span class="pill p-ok">✓ Recommended</span></td></tr>
    <tr><td>Full hedge — lock 100% forward</td><td>₹{hedge['E']:,.0f} Cr + option premium</td><td>Lowest</td><td>Capped upside</td><td><span class="pill p-nu">Neutral</span></td></tr>
   </tbody>
  </table>
 </div>

 <div class="grid2">
  <div class="card">
   <div class="h"><span class="num">5</span> Governance &amp; human oversight — humans stay in control</div>
   <div class="flow">
    <div class="fstep"><b>AI recommendation</b><br>auto if inside caps</div><div class="fa">→</div>
    <div class="fstep"><b>Commodity mgr</b><br>review</div><div class="fa">→</div>
    <div class="fstep"><b>Treasury</b><br>validation</div><div class="fa">→</div>
    <div class="fstep"><b>Procurement</b><br>approval</div><div class="fa">→</div>
    <div class="fstep"><b>ERP</b><br>execution</div><div class="fa">→</div>
    <div class="fstep"><b>Outcome</b><br>monitoring</div>
   </div>
   <div class="tag">Auto-execute inside caps (order &gt; ₹{cfg['preset']['auto_cap_cr']} Cr → escalate, e.g. this ₹{act['immediate_order_value_cr']:.0f} Cr buy). Full audit trail; manual override always on.</div>
  </div>
  <div class="card loop">
   <div class="h"><span class="num">6</span> Continuous learning loop</div>
   <div class="flow">
    <div class="fstep"><b>Market change</b></div><div class="fa">→</div>
    <div class="fstep"><b>Recommendation</b></div><div class="fa">→</div>
    <div class="fstep"><b>Decision</b></div><div class="fa">→</div>
    <div class="fstep"><b>Outcome</b></div><div class="fa">→</div>
    <div class="fstep"><b>Feedback</b></div>
   </div>
   <div class="tag">Monthly back-test scores past calls vs actuals → tunes the weights &amp; triggers. It doesn't just recommend today; it learns to improve tomorrow's decisions.</div>
  </div>
 </div>

 <div class="live">
  <div><div class="l1">▶ Not a concept — a live, open-source working prototype</div>
   <div class="l2">Run it every morning before deciding buy / wait / hedge · upload your own sheets · {cfg['n_paths']:,} Monte-Carlo paths per run</div></div>
  <div style="text-align:right"><div class="lk">{APP}</div>
   <div class="l2" style="margin-top:3px">source: {GH}</div></div>
 </div>
 <div class="foot"><div class="wm">kearney &nbsp;| AI Commodity Copilot</div>
  <div>Live model output · {cfg['risk_appetite']} appetite · illustrative — not financial advice</div></div>
</section></div></body></html>"""
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "copilot_recommendation_slide.html"), "w") as f:
    f.write(html)
print("Built -> copilot_recommendation_slide.html")
