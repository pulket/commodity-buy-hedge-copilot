"""
Builds copilot_audit.html - a COMPLETE audit document for the Commodity Copilot.

Goal: a reader who knows nothing about finance can trace EVERY number in the model
back to the raw data. Every abbreviation is defined, every formula is written out,
and every calculation shows: formula -> plug in the numbers -> result.

Run commodity_copilot.py first (it writes copilot_results.json), then run this.
"""
import json
import numpy as np
import commodity_copilot as cc

PURPLE, PURPLE_D = "#7823DC", "#4C1D95"
INK, MUTE, LINE = "#20222B", "#5b6270", "#e4e2ec"
GREEN, RED = "#15803D", "#C0243B"


# ---------------------------------------------------------------------------
# 1. RE-COMPUTE every intermediate number (so we can SHOW the arithmetic)
# ---------------------------------------------------------------------------
def compute_audit():
    cc.load_fx()
    d = json.load(open("copilot_results.json"))
    c = cc.COMMODITIES["Palm oil (CPO)"]
    spot_s = cc.load_series(c["spot"]); f3_s = cc.load_series(c["f3"]); f6_s = cc.load_series(c["f6"])
    spot, f3, f6 = float(spot_s.iloc[-1]), float(f3_s.iloc[-1]), float(f6_s.iloc[-1])

    # -- price percentile --
    win = spot_s.tail(252); n_le = int((win <= spot).sum()); n_tot = len(win)
    pctile = 100 * n_le / n_tot

    # -- momentum (spot now vs 22 rows back) --
    spot_prev = float(spot_s.iloc[-22]); mom = (spot / spot_prev - 1) * 100

    # -- volatility (std of last 60 daily log-returns, annualised) --
    ret = np.log(spot_s / spot_s.shift(1)).dropna()
    sd_daily = float(ret.tail(60).std()); vol = sd_daily * np.sqrt(252) * 100

    # -- forward curve --
    curve = (f6 / spot - 1) * 100

    # -- FX + freight --
    usdmyr, usdinr = cc.FX["usdmyr"], cc.FX["usdinr"]
    usdinr_mom = cc.FX["usdinr_mom"]
    bdiy = cc.load_series("Priya_BDIY_Line Chart.xlsx")
    bdiy_now = float(bdiy.iloc[-1]); bdiy_avg = float(bdiy.tail(252).mean())
    freight = 35.0 * bdiy_now / bdiy_avg

    # -- landed cost (step by step) --
    usd_fob = spot / usdmyr
    usd_cif = usd_fob + freight
    inr_cif = usd_cif * usdinr
    landed = inr_cif * 1.275

    # -- buy-now sub-scores --
    def clamp(x): return max(0, min(100, x))
    value = 100 - pctile
    mom_s = clamp(50 + mom * 10)
    curve_s = clamp(50 + curve * 10)
    fx_s = clamp(50 + usdinr_mom * 10)
    w = {"value": .35, "momentum": .20, "curve": .25, "fx": .20}
    blend = w["value"] * value + w["momentum"] * mom_s + w["curve"] * curve_s + w["fx"] * fx_s

    # -- supply chain: demand, inventory, net procurement (re-computed to show maths) --
    # use the SAME real-sales demand the model uses, so audit numbers match exactly
    sales = cc.demand_from_sales()
    c["annual_demand"] = sales["annual_demand"]
    c["demand_cv"] = sales["demand_cv"]
    sc = cc.supply_chain(c)

    # -- Monte-Carlo / strategy parameters (volumes = NET procurement) --
    H = cc.HORIZON_M; T = H / 12.0; sigma = vol / 100.0
    monthly = sc["monthly_proc"]; total = sc["net_procurement"]
    strip_native = (spot + f6) / 2.0
    lock_fob = strip_native / usdmyr; lock_cif = lock_fob + freight
    lock_landed = lock_cif * usdinr * 1.275
    premium = 0.4 * lock_landed * sigma * np.sqrt(T)

    # -- chosen strategy + naive from JSON --
    P = d["commodities"]["Palm oil (CPO)"]
    opt = P["optimise"]
    ch = opt["chosen"]; split = opt["split"]; caps = opt["caps"]; act = P["act"]
    naive = next(g for g in opt["grid"] if g["cover"] == 0 and g["hedge"] == 0)
    lam = d["config"]["preset"]["lambda"]

    return {"d": d, "spot": spot, "f3": f3, "f6": f6, "spot_prev": spot_prev,
            "n_le": n_le, "n_tot": n_tot, "pctile": pctile, "mom": mom,
            "sd_daily": sd_daily, "vol": vol, "curve": curve,
            "usdmyr": usdmyr, "usdinr": usdinr, "usdinr_mom": usdinr_mom,
            "bdiy_now": bdiy_now, "bdiy_avg": bdiy_avg, "freight": freight,
            "usd_fob": usd_fob, "usd_cif": usd_cif, "inr_cif": inr_cif, "landed": landed,
            "value": value, "mom_s": mom_s, "curve_s": curve_s, "fx_s": fx_s, "w": w, "blend": blend,
            "H": H, "T": T, "sigma": sigma, "monthly": monthly, "total": total,
            "strip_native": strip_native, "lock_landed": lock_landed, "premium": premium,
            "chosen": ch, "naive": naive, "lam": lam, "opt": opt,
            "sc": sc, "split": split, "caps": caps, "act": act, "unit": c["unit"], "sales": sales,
            "timing": P["timing"],
            "spot_dates": (spot_s.index[-1].strftime("%Y-%m-%d"),
                           spot_s.index[-22].strftime("%Y-%m-%d"))}


# ---------------------------------------------------------------------------
# 2. small HTML helpers
# ---------------------------------------------------------------------------
def calc(formula, steps, result, note=""):
    s = "".join(f'<div class="s">{x}</div>' for x in steps)
    nt = f'<div class="note">{note}</div>' if note else ""
    return (f'<div class="calc"><div class="f">{formula}</div>{s}'
            f'<div class="r">= {result}</div>{nt}</div>')


def cr(x):  # INR -> crore string
    return f"₹{x/1e7:,.1f} Cr"


# ---------------------------------------------------------------------------
# 3. build the document
# ---------------------------------------------------------------------------
def build(a):
    d = a["d"]; C = d["commodities"]; port = d["portfolio"]; cfg = d["config"]
    ch, naive = a["chosen"], a["naive"]

    # ---- abbreviations table ----
    abbr = [
        ("CPO", "Crude Palm Oil - the commodity in the worked example."),
        ("MYR", "Malaysian Ringgit - the currency palm oil is priced in."),
        ("USD", "US Dollar."), ("INR", "Indian Rupee - the buyer's home currency."),
        ("FX", "Foreign Exchange - i.e. currency conversion rates."),
        ("USDMYR", "How many Ringgit one US Dollar buys (e.g. 4.089)."),
        ("USDINR", "How many Rupees one US Dollar buys (e.g. 96.57)."),
        ("BDIY", "Baltic Dry Index - a global measure of ocean shipping (freight) cost."),
        ("FOB", "Free On Board - the price of the goods before shipping is added."),
        ("CIF", "Cost, Insurance &amp; Freight - the price after adding shipping."),
        ("t / bbl / oz", "tonne / barrel / (troy) ounce - the unit each commodity is sold in."),
        ("Cr", "Crore = 10,000,000 (1 crore = ₹1 followed by 7 zeros)."),
        ("%ile / percentile", "Where today's price ranks out of the last 252 days (0 = cheapest, 100 = dearest)."),
        ("SMA", "Simple Moving Average - the average price over the last N days."),
        ("Spot", "The price for buying right now (we use the nearest futures contract)."),
        ("Forward / Futures", "An agreed price today to buy on a future date."),
        ("Forward curve", "Spot vs 3-month vs 6-month prices lined up together."),
        ("Contango", "Forward price is ABOVE spot - it costs extra to lock in (positive carry)."),
        ("Backwardation", "Forward price is BELOW spot - you are effectively paid to lock in."),
        ("Volatility", "How much the price jumps around, expressed as a yearly %. Higher = riskier."),
        ("Momentum", "The recent direction of the price (last ~1 month), as a %."),
        ("Hedge", "A financial contract that protects you from price moves."),
        ("Cover", "Buying part of your future demand now via a physical forward (locks the price)."),
        ("Option / Call / Cap", "Pay a small fee (premium) to cap the price if it rises, but keep the gain if it falls."),
        ("Premium", "The fee you pay for an option."),
        ("Strike", "The capped price level set in an option."),
        ("Floating", "Volume left un-locked - you pay whatever the price is each month."),
        ("Net procurement", "What we actually buy = demand for the period minus the inventory we can use."),
        ("Safety stock", "A minimum buffer of inventory we always keep, in case of surprises."),
        ("Reorder point (ROP)", "Inventory level that triggers a mandatory reorder = lead-time demand + safety stock."),
        ("Must-cover", "The immediate, buy-regardless-of-price quantity to get back above the reorder point."),
        ("Lead time", "Time from placing an order to the goods arriving (order -> ship -> arrive)."),
        ("Lock/Opt/Float", "The 100% split: % locked (forwards) / option-hedged / left floating."),
        ("Holding cost", "The cost of keeping inventory (finance + storage + insurance), e.g. ~1.25% per month."),
        ("Carry", "The extra cost baked into a forward price vs today's spot (positive in contango)."),
        ("Just-in-time (JIT)", "Buying only when needed (ordering exactly one lead-time ahead) to avoid holding cost."),
        ("Dynamic program (DP)", "A method that finds the cheapest schedule by solving small sub-problems in order."),
        ("Wagner-Whitin", "The classic lot-sizing DP that decides which weeks to buy to minimise price + holding cost."),
        ("MC / Monte-Carlo", "Running thousands of random 'what-if' price futures to see the range of outcomes."),
        ("GBM", "Geometric Brownian Motion - the standard maths for a random price path."),
        ("E[Cost] / Expected cost", "The average total cost across all the simulated futures."),
        ("SD / Std dev", "Standard Deviation - a number for how spread-out / uncertain the cost is."),
        ("CaR95", "Cost-at-Risk (95%) - a bad-case cost: only 5% of futures are worse than this."),
        ("λ (lambda)", "Risk-aversion dial: how much we punish uncertainty vs chasing the lowest cost."),
        ("RALC", "Risk-Adjusted Landed Cost = E[Cost] + λ × SD[Cost]. The engine minimises this."),
        ("Correlation", "-1 to +1: do two prices move together (+) or opposite (-) or unrelated (0)?"),
        ("Diversification", "Because prices don't all move together, combined risk is less than the sum."),
        ("Guardrail / Cap", "A hard limit the auto-trading must stay inside."),
        ("MPOB / USDA", "Malaysian Palm Oil Board / US Dept. of Agriculture - official supply-demand reports."),
    ]
    abbr_rows = "".join(f'<tr><td><b>{k}</b></td><td>{v}</td></tr>' for k, v in abbr)

    # ---- frontier grid table (audit of the DECIDE step) ----
    grid = sorted(a["opt"]["grid"], key=lambda g: g["ralc"])
    grows = ""
    for g in grid:
        is_ch = (g["cover"] == ch["cover"] and g["hedge"] == ch["hedge"])
        is_nv = (g["cover"] == 0 and g["hedge"] == 0)
        cls = ' class="pick"' if is_ch else (' class="nv"' if is_nv else "")
        tag = " &#9664; ENGINE PICK (lowest RALC)" if is_ch else (" &#9664; do-nothing" if is_nv else "")
        grows += (f'<tr{cls}><td>{g["cover"]*100:.0f}%</td><td>{g["hedge"]*100:.0f}%</td>'
                  f'<td>{cr(g["E"])}</td><td>{cr(g["sd"])}</td><td>{cr(g["car95"])}</td>'
                  f'<td><b>{cr(g["ralc"])}</b>{tag}</td></tr>')

    # ---- multi-commodity signal table ----
    mrows = ""
    for n, r in C.items():
        s = r["sense"]; o = r["optimise"]; sc = r["score"]
        mrows += (f'<tr><td><b>{n}</b></td><td>{s["spot"]:,.0f} {s["ccy"]}</td>'
                  f'<td>{s["percentile"]:.0f}</td><td>{s["vol"]:.0f}%</td><td>{s["curve"]:+.1f}%</td>'
                  f'<td>{sc["score"]:.0f} &#8594; {sc["action"]}</td>'
                  f'<td>{o["chosen"]["cover"]*100:.0f}% + {o["chosen"]["hedge"]*100:.0f}%</td>'
                  f'<td>{cr(o["chosen"]["E"])}</td><td>{cr(o["chosen"]["sd"])}</td></tr>')

    # ---- portfolio correlation table ----
    names = port["commodities"]
    corr_head = "<tr><td></td>" + "".join(f"<th>{n.split()[0]}</th>" for n in names) + "</tr>"
    corr_body = ""
    for x in names:
        corr_body += f'<tr><th style="text-align:left">{x.split()[0]}</th>' + \
            "".join(f'<td>{port["corr"][x][y]:+.2f}</td>' for y in names) + "</tr>"
    sd_vec = [C[n]["optimise"]["chosen"]["sd"] / 1e7 for n in names]

    # ---- backtest numbers (palm) ----
    bt = C["Palm oil (CPO)"]["backtest"]
    act = C["Palm oil (CPO)"]["act"]

    risk_cut = (1 - ch["sd"] / naive["sd"]) * 100
    ralc_calc = ch["E"] / 1e7 + a["lam"] * ch["sd"] / 1e7

    css = """
    *{box-sizing:border-box}
    body{margin:0;background:#f6f7fb;color:#20222b;font:15px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
    .wrap{max-width:900px;margin:0 auto;padding:26px 22px 90px}
    h1{font-size:27px;margin:0 0 4px}
    h2{font-size:20px;margin:36px 0 10px;padding:10px 0 0;border-top:3px solid #7823dc;color:#4c1d95}
    h3{font-size:16px;margin:20px 0 6px;color:#7823dc}
    .sub{color:#5b6270;margin:0 0 14px}
    .toc{background:#fff;border:1px solid #e4e2ec;border-radius:10px;padding:14px 18px;margin:14px 0}
    .toc a{color:#4c1d95;text-decoration:none;font-size:14px;display:block;margin:3px 0}
    .toc a:hover{text-decoration:underline}
    .card{background:#fff;border:1px solid #e4e2ec;border-radius:10px;padding:14px 18px;margin:12px 0}
    table{border-collapse:collapse;width:100%;font-size:13.5px;margin:8px 0}
    th,td{padding:7px 9px;text-align:right;border-bottom:1px solid #eef0f4;vertical-align:top}
    th:first-child,td:first-child{text-align:left}
    thead th{background:#f5eefd;color:#4c1d95;font-size:12px;text-transform:uppercase;letter-spacing:.02em}
    .abbr td{text-align:left}.abbr td:first-child{white-space:nowrap;color:#4c1d95;font-weight:700;width:120px}
    tr.pick{background:#eafaf0}tr.pick td{border-color:#c8ecd4}
    tr.nv{background:#fdecef}
    .calc{background:#faf7ff;border:1px solid #e4d3fb;border-left:4px solid #7823dc;border-radius:8px;padding:10px 14px;margin:10px 0;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}
    .calc .f{color:#4c1d95;font-weight:700;margin-bottom:3px}
    .calc .s{color:#20222b;margin:2px 0}
    .calc .r{color:#15803d;font-weight:700;margin-top:4px;font-size:14px}
    .calc .note{color:#5b6270;font-family:-apple-system,sans-serif;font-size:12.5px;margin-top:6px}
    .kv{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
    .kv div{background:#fff;border:1px solid #e4e2ec;border-radius:8px;padding:8px 11px;font-size:13.5px}
    .kv b{color:#4c1d95}
    .callout{background:#f5eefd;border:1px solid #d8b8fb;border-radius:9px;padding:11px 15px;margin:12px 0}
    .warn{background:#fff7ed;border:1px solid #fed7aa;border-radius:9px;padding:11px 15px;margin:12px 0}
    code{background:#f0edf7;padding:1px 5px;border-radius:4px;font-size:12.5px}
    .muted{color:#5b6270}
    .foot{color:#5b6270;font-size:12px;margin-top:30px;text-align:center;border-top:1px solid #e4e2ec;padding-top:12px}
    b.p{color:#4c1d95}
    """

    def toc(i, t): return f'<a href="#s{i}">{i}. {t}</a>'

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commodity Copilot - Full Audit Document</title><style>{css}</style></head><body><div class="wrap">

<h1>Commodity Copilot &mdash; Full Audit Document</h1>
<p class="sub">Every number in the model, traced back to the raw data. Written for a reader who
knows nothing about finance: every abbreviation is defined, every formula is written out, and every
calculation shows <b>formula &#8594; plug in the numbers &#8594; result</b>. Worked example =
<b>Palm oil (CPO)</b>; the same method is applied to crude &amp; silver.</p>

<div class="toc">
{toc(1,"How to read this document")}
{toc(2,"Dictionary of every abbreviation &amp; term")}
{toc(3,"The raw data (where every number starts)")}
{toc(4,"Landed cost &mdash; the price that hits the P&amp;L")}
{toc(5,"Supply chain &mdash; from demand to how much we ACTUALLY buy")}
{toc(6,"The 6 market signals (each calculated)")}
{toc(7,"The Buy-Now Score (each sub-score + the blend)")}
{toc(8,"Monte-Carlo &mdash; simulating 20,000 price futures")}
{toc(9,"The cost of a strategy (the formula)")}
{toc(10,"RALC &amp; the frontier &mdash; and why '60% + 50%' is really a 100% split")}
{toc(11,"Risk numbers: E, SD, CaR95, risk-cut")}
{toc(12,"Act &mdash; the guardrail (auto-execute vs escalate) check")}
{toc(13,"Backtest &mdash; checking it on real history")}
{toc(14,"Portfolio &mdash; correlation &amp; the natural-hedge benefit")}
{toc(15,"Where exactly the AI / LLM is used (and where it is NOT)")}
{toc(16,"Every assumption we made (register)")}
</div>

<h2 id="s1">1. How to read this document</h2>
<div class="card">
<p>The model works in four stages: <b class="p">SENSE</b> (read the market) &#8594;
<b class="p">SCORE</b> (rate it 0&ndash;100) &#8594; <b class="p">DECIDE</b> (simulate and choose the
best buy/hedge mix) &#8594; <b class="p">ACT</b> (execute inside limits). This document goes through
each stage and shows the maths.</p>
<p>Whenever you see a purple box like the one below, it is a real calculation you can check yourself:</p>
{calc("example = a &times; b", ["= 2 &times; 3"], "6", "The green line is the answer.")}
<p>All prices are the <b>latest available</b> in the data files (snapshot: {a['spot_dates'][0]}).</p>
</div>

<h2 id="s2">2. Dictionary of every abbreviation &amp; term</h2>
<p class="muted">Read this once; the rest of the document will make sense. Nothing below assumes you already know it.</p>
<div class="card"><table class="abbr"><tbody>{abbr_rows}</tbody></table></div>

<h2 id="s3">3. The raw data (where every number starts)</h2>
<p>Everything is computed from the Excel files in this folder. Each file is a daily price history
(newest row = today). For palm oil we use three of them &mdash; the price for buying now, in 3 months,
and in 6 months:</p>
<div class="kv">
 <div><b>Spot (KO1, buy now)</b><br>{a['spot']:,.0f} MYR / tonne</div>
 <div><b>3-month forward (KO3)</b><br>{a['f3']:,.0f} MYR / tonne</div>
 <div><b>6-month forward (KO6)</b><br>{a['f6']:,.0f} MYR / tonne</div>
 <div><b>USDMYR (FX)</b><br>{a['usdmyr']:.4f} Ringgit per $</div>
 <div><b>USDINR (FX)</b><br>{a['usdinr']:.2f} Rupees per $</div>
 <div><b>Baltic Dry Index (freight)</b><br>{a['bdiy_now']:,.0f} (today)</div>
</div>
<p class="muted">Business inputs: annual demand <b>{a['sales']['annual_demand']:,.0f} units</b> and its volatility
<b>CV {a['sales']['demand_cv']*100:.0f}%</b> come from the company's real sales file (Section 5); inventory
15,000, lead time 1.5 months, planning horizon 6 months are the remaining assumptions (Section 16).</p>

<h2 id="s4">4. Landed cost &mdash; the price that actually hits the P&amp;L</h2>
<p>Palm is priced in Ringgit (MYR) in Malaysia, but we pay in Rupees (INR) in India, and we must add
shipping and import duty. "Landed cost" is the all-in Rupee cost per tonne once it reaches us. Four steps:</p>
<h3>Step 4a &mdash; freight (shipping) cost today</h3>
{calc("freight = base &times; (BDIY today &divide; BDIY 1-yr average)",
      [f"= $35 &times; ({a['bdiy_now']:,.0f} &divide; {a['bdiy_avg']:,.0f})",
       f"= $35 &times; {a['bdiy_now']/a['bdiy_avg']:.3f}"],
      f"${a['freight']:,.1f} per tonne",
      "We assume a typical Malaysia&#8594;India rate of $35/t and scale it by how high freight is today vs its 1-year average.")}
<h3>Step 4b &mdash; convert the Ringgit price to Dollars (FOB)</h3>
{calc("USD price = MYR price &divide; USDMYR",
      [f"= {a['spot']:,.0f} &divide; {a['usdmyr']:.4f}"],
      f"${a['usd_fob']:,.1f} per tonne")}
<h3>Step 4c &mdash; add freight, then convert Dollars to Rupees (CIF)</h3>
{calc("INR price = (USD price + freight) &times; USDINR",
      [f"= (${a['usd_fob']:,.1f} + ${a['freight']:,.1f}) &times; {a['usdinr']:.2f}",
       f"= ${a['usd_cif']:,.1f} &times; {a['usdinr']:.2f}"],
      f"₹{a['inr_cif']:,.0f} per tonne")}
<h3>Step 4d &mdash; add India import duty (27.5%)</h3>
{calc("landed cost = INR price &times; (1 + duty)",
      [f"= ₹{a['inr_cif']:,.0f} &times; 1.275"],
      f"₹{a['landed']:,.0f} per tonne",
      "This ₹{:,.0f}/tonne is the number every rupee figure later in the model is built on.".format(a['landed']))}

<h2 id="s5">5. Supply chain &mdash; from demand to how much we ACTUALLY buy</h2>
<p>Before any price optimisation, the engine turns <b>demand, inventory, lead time and supplier limits</b>
into the real volume to source. The <b>demand and its month-to-month volatility are read from the company's
real sales file</b> ({a['sales']['n_months']} full months) &mdash; not assumed:</p>
{calc("demand &amp; volatility (from the real sales file)",
      [f"annual demand = {a['sales']['annual_demand']:,.0f} units/yr (run-rate from monthly sales)",
       f"demand volatility = CV {a['sales']['demand_cv']*100:.0f}% (std &divide; mean of monthly units)"],
      f"{a['sc']['monthly']:,.0f} / month",
      "Earlier these were guessed; now they come straight from actual sales history.")}
{calc("net procurement = 6-month demand &minus; usable inventory",
      [f"6-month demand = {a['sales']['annual_demand']:,.0f} &divide; 12 &times; 6 = {a['sc']['horizon_demand']:,.0f} t",
       f"usable inventory = inventory &minus; safety = {a['sc']['inventory']:,.0f} &minus; {a['sc']['safety_stock']:,.0f} = {a['sc']['usable_inventory']:,.0f} t",
       f"net = {a['sc']['horizon_demand']:,.0f} &minus; {a['sc']['usable_inventory']:,.0f}"],
      f"{a['sc']['net_procurement']:,.0f} tonnes",
      "This NET number - not the full demand - is what every rupee figure in Sections 9-11 is built on. "
      "What we already hold reduces what we buy.")}
{calc("safety stock = 1.65 &times; demand-CV &times; monthly &times; &radic;(lead time)",
      [f"= 1.65 &times; {a['sales']['demand_cv']:.2f} &times; {a['sc']['monthly']:,.0f} &times; &radic;{a['sc']['lead_m']}",
       f"= 1.65 &times; {a['sales']['demand_cv']:.2f} &times; {a['sc']['monthly']:,.0f} &times; {a['sc']['lead_m']**0.5:.2f}"],
      f"{a['sc']['safety_stock']:,.0f} tonnes",
      "The buffer is sized from the REAL demand volatility (1.65 = 95% service level). More volatile sales "
      "-> bigger safety stock. This is where the sales data directly changes the plan.")}
{calc("reorder point = lead-time demand + safety stock",
      [f"lead-time demand = {a['sc']['lead_m']} months &times; {a['sc']['monthly']:,.0f} t/mo = {a['sc']['lead_m']*a['sc']['monthly']:,.0f} t",
       f"+ safety stock = {a['sc']['safety_stock']:,.0f} t"],
      f"{a['sc']['reorder_point']:,.0f} tonnes",
      "If inventory falls below this, we must reorder to protect supply.")}
{calc("must-cover now = reorder point &minus; current inventory",
      [f"= {a['sc']['reorder_point']:,.0f} &minus; {a['sc']['inventory']:,.0f}"],
      f"{a['sc']['must_cover_now']:,.0f} tonnes (mandatory, buy regardless of price)",
      "Current inventory {:,.0f} t = {:.1f} months of cover, which is BELOW the reorder point - so the engine "
      "forces this buy first, for supply continuity, before optimising for price.".format(a['sc']['inventory'], a['sc']['months_cover']))}
<div class="callout"><b>Supplier limit:</b> our {a['sc']['n_suppliers']} suppliers ({a['sc']['origins']}) can
forward-commit at most <b>{a['sc']['supplier_share']*100:.0f}%</b> of demand. That becomes a hard cap on how much
we can physically lock (used in Section 10).</div>

<h2 id="s6">6. The 6 market signals (each one calculated)</h2>
<p>The engine reads the market as six simple numbers. Here is exactly how each is computed for palm.</p>

<h3>5a &mdash; Price percentile (is it cheap or dear?)</h3>
{calc("percentile = (days in last 252 with price &le; today) &divide; 252 &times; 100",
      [f"= {a['n_le']} &divide; {a['n_tot']} &times; 100"],
      f"{a['pctile']:.0f} out of 100",
      "0 = cheapest in a year, 100 = dearest. {:.0f} means palm is very expensive right now.".format(a['pctile']))}

<h3>5b &mdash; Momentum (which way is it moving?)</h3>
{calc("momentum = (price today &divide; price ~1 month ago &minus; 1) &times; 100",
      [f"= ({a['spot']:,.0f} &divide; {a['spot_prev']:,.0f} &minus; 1) &times; 100"],
      f"{a['mom']:+.1f}%",
      f"Today ({a['spot_dates'][0]}) vs 22 trading days earlier ({a['spot_dates'][1]}). Positive = rising.")}

<h3>5c &mdash; Volatility (how jumpy / risky?)</h3>
{calc("volatility = (std-dev of last 60 daily returns) &times; &radic;252 &times; 100",
      [f"= {a['sd_daily']:.4f} &times; {np.sqrt(252):.2f} &times; 100"],
      f"{a['vol']:.0f}% per year",
      "A 'daily return' is the % change from one day to the next. Std-dev measures how spread out those are; "
      "&radic;252 scales one day up to a year (252 trading days). 17% is moderate.")}

<h3>5d &mdash; Forward curve (contango or backwardation?)</h3>
{calc("curve = (6-month price &divide; spot &minus; 1) &times; 100",
      [f"= ({a['f6']:,.0f} &divide; {a['spot']:,.0f} &minus; 1) &times; 100"],
      f"{a['curve']:+.1f}%",
      "Positive = contango (locking costs extra). Negative = backwardation (you get paid to lock).")}

<h3>5e &mdash; Rupee momentum (are imports getting dearer?)</h3>
{calc("rupee momentum = (USDINR today &divide; USDINR ~1 month ago &minus; 1) &times; 100",
      [f"= {a['usdinr_mom']:+.2f}% (from the USDINR file)"],
      f"{a['usdinr_mom']:+.1f}%",
      "Positive = the rupee is weakening, so imports cost more.")}

<h3>5f &mdash; Landed cost</h3>
<p>Already computed in Section 4: <b>₹{a['landed']:,.0f}/tonne</b>.</p>

<h2 id="s7">7. The Buy-Now Score (each sub-score, then the blend)</h2>
<p>Each signal becomes a 0&ndash;100 sub-score (50 = neutral). Then we blend them with weights that add
up to 100%. Above 60 = buy now, 45&ndash;60 = phase in, below 45 = wait.</p>
{calc("Value sub-score = 100 &minus; percentile",
      [f"= 100 &minus; {a['pctile']:.0f}"], f"{a['value']:.0f}", "Cheaper price &#8594; higher score. Palm is dear, so this is low.")}
{calc("Momentum sub-score = 50 + momentum &times; 10 (capped 0&ndash;100)",
      [f"= 50 + ({a['mom']:.1f}) &times; 10"], f"{a['mom_s']:.0f}")}
{calc("Curve sub-score = 50 + curve &times; 10 (capped)",
      [f"= 50 + ({a['curve']:.1f}) &times; 10"], f"{a['curve_s']:.0f}")}
{calc("FX sub-score = 50 + rupee-momentum &times; 10 (capped)",
      [f"= 50 + ({a['usdinr_mom']:.1f}) &times; 10"], f"{a['fx_s']:.0f}")}
{calc("Buy-Now = 0.35&times;Value + 0.20&times;Momentum + 0.25&times;Curve + 0.20&times;FX",
      [f"= 0.35&times;{a['value']:.0f} + 0.20&times;{a['mom_s']:.0f} + 0.25&times;{a['curve_s']:.0f} + 0.20&times;{a['fx_s']:.0f}",
       f"= {a['w']['value']*a['value']:.1f} + {a['w']['momentum']*a['mom_s']:.1f} + {a['w']['curve']*a['curve_s']:.1f} + {a['w']['fx']*a['fx_s']:.1f}"],
      f"{a['blend']:.0f} / 100 &#8594; PHASE IN",
      "The weights (35/20/25/20) are our chosen importance for each signal - listed in Section 16.")}

<h2 id="s8">8. Monte-Carlo &mdash; simulating 20,000 possible price futures</h2>
<p>We cannot know tomorrow's price, so instead of guessing one number we simulate <b>{cfg['n_paths']:,}</b>
random but realistic price paths for the next 6 months, and look at the whole range of outcomes. Each
path is built one month at a time with this standard formula (GBM):</p>
{calc("next price = this price &times; e^( (&minus;&frac12;&sigma;&sup2;)&middot;dt + &sigma;&middot;&radic;dt &middot; Z )",
      [f"&sigma; (volatility) = {a['sigma']:.3f}",
       f"dt (one month) = 1/12 = {1/12:.3f}",
       "Z = a random draw from a normal 'bell curve' (different each step)"],
      "one simulated month",
      "The &minus;&frac12;&sigma;&sup2; term keeps the AVERAGE future price equal to today's price "
      "(we do not assume we can predict the direction - a deliberate, conservative choice). "
      "Z is what makes each of the 20,000 paths different.")}
<p class="muted">Doing this 6 times gives one 6-month path; doing that 20,000 times gives the full
range of what the price could do.</p>

<h2 id="s9">9. The cost of a strategy (the formula behind every rupee number)</h2>
<p>A "strategy" = two dials: <b>cover</b> (% of the net requirement locked now via forwards) and <b>hedge</b>
(% of the rest protected with options). Volumes are the <b>net procurement</b> from Section 5 &mdash; what we
actually buy after netting off inventory. For each simulated price path we add up the total cost like this:</p>
<div class="kv">
 <div><b>Net to procure (Section 5)</b><br>{a['total']:,.0f} t over 6 months</div>
 <div><b>Per month</b><br>{a['total']:,.0f} &divide; 6 = {a['monthly']:,.0f} t/month</div>
</div>
{calc("Forward lock price = landed cost of the average of spot &amp; 6-month price",
      [f"average price = ({a['spot']:,.0f} + {a['f6']:,.0f}) &divide; 2 = {a['strip_native']:,.0f} MYR",
       "&#8594; run through the same landed-cost steps as Section 4"],
      f"₹{a['lock_landed']:,.0f} per tonne",
      "This is what you pay for the COVERED volume. It is slightly above today's landed cost because palm is in contango.")}
{calc("Option premium (fee) = 0.4 &times; lock price &times; volatility &times; &radic;(0.5 year)",
      [f"= 0.4 &times; ₹{a['lock_landed']:,.0f} &times; {a['sigma']:.2f} &times; {np.sqrt(a['T']):.3f}"],
      f"₹{a['premium']:,.0f} per tonne",
      "The fee you pay for an option that caps the price. ~0.4&times;&sigma;&times;&radic;T is a standard rule-of-thumb for an at-the-money option.")}
<p>Then, on every path, each tonne costs:</p>
<div class="card"><ul>
 <li><b>Covered/locked tonnes</b>: fixed at the lock price above &mdash; no surprises.</li>
 <li><b>Option-hedged tonnes</b>: the lower of (that month's price) or (the cap), plus the premium.</li>
 <li><b>Un-hedged tonnes</b>: whatever that month's simulated price is.</li>
</ul>
<p class="muted">Add these across all 6 months and all tonnes = the total cost for that one path. Repeat for
20,000 paths &#8594; a full distribution of possible total costs.</p></div>

<h2 id="s10">10. RALC &amp; the frontier &mdash; and why "60% + 50%" is really a 100% split</h2>
<p>You asked for a decision that balances <b>cost</b> and <b>stability</b>. From the 20,000 paths, each
strategy gives an average cost <b>E</b> and a spread <b>SD</b>. We score each with one number:</p>
{calc("RALC = E[Cost] + &lambda; &times; SD[Cost]",
      [f"&lambda; = {a['lam']} (the 'balanced' risk setting)",
       f"for the chosen strategy: = {ch['E']/1e7:,.0f} + {a['lam']} &times; {ch['sd']/1e7:,.1f}",
       f"= {ch['E']/1e7:,.0f} + {a['lam']*ch['sd']/1e7:,.1f}"],
      f"{ralc_calc:,.0f} (₹ Cr)",
      "Lower RALC = better. &lambda; decides how much we punish uncertainty: 0.3 aggressive, 0.8 balanced, 1.5 conservative.")}
<p>The engine computes RALC for every allowed cover&times;hedge combination and picks the <b>lowest</b>.
Here is the full table it chose from (this is the complete audit of the DECIDE step):</p>
<table><thead><tr><th>Cover</th><th>Hedge</th><th>E[Cost]</th><th>SD (risk)</th><th>CaR95</th><th>RALC (rank)</th></tr></thead>
<tbody>{grows}</tbody></table>
<p class="muted">The green row is the winner (lowest RALC). The red row is "do-nothing" (buy everything at
spot). Note the engine pick has almost the same expected cost as do-nothing but far less risk &mdash; that is
the whole point.</p>

<h3>Why the winner is 60% &amp; 50% &mdash; and why that is 100%, not 110%</h3>
<div class="warn"><b>Common confusion:</b> "cover 60% + hedge 50%" looks like 110%. It is NOT, because the two
percentages are on <b>different bases</b>: cover is a % of the <i>whole</i> requirement, but hedge is a % of
only the <i>un-locked remainder</i>. Written as one pie they add to exactly 100%:</div>
{calc("Locked = cover",
      [f"= {a['chosen']['cover']*100:.0f}% of the net requirement"],
      f"{a['split']['locked_pct']:.0f}% (physical forwards)")}
{calc("Option-hedged = hedge &times; (1 &minus; cover)",
      [f"= {a['chosen']['hedge']*100:.0f}% &times; (100% &minus; {a['chosen']['cover']*100:.0f}%)",
       f"= {a['chosen']['hedge']*100:.0f}% &times; {(1-a['chosen']['cover'])*100:.0f}%"],
      f"{a['split']['option_pct']:.0f}% (call options / caps)")}
{calc("Un-hedged (floating) = (1 &minus; hedge) &times; (1 &minus; cover)",
      [f"= {(1-a['chosen']['hedge'])*100:.0f}% &times; {(1-a['chosen']['cover'])*100:.0f}%"],
      f"{a['split']['unhedged_pct']:.0f}% (left floating)")}
{calc("TOTAL",
      [f"= {a['split']['locked_pct']:.0f}% + {a['split']['option_pct']:.0f}% + {a['split']['unhedged_pct']:.0f}%"],
      "100% of the net requirement (nothing double-counted)")}
<p><b>Why exactly 60% and 50%?</b> Both are the "balanced" preset's <b>caps</b>. The optimiser wanted to lock
&amp; hedge even more (locking cuts risk), but two guardrails stop it:</p>
<div class="card"><ul>
 <li><b>Cover cap = {a['caps']['cover_cap']*100:.0f}%</b> &mdash; the smaller of the appetite cap
   ({a['caps']['appetite_cover_cap']*100:.0f}%) and what suppliers can forward-commit
   ({a['caps']['supplier_share']*100:.0f}%, from Section 5). You cannot lock more demand than suppliers will sell
   forward, and you do not want to over-commit volume the forecast might not need.</li>
 <li><b>Hedge cap = {a['caps']['hedge_cap']*100:.0f}%</b> &mdash; the appetite's limit on protecting the floating part.</li>
</ul>
<p class="muted">So the numbers are not arbitrary: the RALC optimiser pushed to both caps, and the caps come
straight from the risk preset + supplier capacity. Change the preset (Section 16) and these move.</p></div>

<h3>10b - WHEN to buy: the timing DP &amp; holding cost</h3>
<p>Cover% and hedge% say <b>how much</b>; a separate step decides <b>when</b>. A <b>dynamic program</b>
(Wagner-Whitin) schedules buys on the weekly forward price path, charging a <b>holding cost</b> for anything
bought early and respecting the lead time, then every plan is priced over the 20,000 paths and ranked on RALC.</p>
{calc("holding cost per week = monthly holding &divide; weeks-per-month",
      [f"= {a['timing']['holding_monthly_pct']:.2f}% &divide; 4.33"],
      f"{a['timing']['holding_monthly_pct']/4.33:.3f}% per week",
      "Cost of carrying inventory early = finance + storage + insurance. Lead time = "
      f"{a['timing']['lead_weeks']} weeks.")}
{calc("cost of ordering at week b to consume at week u = price(b) &times; (1 + holding &times; weeks-held)",
      ["the DP picks, for each demand week, the order week b that minimises this;",
       "if holding &gt; the forward carry, the cheapest b is 'just-in-time' (order lead-time before need)."],
      "the optimal buy schedule",
      "This is the classic lot-sizing DP - it trades a cheaper (earlier) forward price against the cost of holding it.")}
<p>Each plan, priced over all 20,000 paths (so it carries real price risk), then compared on RALC:</p>
<table><thead><tr><th>Plan</th><th>Type</th><th>E[cost] (Cr)</th><th>SD (Cr)</th><th>CaR95 (Cr)</th><th>RALC (Cr)</th></tr></thead><tbody>
{''.join(f'<tr class="{"pick" if p["name"]==a["timing"]["recommended"] else ""}"><td>{p["name"]}</td><td>{p["kind"]}</td><td>{p["E"]:,.0f}</td><td>{p["sd"]:,.1f}</td><td>{p["car95"]:,.0f}</td><td><b>{p["ralc"]:,.0f}</b></td></tr>' for p in a["timing"]["policies"])}
</tbody></table>
<div class="callout"><b>Verdict: {a['timing']['verdict']}.</b> The best physical plan
("{a['timing']['phys_best']}") has RALC ₹{a['timing']['phys_best_ralc_cr']:.0f} Cr vs hedge
₹{a['timing']['hedge_ralc_cr']:.0f} Cr - the engine recommends the cheaper. This is exactly the trade-off:
if (forward price you lock) &lt; (spot + holding cost of buying early), hedging wins; otherwise buy physical.
Backwardated commodities (cheap forward) favour hedge; steeply-contango ones can tip to buy-and-hold.</div>

<h2 id="s11">11. Risk numbers: E, SD, CaR95, and the "risk cut"</h2>
<div class="kv">
 <div><b>E[Cost] (average)</b><br>{cr(ch['E'])}</div>
 <div><b>SD (uncertainty)</b><br>{cr(ch['sd'])}</div>
 <div><b>CaR95 (bad case)</b><br>{cr(ch['car95'])}</div>
 <div><b>do-nothing SD</b><br>{cr(naive['sd'])}</div>
</div>
{calc("risk cut = (1 &minus; engine SD &divide; do-nothing SD) &times; 100",
      [f"= (1 &minus; {ch['sd']/1e7:,.1f} &divide; {naive['sd']/1e7:,.1f}) &times; 100"],
      f"{risk_cut:.0f}% less risk",
      "So the plan removes about {:.0f}% of the cost uncertainty vs just buying at spot.".format(risk_cut))}
<div class="callout"><b>CaR95 in words:</b> if we ran the next 6 months 100 times, only 5 of them would
cost more than {cr(ch['car95'])}. It is the number the CFO cares about &mdash; the realistic bad case.</div>

<h2 id="s12">12. Act &mdash; the guardrail check (auto-execute vs escalate)</h2>
<p>The copilot may act on its own only if the immediate order is small enough to sit inside the council's cap.
The immediate order is the <b>larger</b> of (the near-month covered slice) and (the mandatory must-cover from
Section 5). For palm the supply-continuity must-cover drives it:</p>
{calc("immediate order = max( cover-slice , must-cover-now ) &times; lock price",
      [f"cover-slice = {a['chosen']['cover']*100:.0f}% &times; {a['monthly']:,.0f} t/mo = {a['chosen']['cover']*a['monthly']:,.0f} t",
       f"must-cover-now (Section 5) = {a['act']['must_cover_now']:,.0f} t &nbsp;&#8592; larger, so it wins",
       f"= {a['act']['must_cover_now']:,.0f} t &times; ₹{a['lock_landed']:,.0f}"],
      f"₹{act['immediate_order_value_cr']:.1f} Cr")}
<div class="warn"><b>Check:</b> order ₹{act['immediate_order_value_cr']:.1f} Cr vs auto-execute cap
₹{act['auto_execute_cap_cr']} Cr &#8594; order is bigger &#8594; <b>{act['decision']}</b>.
The engine does not self-trade this; it sends it to the council with the rationale. (Crude &amp; silver orders
are smaller than their caps, so those auto-execute.)</div>

<h2 id="s13">13. Backtest &mdash; would this have helped on real history?</h2>
<p>We replay the last year of actual prices and compare two cost lines: buying everything at spot ("naive")
vs the engine's cover-and-hedge plan. We measure the <b>month-to-month wobble (std-dev)</b> of each:</p>
<div class="kv">
 <div><b>Naive cost wobble</b><br>₹{bt['naive']['vol']:,.0f} / tonne</div>
 <div><b>Engine cost wobble</b><br>₹{bt['engine']['vol']:,.0f} / tonne</div>
</div>
{calc("steadier by = (1 &minus; engine wobble &divide; naive wobble) &times; 100",
      [f"= (1 &minus; {bt['engine']['vol']:,.0f} &divide; {bt['naive']['vol']:,.0f}) &times; 100"],
      f"{bt['vol_reduction_pct']:.0f}% steadier",
      f"...at about the same average cost ({bt['cost_diff_pct']:+.1f}%). So the smoothing was essentially free.")}

<h2 id="s14">14. Portfolio &mdash; correlation &amp; the natural-hedge benefit</h2>
<p>Because the three commodities do not move together, buying them as one portfolio cancels some risk.
First, how much each pair moves together (correlation, &minus;1 to +1):</p>
<table style="width:auto"><tbody>{corr_head}{corr_body}</tbody></table>
<p>Each commodity's own risk (SD): palm {sd_vec[0]:.1f}, crude {sd_vec[1]:.1f}, silver {sd_vec[2]:.1f} (₹ Cr).</p>
{calc("if risks simply ADDED = SD&#8321; + SD&#8322; + SD&#8323;",
      [f"= {sd_vec[0]:.1f} + {sd_vec[1]:.1f} + {sd_vec[2]:.1f}"],
      f"₹{port['additive_sd_cr']:.1f} Cr")}
{calc("real portfolio risk = &radic;( SD-vector &times; correlation-matrix &times; SD-vector )",
      ["(the standard formula that accounts for how they move together)"],
      f"₹{port['portfolio_sd_cr']:.1f} Cr")}
{calc("natural-hedge benefit = (1 &minus; real &divide; added-up) &times; 100",
      [f"= (1 &minus; {port['portfolio_sd_cr']:.1f} &divide; {port['additive_sd_cr']:.1f}) &times; 100"],
      f"{port['diversification_benefit_pct']:.0f}% lower risk",
      "This risk reduction is free - it comes purely from managing the commodities together, not in silos.")}

<h2 id="s15">15. Where exactly the AI / LLM is used (and where it is NOT)</h2>
<p>Important for a defensible pitch: <b>the AI does not invent the numbers.</b> The pricing maths
(RALC, Monte-Carlo, the frontier) stays a transparent, auditable engine. The AI sits <i>around</i> it &mdash;
turning messy real-world text into structured, cited inputs, then explaining, drafting and executing inside
hard limits. Every touchpoint:</p>
<table><thead><tr><th>Stage</th><th>AI component</th><th>Technique</th><th>Reads</th><th>Produces</th></tr></thead><tbody>
<tr><td><b>Sense</b></td><td>Market sensing</td><td><b>LLM</b></td><td>News, MPOB/USDA reports, export-duty notices, weather &amp; port advisories</td><td>A fundamentals bias per commodity, each with a cited reason an analyst can check</td></tr>
<tr><td><b>Sense</b></td><td>Document extraction</td><td><b>LLM</b></td><td>Supplier contracts, invoices, customs docs, ERP demand files</td><td>Structured inventory / lead-time / demand fields (feeds Section 5)</td></tr>
<tr><td><b>Score</b></td><td>&mdash; none (on purpose)</td><td>Rules</td><td>The 6 signals</td><td>The 0-100 score by a fixed formula &mdash; kept auditable</td></tr>
<tr><td><b>Decide</b></td><td>Scenario forecasting</td><td><b>ML</b> (+LLM)</td><td>Price/vol history + the event read</td><td>Probabilities for the price paths (upgrades the plain random walk)</td></tr>
<tr><td><b>Decide</b></td><td>Anomaly detection</td><td><b>ML</b></td><td>Live price, FX, freight, basis</td><td>Flags an odd move &amp; auto-fires the matching trigger</td></tr>
<tr><td><b>Act</b></td><td>Agentic execution</td><td><b>LLM agent</b></td><td>The chosen plan + the caps</td><td>Drafts the order, checks guardrails, auto-executes in caps or writes the escalation memo</td></tr>
<tr><td><b>All</b></td><td>Natural-language Q&amp;A</td><td><b>LLM</b></td><td>A plain question + the live model</td><td>"Margin if palm +10% &amp; rupee -3%?" &#8594; runs the model &amp; explains; writes memos/briefs</td></tr>
<tr><td><b>Monitor</b></td><td>Learning loop</td><td>ML + <b>LLM</b></td><td>Monthly back-test vs actuals</td><td>Summarises hits/misses &amp; proposes weight/trigger tweaks (human sign-off)</td></tr>
</tbody></table>
<div class="callout"><b>The rule that makes it trustworthy:</b> the LLM converts <i>text &#8594; structured, cited
input</i> and drafts/explains/executes &mdash; it never sets a price or overrides a guardrail. So you get AI's
reach over messy information <b>plus</b> a fully auditable number engine. That is why the SCORE step is
deliberately left as fixed rules, not an LLM.</div>

<h2 id="s16">16. Every assumption we made (register)</h2>
<p class="muted">These are the inputs we chose (not read from market data). Change any of them at the top of
<code>commodity_copilot.py</code> and every number above updates.</p>
<table><thead><tr><th>Assumption</th><th>Value</th><th>Why / note</th></tr></thead><tbody>
<tr><td>Annual demand (flagship)</td><td>{a['sales']['annual_demand']:,.0f} units</td><td><b>From the real sales file</b> (crude/silver still illustrative).</td></tr>
<tr><td>Demand volatility (flagship)</td><td>CV {a['sales']['demand_cv']*100:.0f}%</td><td><b>From the real sales file</b>; sizes the safety stock.</td></tr>
<tr><td>Inventory on hand (palm)</td><td>15,000 t (~1.5 months)</td><td>Netted off demand to get net procurement.</td></tr>
<tr><td>Safety stock (flagship)</td><td>1.65 &times; CV &times; demand &times; &radic;lead</td><td>Sized from the real demand volatility (95% service).</td></tr>
<tr><td>Supplier forward capacity</td><td>80% (palm)</td><td>Max share suppliers commit &#8594; caps how much we can lock.</td></tr>
<tr><td>Lead time</td><td>1.5 months</td><td>Order &#8594; ship &#8594; arrive; sets the reorder point.</td></tr>
<tr><td>Planning horizon</td><td>6 months</td><td>Rolling window, re-solved weekly.</td></tr>
<tr><td>Import duty (palm)</td><td>27.5%</td><td>Illustrative India CPO duty.</td></tr>
<tr><td>Base freight</td><td>$35 / tonne</td><td>Scaled by the Baltic Dry Index.</td></tr>
<tr><td>Buy-Now weights</td><td>Value 35 / Momentum 20 / Curve 25 / FX 20</td><td>Chosen importance of each signal.</td></tr>
<tr><td>Price drift in Monte-Carlo</td><td>0 (martingale)</td><td>We do not assume we can predict direction.</td></tr>
<tr><td>Monte-Carlo paths</td><td>{cfg['n_paths']:,}</td><td>More paths = smoother numbers.</td></tr>
<tr><td>Option premium factor</td><td>0.4 &times; &sigma; &times; &radic;T</td><td>Standard at-the-money rule of thumb.</td></tr>
<tr><td>&lambda; (risk aversion)</td><td>1.5 / 0.8 / 0.3</td><td>Conservative / Balanced / Aggressive presets.</td></tr>
<tr><td>Coverage &amp; hedge caps</td><td>see the 3-preset table</td><td>Hard limits the autonomy stays inside.</td></tr>
</tbody></table>

<div class="callout"><b>Bottom line:</b> every rupee figure in the slides and the explainer can be traced,
step by step, from the raw Excel prices through Sections 4&ndash;14 above. Nothing is a black box.</div>

<p class="foot">Generated by copilot_audit.py from the project data files. Snapshot {a['spot_dates'][0]}.
Illustrative decision-support tool &mdash; not financial advice.</p>
</div></body></html>"""
    with open("copilot_audit.html", "w") as fh:
        fh.write(html)
    print("Built -> copilot_audit.html")


if __name__ == "__main__":
    build(compute_audit())
