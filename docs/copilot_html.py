"""
Builds two self-contained HTML files for the Commodity Copilot model:
  1. copilot_model_explained.html  -> detailed explainer + worked example + glossary
  2. copilot_slides.html           -> two Kearney-style consulting slides

Reads the real numbers from copilot_results.json (run commodity_copilot.py first).
Presentation only - no decision logic lives here.
"""
import json
import numpy as np
import commodity_copilot as cc   # only for load_series (the price line chart)

# ---- Kearney-ish palette ---------------------------------------------------
PURPLE, PURPLE_D = "#7823DC", "#4C1D95"
TINT, TINT2 = "#F5EEFD", "#EBDFFB"
INK, MUTE, LINE = "#20222B", "#6B7280", "#E4E2EC"
GREEN, RED, AMBER = "#15803D", "#C0243B", "#B45309"


def split_str(oo, sep=" &#183; "):
    """cover% + hedge% -> the 100% three-way split (so it never looks like 110)."""
    sp = oo["split"]
    return (f'{sp["locked_pct"]:.0f}% locked{sep}{sp["option_pct"]:.0f}% option'
            f'{sep}{sp["unhedged_pct"]:.0f}% float')


# ===========================================================================
# SVG helpers
# ===========================================================================
def line_chart(dates, vals, low, high, buy, slow, ccy):
    W, H, pad = 720, 230, 34
    lo = min(min(vals), buy, low) * 0.995
    hi = max(max(vals), slow, high) * 1.005
    n = len(vals)
    def x(i): return pad + (W - 2 * pad) * i / max(1, n - 1)
    def y(v): return H - pad - (H - 2 * pad) * (v - lo) / (hi - lo)
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    area = f"{pad},{H-pad} " + pts + f" {W-pad},{H-pad}"
    grid = ""
    for f in (0, .25, .5, .75, 1):
        v = lo + (hi - lo) * f; yy = y(v)
        grid += (f'<line x1="{pad}" y1="{yy:.1f}" x2="{W-pad}" y2="{yy:.1f}" stroke="{LINE}"/>'
                 f'<text x="2" y="{yy+3:.1f}" font-size="9" fill="{MUTE}">{v:,.0f}</text>')
    def hl(v, col, lab):
        yy = y(v)
        return (f'<line x1="{pad}" y1="{yy:.1f}" x2="{W-pad}" y2="{yy:.1f}" stroke="{col}" '
                f'stroke-width="1.2" stroke-dasharray="4,4"/>'
                f'<text x="{W-pad+3}" y="{yy+3:.1f}" font-size="10" fill="{col}">{lab}</text>')
    cur = vals[-1]
    return f'''<svg viewBox="0 0 {W+120} {H}" width="100%" style="max-width:820px">{grid}
      <polygon points="{area}" fill="{PURPLE}" opacity="0.07"/>
      <polyline points="{pts}" fill="none" stroke="{PURPLE}" stroke-width="2"/>
      {hl(buy, GREEN, f"buy trigger {buy:,.0f}")}{hl(slow, AMBER, f"slow-buy {slow:,.0f}")}
      <circle cx="{x(n-1):.1f}" cy="{y(cur):.1f}" r="4" fill="{PURPLE}"/>
      <text x="{x(n-1)-4:.1f}" y="{y(cur)-8:.1f}" font-size="10" fill="{PURPLE}" text-anchor="end">now {cur:,.0f} {ccy}</text>
      <text x="{pad}" y="{H-8}" font-size="9" fill="{MUTE}">{dates[0]}</text>
      <text x="{W-pad}" y="{H-8}" font-size="9" fill="{MUTE}" text-anchor="end">{dates[-1]}</text></svg>'''


def hbars(parts, weights):
    W, rowh, pad = 560, 30, 150
    names = {"value": "Value (cheap?)", "momentum": "Momentum (rising?)",
             "curve": "Curve (contango?)", "fx": "FX (rupee weaker?)"}
    order = ["value", "momentum", "curve", "fx"]
    H = rowh * len(order) + 34
    barw = W - pad - 95
    rows = ""
    for i, k in enumerate(order):
        yy = 8 + i * rowh; val = parts[k]; w = barw * val / 100
        col = PURPLE if val >= 50 else MUTE
        rows += (f'<text x="0" y="{yy+15}" font-size="11" fill="{INK}">{names[k]}</text>'
                 f'<rect x="{pad}" y="{yy+4}" width="{barw}" height="16" rx="3" fill="{LINE}"/>'
                 f'<rect x="{pad}" y="{yy+4}" width="{w:.0f}" height="16" rx="3" fill="{col}"/>'
                 f'<text x="{pad+barw+8}" y="{yy+16}" font-size="10" fill="{MUTE}">{val:.0f} (w{weights[k]*100:.0f}%)</text>')
    mid = pad + barw * .5
    rows += (f'<line x1="{mid}" y1="6" x2="{mid}" y2="{H-26}" stroke="{AMBER}" stroke-dasharray="3,3"/>'
             f'<text x="{mid}" y="{H-12}" font-size="9" fill="{AMBER}" text-anchor="middle">neutral = 50</text>')
    return f'<svg viewBox="0 0 {W+10} {H}" width="100%" style="max-width:640px">{rows}</svg>'


def frontier_scatter(grid, frontier, chosen, maxw=600):
    """x = expected cost (Cr), y = risk/volatility (Cr). Lower-left = better."""
    W, H, pad = 560, 300, 46
    Es = [g["E"] / 1e7 for g in grid]; Ss = [g["sd"] / 1e7 for g in grid]
    xlo, xhi = min(Es) * .999, max(Es) * 1.001
    ylo, yhi = 0, max(Ss) * 1.08
    def x(v): return pad + (W - 2 * pad) * (v - xlo) / (xhi - xlo)
    def y(v): return H - pad - (H - 2 * pad) * (v - ylo) / (yhi - ylo)
    # axes
    svg = (f'<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="{INK}"/>'
           f'<line x1="{pad}" y1="{pad-6}" x2="{pad}" y2="{H-pad}" stroke="{INK}"/>'
           f'<text x="{(W)/2}" y="{H-8}" font-size="10" fill="{MUTE}" text-anchor="middle">Expected cost (₹ Cr) → cheaper is left</text>'
           f'<text x="12" y="{pad-14}" font-size="10" fill="{MUTE}">Risk = cost volatility (₹ Cr)</text>')
    # all candidate strategies
    for g in grid:
        svg += f'<circle cx="{x(g["E"]/1e7):.1f}" cy="{y(g["sd"]/1e7):.1f}" r="3.2" fill="{MUTE}" opacity="0.5"/>'
    # efficient frontier line
    fr = sorted(frontier, key=lambda g: g["E"])
    fpts = " ".join(f'{x(g["E"]/1e7):.1f},{y(g["sd"]/1e7):.1f}' for g in fr)
    svg += f'<polyline points="{fpts}" fill="none" stroke="{PURPLE}" stroke-width="2" opacity="0.7"/>'
    for g in fr:
        svg += f'<circle cx="{x(g["E"]/1e7):.1f}" cy="{y(g["sd"]/1e7):.1f}" r="4" fill="{PURPLE}"/>'
    # naive (fully floating) and chosen
    naive = next(g for g in grid if g["cover"] == 0 and g["hedge"] == 0)
    svg += (f'<circle cx="{x(naive["E"]/1e7):.1f}" cy="{y(naive["sd"]/1e7):.1f}" r="6" fill="{RED}"/>'
            f'<text x="{x(naive["E"]/1e7)+8:.1f}" y="{y(naive["sd"]/1e7)+4:.1f}" font-size="10" fill="{RED}">do-nothing (all float)</text>')
    svg += (f'<circle cx="{x(chosen["E"]/1e7):.1f}" cy="{y(chosen["sd"]/1e7):.1f}" r="7" fill="{GREEN}" stroke="#fff" stroke-width="1.5"/>'
            f'<text x="{x(chosen["E"]/1e7):.1f}" y="{y(chosen["sd"]/1e7)-11:.1f}" font-size="10.5" fill="{GREEN}" text-anchor="middle" font-weight="700">engine pick</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{maxw}px">{svg}</svg>'


def dist_chart(dist, maxw=600):
    """Two overlaid cost distributions: do-nothing vs engine, with CaR95 marks."""
    W, H, pad = 560, 240, 40
    cx = dist["centers"]; nv = dist["naive"]; en = dist["engine"]
    xlo, xhi = cx[0], cx[-1]; ymax = max(max(nv), max(en)) * 1.1
    def x(v): return pad + (W - 2 * pad) * (v - xlo) / (xhi - xlo)
    def y(v): return H - pad - (H - 2 * pad) * v / ymax
    def poly(counts, col, fill):
        pts = " ".join(f"{x(c):.1f},{y(v):.1f}" for c, v in zip(cx, counts))
        area = f"{x(cx[0]):.1f},{H-pad} " + pts + f" {x(cx[-1]):.1f},{H-pad}"
        return (f'<polygon points="{area}" fill="{col}" opacity="{fill}"/>'
                f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.8"/>')
    svg = f'<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="{INK}"/>'
    svg += poly(nv, RED, 0.10) + poly(en, PURPLE, 0.16)
    def vline(v, col, lab, dy=0):
        return (f'<line x1="{x(v):.1f}" y1="{pad-4}" x2="{x(v):.1f}" y2="{H-pad}" stroke="{col}" stroke-dasharray="3,3"/>'
                f'<text x="{x(v):.1f}" y="{pad-6+dy}" font-size="9" fill="{col}" text-anchor="middle">{lab}</text>')
    svg += vline(dist["engine_car95"], PURPLE_D, f"engine CaR95 ₹{dist['engine_car95']:,.0f}", 0)
    svg += vline(dist["naive_car95"], RED, f"do-nothing CaR95 ₹{dist['naive_car95']:,.0f}", 12)
    svg += (f'<text x="{pad}" y="{H-8}" font-size="9" fill="{MUTE}">₹{xlo:,.0f} Cr</text>'
            f'<text x="{W-pad}" y="{H-8}" font-size="9" fill="{MUTE}" text-anchor="end">₹{xhi:,.0f} Cr</text>'
            f'<rect x="{W-150}" y="{pad}" width="10" height="10" fill="{PURPLE}" opacity="0.5"/>'
            f'<text x="{W-136}" y="{pad+9}" font-size="9.5" fill="{INK}">engine plan</text>'
            f'<rect x="{W-150}" y="{pad+14}" width="10" height="10" fill="{RED}" opacity="0.4"/>'
            f'<text x="{W-136}" y="{pad+23}" font-size="9.5" fill="{INK}">do-nothing</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{maxw}px">{svg}</svg>'


def reduction_bars(items):
    """items = [(label, pct)] volatility reduction per commodity."""
    W, rowh, pad = 520, 30, 130
    H = rowh * len(items) + 16
    barw = W - pad - 60; mx = 50
    rows = ""
    for i, (lab, pct) in enumerate(items):
        yy = 8 + i * rowh; w = barw * min(pct, mx) / mx
        rows += (f'<text x="0" y="{yy+16}" font-size="11" fill="{INK}">{lab}</text>'
                 f'<rect x="{pad}" y="{yy+5}" width="{barw}" height="16" rx="3" fill="{LINE}"/>'
                 f'<rect x="{pad}" y="{yy+5}" width="{w:.0f}" height="16" rx="3" fill="{GREEN}"/>'
                 f'<text x="{pad+w+6}" y="{yy+17}" font-size="10" fill="{MUTE}">{pct:.0f}% steadier</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:560px">{rows}</svg>'


def corr_table(names, corr):
    cells = "<tr><td></td>" + "".join(f'<th>{n.split()[0]}</th>' for n in names) + "</tr>"
    for a in names:
        row = f"<tr><th style='text-align:left'>{a.split()[0]}</th>"
        for b in names:
            v = corr[a][b]
            inten = min(abs(v), 1)
            bg = (f"rgba(120,35,220,{0.10+0.55*inten})" if v > 0.05 else
                  (f"rgba(192,36,59,{0.10+0.4*inten})" if v < -0.05 else "#f3f4f8"))
            fg = "#fff" if v > 0.55 else INK
            row += f'<td style="background:{bg};color:{fg}">{v:+.2f}</td>'
        cells += row + "</tr>"
    return (f'<table class="corr"><tbody>{cells}</tbody></table>')


# ===========================================================================
# EXPLAINER
# ===========================================================================
EXP_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f6f7fb;color:#20222b;font:15px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:26px 20px 80px}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:34px 0 8px;padding-top:12px;border-top:2px solid #ececf2}
h3{font-size:15px;margin:16px 0 6px;color:#7823dc}
.sub{color:#6b7280;margin:0 0 16px}
.card{background:#fff;border:1px solid #e4e2ec;border-radius:12px;padding:16px 18px;margin:12px 0;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600}
.buy{background:#dcfce7;color:#15803d}.wait{background:#fee2e2;color:#c0243b}.phase{background:#fef3c7;color:#b45309}.hedge{background:#ebdffb;color:#4c1d95}
.big{font-size:32px;font-weight:800;line-height:1;color:#4c1d95}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi{background:#fff;border:1px solid #e4e2ec;border-radius:10px;padding:11px 13px}
.kpi .l{font-size:10.5px;color:#6b7280;text-transform:uppercase;letter-spacing:.03em}
.kpi .v{font-size:19px;font-weight:800;margin-top:2px;color:#4c1d95}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0}
th,td{padding:7px 9px;text-align:right;border-bottom:1px solid #eef0f4}
th:first-child,td:first-child{text-align:left}
thead th{background:#f5eefd;color:#4c1d95;font-size:11.5px;text-transform:uppercase;letter-spacing:.02em}
.corr{width:auto}.corr th,.corr td{text-align:center;padding:6px 12px;border:1px solid #eef0f4;font-size:12px}
.muted{color:#6b7280}.chart-wrap{overflow-x:auto}
.step{display:flex;gap:12px;align-items:flex-start;margin:8px 0}
.num{flex:0 0 26px;height:26px;border-radius:50%;background:#7823dc;color:#fff;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center;margin-top:2px}
.callout{background:#f5eefd;border:1px solid #d8b8fb;border-radius:10px;padding:12px 15px;margin:12px 0}
.math{background:#faf7ff;border:1px solid #e4d3fb;border-radius:8px;padding:10px 14px;font-size:14px}
code{background:#f3f4f8;border:1px solid #e4e2ec;padding:1px 5px;border-radius:4px;font-size:12.5px}
.trg{border-left:3px solid #7823dc;padding:5px 0 5px 12px;margin:7px 0;font-size:13.5px}
.foot{color:#6b7280;font-size:12px;margin-top:26px;text-align:center}
.tag{font-size:11px;color:#6b7280}
"""


def build_explainer(d, palm_series, out):
    cfg = d["config"]; port = d["portfolio"]; C = d["commodities"]
    flag_name = next(n for n, r in C.items() if r["commodity"]["flagship"])
    P = C[flag_name]; s = P["sense"]; sc = P["score"]; opt = P["optimise"]
    ch = opt["chosen"]; act = P["act"]; bt = P["backtest"]; dist = opt["dist"]
    sup = P["supply_chain"]; sp = opt["split"]; caps = opt["caps"]
    ccy, unit = s["ccy"], s["unit"]
    lo, hi = s["low52"], s["high52"]
    buy_t = lo + .25 * (hi - lo); slow_t = lo + .75 * (hi - lo)
    dates, vals = palm_series

    # multi-commodity summary rows
    def acls(a): return "buy" if "BUY" in a else ("wait" if "WAIT" in a else "phase")
    rows = ""
    for n, r in C.items():
        ss, scc, oo, aa = r["sense"], r["score"], r["optimise"], r["act"]
        star = " ★" if r["commodity"]["flagship"] else ""
        rows += (f'<tr><td><b>{n}{star}</b></td>'
                 f'<td>{ss["spot"]:,.0f} {ss["ccy"]}</td><td>{ss["percentile"]:.0f}</td>'
                 f'<td>{ss["vol"]:.0f}%</td><td>{ss["curve"]:+.1f}%</td>'
                 f'<td><span class="pill {acls(scc["action"])}">{scc["action"]}</span></td>'
                 f'<td style="font-size:11.5px">{split_str(oo)}</td>'
                 f'<td>-{oo["risk_cut_pct"]:.0f}%</td>'
                 f'<td>{"AUTO" if aa["decision"]=="AUTO-EXECUTE" else "ESCALATE"}</td></tr>')

    sig_rows = "".join(f'<tr><td>{a}</td><td>{b}</td><td class="muted" style="text-align:left">{c}</td></tr>' for a, b, c in [
        ("Spot", f"{s['spot']:,.0f} {ccy}/{unit}", "Today's price (nearest futures)."),
        ("52-week range", f"{lo:,.0f} - {hi:,.0f}", "Cheapest & dearest in a year."),
        ("Price percentile", f"{s['percentile']:.0f}/100", "0 = cheapest, 100 = dearest. Higher = expensive."),
        ("Momentum (~1m)", f"{s['momentum']:+.1f}%", "Recent direction."),
        ("Volatility (yr)", f"{s['vol']:.0f}%", "How jumpy = how much risk."),
        ("6-month curve", f"{s['curve']:+.1f}%", "+contango = costs to lock; -backwardation = paid to lock."),
        ("Landed cost", f"₹{s['landed']:,.0f}/{unit}", "Price + FX + freight + duty. Hits the P&L."),
    ])

    trg = "".join(f'<div class="trg"><b>IF</b> {t["if"]} &nbsp;<b>THEN</b> {t["then"]}</div>' for t in P["triggers"])
    preset = cfg["preset"]
    presets_rows = "".join(
        f'<tr><td>{k.title()}</td><td>{v["lambda"]}</td><td>{v["max_cover"]*100:.0f}%</td>'
        f'<td>{v["max_hedge"]*100:.0f}%</td><td>₹{v["auto_cap_cr"]} Cr</td></tr>'
        for k, v in cc.PRESETS.items())

    price_svg = line_chart(dates, vals, lo, hi, buy_t, slow_t, ccy)
    bars_svg = hbars(sc["parts"], {"value": .35, "momentum": .20, "curve": .25, "fx": .20})
    fr_svg = frontier_scatter(opt["grid"], opt["frontier"], ch)
    dist_svg = dist_chart(dist)
    red_svg = reduction_bars([(n, C[n]["backtest"]["vol_reduction_pct"]) for n in C])
    corr_svg = corr_table(port["commodities"], port["corr"])

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commodity Copilot - model explained</title><style>{EXP_CSS}</style></head><body><div class="wrap">

<h1>Commodity Copilot - how the model works</h1>
<p class="sub">A transparent <b>Sense &#8594; Score &#8594; Decide &#8594; Act</b> engine that decides
<b>what, when, how much, and whether to hedge</b> across a basket of commodities - and acts inside
guardrails. Worked example below: <b>{flag_name}</b> (imported India &#8592; Malaysia), plus crude &amp; silver.</p>

<div class="card">
 <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:16px;align-items:center">
  <div><div class="tag">FLAGSHIP PLAN TODAY ({flag_name}) &mdash; % of net requirement</div>
   <div class="big">{sp['locked_pct']:.0f}% locked &#183; {sp['option_pct']:.0f}% option &#183; {sp['unhedged_pct']:.0f}% float</div>
   <div class="tag" style="margin-top:2px">(= 100%; "locked" = physical forwards, "option" = price caps)</div>
   <div style="margin-top:8px"><span class="pill {acls(sc['action'])}">{sc['action']}</span>
    <span class="pill hedge">{act['decision']}</span></div></div>
  <div style="text-align:right"><div class="tag">RISK CUT vs BUYING BLINDLY</div>
   <div class="big" style="color:#15803d">-{opt['risk_cut_pct']:.0f}%</div>
   <div class="tag" style="margin-top:6px">cost volatility, at ~equal expected cost<br>(insurance, not a discount)</div></div>
 </div>
</div>

<div class="grid">
 <div class="kpi"><div class="l">Portfolio 6-mo spend</div><div class="v">₹{port['total_spend_cr']:,.0f} Cr</div></div>
 <div class="kpi"><div class="l">Risk (added up)</div><div class="v">₹{port['additive_sd_cr']:,.0f} Cr</div></div>
 <div class="kpi"><div class="l">Risk (netted)</div><div class="v">₹{port['portfolio_sd_cr']:,.0f} Cr</div></div>
 <div class="kpi"><div class="l">Natural-hedge benefit</div><div class="v">{port['diversification_benefit_pct']:.0f}%</div></div>
 <div class="kpi"><div class="l">Monte-Carlo paths</div><div class="v">{cfg['n_paths']:,}</div></div>
</div>

<h2>1. What's different from a simple rule</h2>
<p>Instead of a rule of thumb, the engine <b>simulates thousands of possible price futures</b>
and picks the buy/hedge mix that is best on a metric combining <b>cost AND stability</b>. It runs
this for every commodity, then nets the risks across the portfolio. Four stages:</p>
<div class="card">
 <div class="step"><div class="num">S</div><div><b>Sense</b> - read the market for each commodity: 6 signals from price, curve, FX &amp; freight.</div></div>
 <div class="step"><div class="num">S</div><div><b>Score</b> - turn signals into a 0-100 Buy-Now score (buy / phase / wait).</div></div>
 <div class="step"><div class="num">D</div><div><b>Decide</b> - Monte-Carlo the cost of every candidate strategy and pick the one that minimises <b>RALC</b> (below), inside the appetite caps.</div></div>
 <div class="step"><div class="num">A</div><div><b>Act</b> - auto-execute if the order sits inside the council's guardrails, otherwise escalate.</div></div>
</div>

<h2>2. The whole basket at a glance</h2>
<div class="chart-wrap"><table>
 <thead><tr><th>Commodity</th><th>Spot</th><th>%ile</th><th>Vol</th><th>Curve</th><th>Buy-now</th><th>Plan (=100% of net need)</th><th>Risk cut</th><th>Act</th></tr></thead>
 <tbody>{rows}</tbody></table></div>
<p class="muted">Notice the engine adapts per commodity: palm is expensive &amp; contango &#8594; phase in;
crude is in backwardation (you're <i>paid</i> to lock) &#8594; cover even though timing says wait;
silver is cheap-ish but very volatile &#8594; buy &amp; hedge.</p>

<h2>3. Supply chain &mdash; from demand to how much we ACTUALLY buy</h2>
<p>Price is only half the story. Before pricing anything, the engine turns <b>demand, inventory, lead time
and supplier limits</b> into the real volume to source &mdash; and the non-negotiable "must-buy-now"
quantity that protects supply continuity. <b>Demand and its volatility are read from the company's real sales
file</b> (~{cfg['sales']['annual_demand']:,.0f} units/yr, demand swings <b>CV {sup['demand_cv']*100:.0f}%</b>
month-to-month) &mdash; not assumed. For <b>{flag_name}</b>:</p>
<div class="chart-wrap"><table>
 <thead><tr><th>Supply-chain step</th><th>Value</th><th>What it means</th></tr></thead><tbody>
 <tr><td>Demand over 6 months</td><td>{sup['horizon_demand']:,.0f} {unit}</td><td>From the real sales run-rate ({cfg['sales']['annual_demand']:,.0f}/yr &divide; 2).</td></tr>
 <tr><td>Inventory on hand</td><td>{sup['inventory']:,.0f} {unit}</td><td>= {sup['months_cover']:.1f} months of cover already in stock.</td></tr>
 <tr><td>Safety stock (keep aside)</td><td>{sup['safety_stock']:,.0f} {unit}</td><td>Sized from the real demand volatility (CV {sup['demand_cv']*100:.0f}%), not a guess.</td></tr>
 <tr><td>Usable inventory</td><td>{sup['usable_inventory']:,.0f} {unit}</td><td>Stock above safety we can burn down (inventory &minus; safety).</td></tr>
 <tr><td><b>Net procurement</b></td><td><b>{sup['net_procurement']:,.0f} {unit}</b></td><td>What we actually buy = demand &minus; usable inventory. <b>Every rupee figure uses this.</b></td></tr>
 <tr><td>Reorder point</td><td>{sup['reorder_point']:,.0f} {unit}</td><td>lead-time demand + safety. Below this &#8594; must reorder.</td></tr>
 <tr><td><b>Must-cover now</b></td><td><b>{sup['must_cover_now']:,.0f} {unit}</b></td><td>Immediate mandatory buy to get back above the reorder point &mdash; regardless of price.</td></tr>
 <tr><td>Suppliers / origins</td><td>{sup['n_suppliers']} &middot; {sup['origins']}</td><td>Can forward-commit up to {sup['supplier_share']*100:.0f}% of demand (a real cap on how much we can lock).</td></tr>
</tbody></table></div>
<div class="callout"><b>Why this matters:</b> the {sup['inventory']:,.0f} {unit} we already hold cuts the buy from
{sup['horizon_demand']:,.0f} to <b>{sup['net_procurement']:,.0f} {unit}</b>. But cover is
{sup['months_cover']:.1f} months and the reorder point is {sup['reorder_point']:,.0f} {unit}, so we are
<b>below reorder</b> &mdash; the engine forces a mandatory <b>{sup['must_cover_now']:,.0f} {unit}</b> buy now
to protect supply, <i>before</i> it starts optimising for price. Supplier capacity ({sup['supplier_share']*100:.0f}%)
also caps how much we may physically lock.</div>

<h2>4. Deep dive - {flag_name}</h2>

<div class="step"><div class="num">S</div><div style="flex:1">
 <h3 style="margin-top:2px">Sense - the 6 signals</h3>
 <div class="chart-wrap"><table><thead><tr><th>Signal</th><th>Value</th><th>Meaning</th></tr></thead><tbody>{sig_rows}</tbody></table></div>
 <div class="chart-wrap">{price_svg}</div>
</div></div>

<div class="step"><div class="num">S</div><div style="flex:1">
 <h3>Score - buy now, phase, or wait?</h3>
 <p>Four sub-scores blend into one Buy-Now score. Above 60 buy, 45-60 phase, below 45 wait.</p>
 <div class="chart-wrap">{bars_svg}</div>
 <p class="muted">Blended score = <b>{sc['score']:.0f}/100 &#8594; {sc['action']}</b>. Palm is dear (low value)
 but contango &amp; a weak rupee push toward securing supply - hence "phase in", not "wait".</p>
</div></div>

<div class="step"><div class="num">D</div><div style="flex:1">
 <h3>Decide - the RALC metric and the efficient frontier</h3>
 <p>You asked for a metric that balances <b>cost</b> and <b>stability</b>. The engine minimises:</p>
 <div class="math"><b>RALC = E[Cost] + &#955; &#215; SD[Cost]</b><br>
  <span class="muted">expected cost + a penalty on how much that cost can swing.
  &#955; (risk-aversion) = <b>{cfg['preset']['lambda']}</b> for the "{cfg['risk_appetite']}" preset
  (Conservative 1.5 &#183; Balanced 0.8 &#183; Aggressive 0.3).</span></div>
 <p>Each dot below is one candidate strategy (a cover% &#215; hedge% mix), scored by Monte-Carlo on
 <b>expected cost</b> (left = cheaper) vs <b>risk</b> (down = steadier). The purple line is the
 <b>efficient frontier</b> - the best you can do. The engine picks the frontier point that matches
 the appetite's &#955;.</p>
 <div class="chart-wrap">{fr_svg}</div>
 <div class="callout"><b>The chosen plan &mdash; and why it is 100%, not 110%.</b> The engine picks
  <b>cover = {ch['cover']*100:.0f}%</b> and <b>hedge = {ch['hedge']*100:.0f}%</b>. But "hedge {ch['hedge']*100:.0f}%"
  means {ch['hedge']*100:.0f}% <i>of the un-locked {(1-ch['cover'])*100:.0f}%</i>, not of the total. So the real
  split of the net requirement is:
  <ul style="margin:6px 0">
   <li><b>{sp['locked_pct']:.0f}% locked</b> now via physical forwards (= cover {ch['cover']*100:.0f}%)</li>
   <li><b>{sp['option_pct']:.0f}% option-hedged</b> (= {ch['hedge']*100:.0f}% &times; the remaining {(1-ch['cover'])*100:.0f}%)</li>
   <li><b>{sp['unhedged_pct']:.0f}% left floating</b> (the rest of the remaining {(1-ch['cover'])*100:.0f}%)</li>
  </ul>
  <b>{sp['locked_pct']:.0f} + {sp['option_pct']:.0f} + {sp['unhedged_pct']:.0f} = 100%.</b></div>
 <p class="muted"><b>Why {ch['cover']*100:.0f}% &amp; {ch['hedge']*100:.0f}% exactly?</b> Both hit the
  "{cfg['risk_appetite']}" preset's caps &mdash; the optimiser wanted to reduce risk further, but the caps stop it:
  cover is limited to {caps['cover_cap']*100:.0f}% (the smaller of the appetite cap {caps['appetite_cover_cap']*100:.0f}%
  and what suppliers will commit, {caps['supplier_share']*100:.0f}%) and hedge to {caps['hedge_cap']*100:.0f}%.
  Result: E[cost] ₹{ch['E']/1e7:,.0f} Cr, risk ₹{ch['sd']/1e7:,.1f} Cr, CaR95 ₹{ch['car95']/1e7:,.0f} Cr.
  Instrument: {opt['instrument']}.</p>

 <h3>The pay-off distribution (why it's insurance)</h3>
 <p>Running 20,000 price futures gives the full range of possible total cost. Do-nothing (red) has a
 long expensive tail; the engine plan (purple) is far tighter - a much lower <b>worst case (CaR95)</b>.</p>
 <div class="chart-wrap">{dist_svg}</div>
 <p class="muted">Do-nothing worst-case (95%) ₹{dist['naive_car95']:,.0f} Cr vs engine
 ₹{dist['engine_car95']:,.0f} Cr - the plan trims the bad tail. Expected cost is about the same
 (₹{dist['naive_E']:,.0f} vs ₹{dist['engine_E']:,.0f} Cr): you buy stability, not a discount.</p>

 <h3>WHEN to buy - physical (with holding cost) vs hedge</h3>
 <p>Cover% and hedge% answer <i>how much</i>; this answers <i>when</i>. A <b>dynamic program</b> schedules
 buys week-by-week on the forward price path, charging a <b>holding cost of {P['timing']['holding_monthly_pct']:.2f}%/month</b>
 (finance + storage + insurance) for anything bought early, and respecting the <b>{P['timing']['lead_weeks']}-week lead
 time</b>. Each plan is then priced over the 20,000 paths (so it carries real price risk) and ranked on RALC.
 The core trade-off is simple: <b>is the forward price you would lock cheaper than buying at spot and paying to
 hold it?</b></p>
 <div class="chart-wrap"><table><thead><tr><th>Plan</th><th>Type</th><th>E[cost]</th><th>Risk (SD)</th><th>CaR95</th><th>RALC</th></tr></thead><tbody>
 {''.join(f'<tr style="background:{"#eafaf0" if p["name"]==P["timing"]["recommended"] else "#fff"}"><td>{p["name"]}</td><td>{p["kind"]}</td><td>₹{p["E"]:,.0f} Cr</td><td>₹{p["sd"]:,.1f} Cr</td><td>₹{p["car95"]:,.0f} Cr</td><td><b>₹{p["ralc"]:,.0f} Cr</b></td></tr>' for p in P["timing"]["policies"])}
 </tbody></table></div>
 <div class="callout"><b>Verdict for {flag_name}: {P['timing']['verdict']}.</b> Best physical plan
 ("{P['timing']['phys_best']}") has RALC ₹{P['timing']['phys_best_ralc_cr']:.0f} Cr vs hedge
 ₹{P['timing']['hedge_ralc_cr']:.0f} Cr. Here holding cost ({P['timing']['holding_monthly_pct']:.2f}%/mo) is larger
 than the weekly forward carry, so the DP finds <b>just-in-time</b> is the best physical timing - buying early to
 hold isn't worth it. The engine then picks whichever of best-physical vs hedge is cheaper on a risk-adjusted basis.
 (Crude, in backwardation, favours hedge strongly; silver, in steeper contango, tips to buy-physical.)</div>
</div></div>

<div class="step"><div class="num">A</div><div style="flex:1">
 <h3>Act - guardrails (auto-execute vs escalate)</h3>
 <div class="callout">Near-term order = <b>₹{act['immediate_order_value_cr']:.1f} Cr</b> &nbsp;|&nbsp;
  auto-execute cap = <b>₹{act['auto_execute_cap_cr']} Cr</b> &nbsp;&#8594;&nbsp;
  <b>{act['decision']}</b><br><span class="muted">{act['reason']}.</span></div>
 <h3>Trigger playbook</h3>{trg}
 <h3>Backtest - would it have helped? (real history)</h3>
 <p>Replaying on the last year of prices, the engine's cost line was materially steadier than naive
 spot buying, at roughly equal cost:</p>
 <div class="chart-wrap">{red_svg}</div>
</div></div>

<h2>5. Portfolio view - the multi-commodity pay-off</h2>
<p>Because commodities don't move together, buying them as a <b>portfolio</b> nets some risk away.
Correlations of daily returns:</p>
<div class="chart-wrap">{corr_svg}</div>
<div class="callout">If the three risks simply added up: <b>₹{port['additive_sd_cr']:,.0f} Cr</b>.
 Netted across the portfolio: <b>₹{port['portfolio_sd_cr']:,.0f} Cr</b> &#8594;
 a <b>{port['diversification_benefit_pct']:.0f}% natural-hedge benefit</b> at no extra cost, purely from
 managing them together instead of in silos.</div>

<h2>6. Risk-appetite presets (one dial, set by the council)</h2>
<div class="chart-wrap"><table><thead><tr><th>Preset</th><th>&#955; (RALC)</th><th>Max cover</th><th>Max hedge</th><th>Auto-execute cap</th></tr></thead><tbody>{presets_rows}</tbody></table></div>
<p class="muted">The preset sets both the optimiser's &#955; and the hard caps the autonomy runs inside -
so risk appetite is a single, governed choice.</p>

<h2>7. Where exactly the AI / LLM is used (and where it is NOT)</h2>
<p>This is important: the AI does <b>not</b> invent the numbers. The pricing maths (RALC, Monte-Carlo, the
frontier) stays a <b>transparent, auditable engine</b>. The AI sits <i>around</i> it &mdash; it turns messy
real-world text into structured, cited inputs, explains and drafts, and executes inside hard limits. Here is
every touchpoint, mapped to the four stages:</p>
<div class="chart-wrap"><table>
 <thead><tr><th>Stage</th><th>AI component</th><th>Technique</th><th>Reads</th><th>Produces</th><th>Human control</th></tr></thead>
 <tbody>
 <tr><td><b>SENSE</b></td><td>Market sensing</td><td><b>LLM</b></td><td>News, MPOB/USDA reports, export-duty notices, weather &amp; port advisories, analyst notes</td><td>A <b>fundamentals bias (&minus;1..+1)</b> per commodity, each with a one-line reason + source link</td><td>Analyst sees the citation; can reject it</td></tr>
 <tr><td><b>SENSE</b></td><td>Document extraction</td><td><b>LLM</b></td><td>Supplier contracts, invoices, customs &amp; quality docs, ERP demand files</td><td>Structured fields (volumes, prices, incoterms, dates) that feed inventory &amp; lead-time inputs automatically</td><td>Validated against ERP</td></tr>
 <tr><td><b>SCORE</b></td><td>&mdash; (deliberately none)</td><td>Rules</td><td>The 6 signals</td><td>The 0&ndash;100 score by a fixed formula</td><td>Kept rules-based on purpose so it is auditable</td></tr>
 <tr><td><b>DECIDE</b></td><td>Scenario forecasting</td><td><b>ML</b> (+LLM)</td><td>Price/vol history + the LLM's event read</td><td>Probabilities for the price paths (replaces the plain random walk); a fatter up-tail if an export ban is likely</td><td>Council sets the risk preset (&lambda;, caps)</td></tr>
 <tr><td><b>DECIDE</b></td><td>Anomaly detection</td><td><b>ML</b></td><td>Live price, FX, freight, basis</td><td>Flags an odd move and auto-fires the matching trigger</td><td>Alerts a human; thresholds are set</td></tr>
 <tr><td><b>ACT</b></td><td>Agentic execution &amp; drafting</td><td><b>LLM agent</b></td><td>The engine's chosen plan + the policy caps</td><td>Drafts the order, checks it vs guardrails, auto-executes inside caps <i>or</i> writes the escalation memo</td><td>Hard caps + manual override; every action audited</td></tr>
 <tr><td><b>ALL</b></td><td>Natural-language Q&amp;A &amp; explanations</td><td><b>LLM</b></td><td>A plain-English question + the live model</td><td>"Margin if palm +10% &amp; rupee &minus;3%?" &#8594; runs the model &amp; explains; also writes the council memo &amp; weekly brief</td><td>Answers link back to the model run</td></tr>
 <tr><td><b>MONITOR</b></td><td>Learning loop</td><td>ML + <b>LLM</b></td><td>Monthly back-test: calls vs actuals</td><td>Summarises what went right/wrong &amp; proposes weight/trigger tweaks</td><td>Changes need human sign-off</td></tr>
 </tbody></table></div>
<div class="callout"><b>The one rule that makes it trustworthy:</b> the LLM converts <i>text &#8594; structured, cited input</i>
and drafts/explains/executes; it never sets a price or overrides a guardrail. So you get AI's reach over messy
real-world information <b>plus</b> a fully auditable number engine &mdash; exactly what a large organisation can pilot.</div>

<h2>8. How to run / change it</h2>
<div class="callout"><b>To change the example:</b> edit <code>RISK_APPETITE</code>, demand, inventory or the
commodity list at the top of <code>commodity_copilot.py</code>, run <code>python3 commodity_copilot.py</code>,
then <code>python3 copilot_html.py</code> to rebuild this page and the slides.</div>

<p class="foot">Generated by commodity_copilot.py + copilot_html.py from the data files in this folder.
Illustrative decision-support tool - not financial advice.</p>
</div></body></html>"""
    with open(out, "w") as fh:
        fh.write(html)


# ===========================================================================
# SLIDES  (two Kearney-style 16:9 slides)
# ===========================================================================
SLIDE_CSS = """
:root{--p:#7823DC;--pd:#4C1D95;--tint:#F5EEFD;--tint2:#EBDFFB;--ink:#20222B;--mut:#6B7280;--line:#E4E2EC;--gr:#15803D;--rd:#C0243B}
*{box-sizing:border-box}
html,body{margin:0;background:#5b5766;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:var(--ink)}
.hint{color:#e9e6f2;font-size:13px;text-align:center;padding:16px 10px 4px}
.deck{display:flex;flex-direction:column;align-items:center;gap:26px;padding:14px 10px 60px}
.slide{width:1280px;height:720px;background:#fff;position:relative;box-shadow:0 10px 40px rgba(0,0,0,.35);overflow:hidden;padding:26px 34px 40px}
.slide::before{content:"";position:absolute;top:0;left:0;right:0;height:6px;background:linear-gradient(90deg,var(--p),#B06BF2)}
.eyebrow{font-size:10.5px;letter-spacing:.14em;font-weight:700;color:var(--p);text-transform:uppercase;margin-top:6px}
.atitle{font-size:20px;line-height:1.25;font-weight:700;margin:5px 0 8px;max-width:1180px}
.atitle b{color:var(--p)}
.rule{height:2px;background:var(--ink);opacity:.85;margin:0 0 12px}
.foot{position:absolute;left:34px;right:34px;bottom:12px;display:flex;justify-content:space-between;align-items:center;font-size:9.5px;color:var(--mut);border-top:1px solid var(--line);padding-top:6px}
.wm{font-weight:800;color:var(--p);font-size:14px}.wm span{color:var(--ink)}
.box{border:1px solid var(--line);border-radius:8px;padding:9px 11px;background:#fff}
.box h4{margin:0 0 5px;font-size:11px;letter-spacing:.03em;text-transform:uppercase;color:var(--pd);font-weight:700;display:flex;align-items:center;gap:6px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--p);display:inline-block}
.sm{font-size:10.5px;line-height:1.4}.xs{font-size:9.4px;line-height:1.34;color:var(--mut)}
b.p{color:var(--pd)}
ol,ul{margin:3px 0;padding-left:16px}li{margin:2px 0}
.chip{display:inline-block;background:#fff;border:1px solid var(--p);color:var(--pd);border-radius:999px;font-size:9.5px;font-weight:600;padding:2px 8px;margin:2px 3px 0 0}
code{background:var(--tint);border:1px solid var(--line);border-radius:4px;padding:0 4px;font-size:10px}
/* slide1 */
.s1{display:grid;grid-template-columns:350px 1fr;gap:16px;height:496px}
.lcol{display:flex;flex-direction:column;gap:10px}
.arch{display:flex;gap:10px;height:100%}
.stack{flex:1;display:flex;flex-direction:column;justify-content:space-between}
.layer{display:flex;gap:9px;align-items:stretch}
.ltag{flex:0 0 92px;border-radius:7px;color:#fff;background:var(--pd);display:flex;flex-direction:column;justify-content:center;padding:6px 8px}
.ltag b{font-size:10.5px;line-height:1.15}.ltag span{font-size:8.4px;opacity:.85}
.lb{flex:1;display:flex;gap:7px}
.ab{flex:1;border:1px solid var(--line);border-radius:7px;background:#fff;padding:6px 7px;display:flex;flex-direction:column;justify-content:center}
.ab b{font-size:9.8px;line-height:1.13}.ab span{font-size:8.2px;color:var(--mut);line-height:1.18;margin-top:1px}
.ab.pill{background:var(--tint);border-color:var(--p)}.ab.dec{background:var(--tint2);border-color:var(--p)}.ab.dec b{color:var(--pd)}
.lanes{flex:1;display:flex;flex-direction:column;gap:4px;justify-content:center}
.lane{display:flex;gap:6px;align-items:stretch}
.llab{flex:0 0 22px;border-radius:5px;font-size:7.5px;font-weight:800;display:flex;align-items:center;justify-content:center;color:#fff}
.llab.fin{background:#4C1D95}.llab.sc{background:#0f766e}
.ab.sc{background:#e6f6f3;border-color:#14b8a6}.ab.sc b{color:#0f766e}.ab.sc span{color:#4b6360}
.ab{padding:4px 7px}
.arw{height:13px;display:flex;align-items:center;justify-content:center}
.airail{flex:0 0 138px;border:1px solid var(--p);border-radius:8px;background:linear-gradient(180deg,#faf5ff,#f1e6fd);padding:8px 9px;display:flex;flex-direction:column}
.airail h4{margin:0 0 4px;font-size:10px;color:var(--pd);text-transform:uppercase;font-weight:800}
.airail .ai{font-size:9.2px;line-height:1.25;margin:3.5px 0;border-left:2px solid var(--p);padding-left:6px}
.airail .ai b{color:var(--pd)}
.band{margin-top:9px;display:flex;gap:8px}
.bc{flex:1;border:1px solid var(--line);border-left:3px solid var(--p);border-radius:6px;padding:6px 8px}
.bc b{font-size:10px;color:var(--pd)}.bc span{display:block;font-size:8.8px;color:var(--mut);margin-top:1px}
/* slide2 */
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:10px}
.kpi{border:1px solid var(--line);border-radius:7px;padding:6px 9px;background:#fff}
.kpi .l{font-size:8.4px;text-transform:uppercase;letter-spacing:.03em;color:var(--mut)}
.kpi .v{font-size:15px;font-weight:800;color:var(--pd);margin-top:1px;line-height:1.05}
.kpi .n{font-size:8.2px;color:var(--mut)}
.s2{display:grid;grid-template-columns:1.15fr 1fr;gap:14px;height:452px}
.col{display:flex;flex-direction:column;gap:9px}
table.t{width:100%;border-collapse:collapse;font-size:10px}
table.t th,table.t td{padding:4px 6px;text-align:right;border-bottom:1px solid var(--line)}
table.t th:first-child,table.t td:first-child{text-align:left}
table.t thead th{background:var(--tint);color:var(--pd);font-size:8.8px;text-transform:uppercase}
.pillx{display:inline-block;padding:1px 6px;border-radius:999px;font-size:8.6px;font-weight:700}
.b-buy{background:#dcfce7;color:#15803d}.b-wait{background:#fee2e2;color:#c0243b}.b-phase{background:#fef3c7;color:#b45309}
.hi{background:var(--tint);border:1px solid var(--p);border-radius:7px;padding:7px 9px;font-size:9.8px;line-height:1.4}
.hi b{color:var(--pd)}
.band2{margin-top:9px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.b2{border:1px solid var(--line);border-top:3px solid var(--pd);border-radius:6px;padding:6px 8px}
.b2 b{font-size:9.4px;color:var(--pd)}.b2 span{display:block;font-size:8.7px;color:var(--mut);margin-top:2px;line-height:1.3}
@media print{html,body{background:#fff}.hint{display:none}.deck{gap:0;padding:0}.slide{box-shadow:none;page-break-after:always}@page{size:1280px 720px;margin:0}}
"""


def build_slides(d, out):
    cfg = d["config"]; port = d["portfolio"]; C = d["commodities"]
    flag = next(n for n, r in C.items() if r["commodity"]["flagship"])
    P = C[flag]; s = P["sense"]; opt = P["optimise"]; ch = opt["chosen"]; sup = P["supply_chain"]
    dist = opt["dist"]

    # slide-2 chart svgs (compact so they fit the slide boxes)
    fr_svg = frontier_scatter(opt["grid"], opt["frontier"], ch, maxw=360)
    dist_svg = dist_chart(dist, maxw=360)

    def acls(a): return "b-buy" if "BUY" in a else ("b-wait" if "WAIT" in a else "b-phase")
    trows = ""
    for n, r in C.items():
        ss, scc, oo, aa = r["sense"], r["score"], r["optimise"], r["act"]
        spl = oo["split"]; tv = r["timing"]["verdict"]
        tcell = "HEDGE" if tv == "HEDGE" else "PHYS"
        tcls = "b-wait" if tv == "HEDGE" else "b-buy"
        trows += (f'<tr><td><b>{n.split("(")[0].strip()}</b></td>'
                  f'<td><span class="pillx {acls(scc["action"])}">{scc["action"]}</span></td>'
                  f'<td>{spl["locked_pct"]:.0f}/{spl["option_pct"]:.0f}/{spl["unhedged_pct"]:.0f}</td>'
                  f'<td>-{oo["risk_cut_pct"]:.0f}%</td>'
                  f'<td><span class="pillx {tcls}">{tcell}</span></td>'
                  f'<td>{"AUTO" if aa["decision"]=="AUTO-EXECUTE" else "ESC."}</td></tr>')

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commodity Copilot - Kearney slides</title><style>{SLIDE_CSS}</style></head><body>
<div class="hint">Two 16:9 slides (Kearney-style). Screenshot each - or Print &#8594; Save as PDF - to drop into PowerPoint.</div>
<div class="deck">

<section class="slide">
 <div class="eyebrow">AI Commodity Copilot &nbsp;&#183;&nbsp; Solution &amp; architecture</div>
 <div class="atitle">An <b>agentic Sense&#8594;Score&#8594;Decide&#8594;Act</b> copilot simulates thousands of price futures,
  picks the buy/hedge mix that is best on <b>cost <i>and</i> stability</b>, and <b>acts inside the council's guardrails</b></div>
 <div class="rule"></div>
 <div class="s1">
  <div class="lcol">
   <div class="box"><h4><span class="dot"></span>How it decides</h4>
    <ol class="sm"><li><b>Sense</b> 6 signals per commodity (price, curve, FX, freight)</li>
    <li><b>Score</b> a 0-100 buy-now signal &#8594; buy / phase / wait</li>
    <li><b>Decide</b> via Monte-Carlo: minimise <b>RALC</b> on the efficient frontier</li>
    <li><b>Act</b> auto-execute in caps, else escalate to the council</li></ol></div>
   <div class="box" style="background:var(--tint)"><h4><span class="dot"></span>The metric (cost + stability)</h4>
    <div class="sm"><b class="p">RALC = E[Cost] + &#955;&#183;SD[Cost]</b></div>
    <div class="xs" style="margin-top:3px">Minimise expected cost <i>plus</i> a penalty on how much it can swing.
     &#955; set by 3 presets: Conservative 1.5 &#183; Balanced 0.8 &#183; Aggressive 0.3. {cfg['n_paths']:,} MC paths.</div></div>
   <div class="box"><h4><span class="dot"></span>Data (this folder)</h4>
    <div class="xs"><b class="p">Prices/curve:</b> palm, crude, silver 1/3/6-mo &#183; <b class="p">FX:</b> USDMYR, USDINR
     &#183; <b class="p">Freight:</b> Baltic Dry &#183; <b class="p">Fundamentals:</b> world supply-demand, UN trade
     &#183; <b class="p">Business:</b> demand, inventory, appetite</div></div>
   <div class="box" style="flex:1"><h4><span class="dot"></span>3 risk-appetite presets (council picks)</h4>
    <table class="t" style="font-size:9.4px"><thead><tr><th>Preset</th><th>&#955;</th><th>Max cover</th><th>Max hedge</th><th>Auto cap</th></tr></thead><tbody>
     <tr><td>Conservative</td><td>1.5</td><td>85%</td><td>80%</td><td>&#8377;60 Cr</td></tr>
     <tr><td>Balanced</td><td>0.8</td><td>60%</td><td>50%</td><td>&#8377;40 Cr</td></tr>
     <tr><td>Aggressive</td><td>0.3</td><td>40%</td><td>30%</td><td>&#8377;20 Cr</td></tr>
    </tbody></table>
    <div class="xs" style="margin-top:3px">One dial sets both the RALC &#955; and the hard caps the autonomy runs inside.</div></div>
  </div>
  <div class="box" style="padding:11px 12px"><h4 style="justify-content:space-between"><span><span class="dot"></span>Architecture - two tracks run through every stage</span>
    <span style="font-weight:600;text-transform:none;font-size:9px"><span class="llab fin" style="padding:1px 4px">FIN</span> financial &nbsp; <span class="llab sc" style="padding:1px 4px">SC</span> supply-chain</span></h4>
   <div class="arch" style="height:452px">
    <div class="stack">
     <div class="layer"><div class="ltag"><b>1 &#183; SENSE</b><span>read inputs</span></div>
      <div class="lanes">
       <div class="lane"><div class="llab fin">FIN</div>
        <div class="ab"><b>Price &amp; curve</b><span>%ile, momentum, contango</span></div>
        <div class="ab"><b>Volatility</b><span>risk</span></div><div class="ab"><b>FX</b><span>USDMYR/INR</span></div>
        <div class="ab"><b>Freight</b><span>Baltic Dry</span></div></div>
       <div class="lane"><div class="llab sc">SC</div>
        <div class="ab sc"><b>Demand</b><span>from sales file</span></div>
        <div class="ab sc"><b>Inventory</b><span>on hand</span></div><div class="ab sc"><b>Lead time</b><span>order&#8594;arrive</span></div>
        <div class="ab sc"><b>Suppliers</b><span>capacity/origins</span></div></div>
      </div></div>
     <div class="arw"><svg viewBox="0 0 16 13" width="15"><path d="M8 0v8M3 6l5 6 5-6" stroke="#7823DC" stroke-width="1.6" fill="none"/></svg></div>
     <div class="layer"><div class="ltag"><b>2 &#183; SCORE</b><span>0-100</span></div>
      <div class="lanes">
       <div class="lane"><div class="llab fin">FIN</div>
        <div class="ab pill"><b>Value</b><span>cheap?</span></div><div class="ab pill"><b>Momentum</b><span>rising?</span></div>
        <div class="ab pill"><b>Curve</b><span>contango?</span></div><div class="ab pill"><b>FX</b><span>&#8377; weaker?</span></div>
        <div class="ab pill"><b>&#8594; Buy-now</b><span>buy/phase/wait</span></div></div>
       <div class="lane"><div class="llab sc">SC</div>
        <div class="ab sc"><b>Demand vol</b><span>CV {sup['demand_cv']*100:.0f}%</span></div>
        <div class="ab sc"><b>Cover</b><span>{sup['months_cover']:.1f} months</span></div>
        <div class="ab sc"><b>Reorder</b><span>{"breached" if sup['below_reorder'] else "ok"}</span></div>
        <div class="ab sc"><b>&#8594; Urgency</b><span>continuity risk</span></div></div>
      </div></div>
     <div class="arw"><svg viewBox="0 0 16 13" width="15"><path d="M8 0v8M3 6l5 6 5-6" stroke="#7823DC" stroke-width="1.6" fill="none"/></svg></div>
     <div class="layer"><div class="ltag"><b>3 &#183; DECIDE</b><span>Monte-Carlo</span></div>
      <div class="lanes">
       <div class="lane"><div class="llab fin">FIN</div>
        <div class="ab dec"><b>Cover %</b><span>lock now</span></div><div class="ab dec"><b>Hedge %</b><span>options/caps</span></div>
        <div class="ab dec"><b>RALC min</b><span>on frontier</span></div><div class="ab dec"><b>Triggers</b><span>price/vol/FX</span></div></div>
       <div class="lane"><div class="llab sc">SC</div>
        <div class="ab sc"><b>Net buy</b><span>{sup['net_procurement']:,.0f} {sup['unit']}</span></div>
        <div class="ab sc"><b>Must-cover</b><span>{sup['must_cover_now']:,.0f} now</span></div>
        <div class="ab sc"><b>Supplier cap</b><span>{sup['supplier_share']*100:.0f}%</span></div>
        <div class="ab sc"><b>Safety stock</b><span>from CV</span></div></div>
      </div></div>
     <div class="arw"><svg viewBox="0 0 16 13" width="15"><path d="M8 0v8M3 6l5 6 5-6" stroke="#7823DC" stroke-width="1.6" fill="none"/></svg></div>
     <div class="layer"><div class="ltag" style="background:var(--p)"><b>4 &#183; ACT</b><span>governed</span></div>
      <div class="lanes">
       <div class="lane"><div class="llab fin">FIN</div>
        <div class="ab" style="border-color:var(--p)"><b>Auto-execute inside caps</b><span>else escalate to council &#183; full audit trail &#183; manual override</span></div></div>
       <div class="lane"><div class="llab sc">SC</div>
        <div class="ab sc"><b>Supply continuity first</b><span>mandatory must-cover buy before price-optimising</span></div></div>
      </div></div>
     <div class="arw"><svg viewBox="0 0 16 13" width="15"><path d="M8 0v8M3 6l5 6 5-6" stroke="#7823DC" stroke-width="1.6" fill="none"/></svg></div>
     <div class="layer"><div class="ltag" style="background:var(--pd)"><b>5 &#183; OUTPUT</b><span>plan</span></div>
      <div class="lanes">
       <div class="lane"><div class="llab fin">FIN</div>
        <div class="ab" style="border-color:var(--pd);background:var(--tint)"><b>Hedge plan + portfolio nets risk &#8594; {port['diversification_benefit_pct']:.0f}% natural hedge</b><span>&#8594; Treasury</span></div></div>
       <div class="lane"><div class="llab sc">SC</div>
        <div class="ab sc"><b>Buy plan: volumes &amp; timing</b><span>&#8594; Procurement</span></div></div>
      </div></div>
    </div>
    <div class="airail"><h4>AI / LLM layer (wraps all)</h4>
     <div class="ai"><b>Sense &mdash; LLM</b><br>reads news/MPOB/USDA &#8594; cited signal, extracts contract/ERP data</div>
     <div class="ai"><b>Decide &mdash; ML</b><br>path probabilities + anomaly alerts</div>
     <div class="ai"><b>Act &mdash; LLM agent</b><br>drafts &amp; executes in caps, writes escalation memo</div>
     <div class="ai"><b>NL Q&amp;A &mdash; LLM</b><br>instant what-if + explanations</div>
     <div class="ai" style="border-color:var(--pd)"><b>Score = rules</b><br>kept auditable; AI never sets the price</div></div>
   </div>
  </div>
 </div>
 <div class="band">
  <div class="bc"><b>Multi-commodity</b><span>palm, crude, silver + FX &amp; freight</span></div>
  <div class="bc"><b>Cost + stability</b><span>RALC on an efficient frontier</span></div>
  <div class="bc"><b>Governed autonomy</b><span>caps, escalation, audit trail, manual override</span></div>
  <div class="bc"><b>Backtested</b><span>steadier cost vs naive on real history</span></div>
 </div>
 <div class="foot"><div class="wm">kearney<span> &nbsp;| AI Commodity Copilot</span></div>
  <div>Source: palm/crude/silver, FX &amp; freight series + world supply-demand / UN trade data in project folder. Illustrative - not financial advice.</div><div>1</div></div>
</section>

<section class="slide">
 <div class="eyebrow">Model in action &nbsp;&#183;&nbsp; live run, {cfg['risk_appetite']} appetite &#183; {cfg['n_paths']:,} Monte-Carlo paths</div>
 <div class="atitle">Across the basket the copilot cuts cost-risk <b>~{opt['risk_cut_pct']:.0f}%</b> at ~equal expected cost,
  and nets a further <b>{port['diversification_benefit_pct']:.0f}%</b> by managing commodities as one portfolio</div>
 <div class="rule"></div>
 <div class="kpis">
  <div class="kpi"><div class="l">Portfolio 6-mo spend</div><div class="v">₹{port['total_spend_cr']:,.0f}<span style="font-size:9px"> Cr</span></div><div class="n">palm + crude + silver</div></div>
  <div class="kpi"><div class="l">Risk if siloed</div><div class="v">₹{port['additive_sd_cr']:,.0f}<span style="font-size:9px"> Cr</span></div><div class="n">risks added up</div></div>
  <div class="kpi"><div class="l">Risk if netted</div><div class="v">₹{port['portfolio_sd_cr']:,.0f}<span style="font-size:9px"> Cr</span></div><div class="n">-{port['diversification_benefit_pct']:.0f}% natural hedge</div></div>
  <div class="kpi"><div class="l">Flagship risk cut</div><div class="v">-{opt['risk_cut_pct']:.0f}%</div><div class="n">palm, vs do-nothing</div></div>
  <div class="kpi"><div class="l">Worst-case trimmed</div><div class="v">₹{dist['naive_car95']-dist['engine_car95']:,.0f}<span style="font-size:9px"> Cr</span></div><div class="n">CaR95: {dist['naive_car95']:,.0f}&#8594;{dist['engine_car95']:,.0f}</div></div>
 </div>
 <div class="s2">
  <div class="col">
   <div class="box"><h4><span class="dot"></span>Per-commodity decisions (the whole basket)</h4>
    <table class="t"><thead><tr><th>Commodity</th><th>Buy-now</th><th>Lock/Opt/Float</th><th>Risk cut</th><th>Timing</th><th>Act</th></tr></thead><tbody>{trows}</tbody></table>
    <div class="xs" style="margin-top:4px"><b class="p">Timing</b> = a DP schedules buys on the forward path incl. <b>{P['timing']['holding_monthly_pct']:.2f}%/mo holding cost</b> &amp; {P['timing']['lead_weeks']}-wk lead, then compares best physical (buy-&amp;-hold) vs hedge and picks the cheaper. <b>Lock/Opt/Float</b> adds to 100% (not "60+50").</div></div>
   <div class="box" style="flex:1"><h4><span class="dot"></span>Decide - efficient frontier (palm)</h4>
    <div style="text-align:center">{fr_svg}</div>
    <div class="xs">Each dot = a cover&#215;hedge strategy. Engine picks the frontier point matching the appetite's &#955;; do-nothing (red) is dominated.</div></div>
  </div>
  <div class="col">
   <div class="box"><h4><span class="dot"></span>The pay-off distribution (palm, 20k futures)</h4>
    <div style="text-align:center">{dist_svg}</div>
    <div class="xs">Do-nothing has a long expensive tail; the engine plan trims the worst case with about the same expected cost.</div></div>
   <div class="hi"><b>Read it as insurance, not a bet.</b> Expected cost is ~unchanged
    (₹{dist['naive_E']:,.0f} &#8594; ₹{dist['engine_E']:,.0f} Cr) but the 95%-worst-case cost falls
    <b>₹{dist['naive_car95']-dist['engine_car95']:,.0f} Cr</b>. On real history the cost line was
    <b>{P['backtest']['vol_reduction_pct']:.0f}% steadier</b> than naive buying.</div>
   <div class="box" style="flex:1"><h4><span class="dot"></span>Supply chain &amp; governance</h4>
    <div class="xs"><b class="p">Supply first:</b> nets inventory ({P['supply_chain']['horizon_demand']:,.0f}&#8594;{P['supply_chain']['net_procurement']:,.0f} {s['unit']} to buy),
     and below the reorder point forces a mandatory <b>{P['supply_chain']['must_cover_now']:,.0f} {s['unit']}</b> buy for continuity <i>before</i> price-optimising.
     <b class="p">Council</b> sets the preset (&#955; + caps); copilot auto-executes inside caps, escalates the rest
     (palm ₹{P['act']['immediate_order_value_cr']:.0f} Cr &gt; ₹{P['act']['auto_execute_cap_cr']} Cr cap &#8594; escalate). Full audit trail; manual override always on.</div></div>
  </div>
 </div>
 <div class="band2">
  <div class="b2"><b>Cadence</b><span>weekly re-solve + real-time trigger alerts</span></div>
  <div class="b2"><b>Decision rights</b><span>auto in caps; council/CFO for the rest</span></div>
  <div class="b2"><b>Proof</b><span>backtest: steadier cost vs naive, ~equal price</span></div>
  <div class="b2"><b>Scale-up</b><span>1 commodity &#8594; basket &#8594; full portfolio autonomy</span></div>
 </div>
 <div class="foot"><div class="wm">kearney<span> &nbsp;| AI Commodity Copilot</span></div>
  <div>Live model output (24-25 Jul snapshot). Figures illustrative - not financial advice.</div><div>2</div></div>
</section>
</div></body></html>"""
    with open(out, "w") as fh:
        fh.write(html)


# ===========================================================================
def main():
    d = json.load(open("copilot_results.json"))
    # load the flagship price series for the line chart
    palm = cc.load_series(cc.COMMODITIES["Palm oil (CPO)"]["spot"]).tail(252)
    palm_series = ([dt.strftime("%Y-%m-%d") for dt in palm.index],
                   [round(float(v), 1) for v in palm.values])
    build_explainer(d, palm_series, "copilot_model_explained.html")
    build_slides(d, "copilot_slides.html")
    print("Built -> copilot_model_explained.html  and  copilot_slides.html")


if __name__ == "__main__":
    main()
