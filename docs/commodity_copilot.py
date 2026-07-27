"""
=============================================================================
 COMMODITY COPILOT  -  AI buy/hedge decision engine  (Kearney Case 4)
-----------------------------------------------------------------------------
 Upgraded model that implements the locked solution design:

   SENSE  ->  read the market for each commodity (6 signals)
   SCORE  ->  turn signals into 0-100 scores
   DECIDE ->  answer the 4 questions (buy-now / coverage / hedge / triggers)
              by MINIMISING a cost-AND-stability metric via Monte-Carlo
   ACT    ->  auto-execute inside the council's guardrails, else escalate

 What is genuinely new vs the first model:
   * MULTI-COMMODITY  : palm oil, crude, silver (+ FX & freight overlays)
   * PROBABILISTIC    : Monte-Carlo price paths -> a full cost distribution
   * RALC METRIC      : Risk-Adjusted Landed Cost = E[cost] + lambda * sd[cost]
                        (combines cost and stability - the client's own ask)
   * EFFICIENT FRONTIER: every candidate strategy scored on cost vs risk;
                         the engine picks the frontier point for the appetite
   * 3 RISK PRESETS   : conservative / balanced / aggressive -> lambda + caps
   * GUARDRAILS       : auto-execute within caps, else escalate to the council
   * BACKTEST         : replay on history vs naive buying
   * PORTFOLIO        : correlation across commodities -> natural-hedge benefit

 Everything is driven by the real Excel files already in this folder.
 It is a transparent rules+simulation engine - no black box.
=============================================================================
"""

import json
import os
import numpy as np
import pandas as pd

np.random.seed(7)  # reproducible numbers (the deck will quote them)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
HORIZON_M   = 6        # rolling 6-month planning window
N_PATHS     = 20_000   # Monte-Carlo price paths
VOL_WINDOW  = 60       # days for volatility
PCT_WINDOW  = 252      # days for the 52-week percentile
HOLDING_MONTHLY = 0.0125   # cost of holding inventory (finance + storage + insurance) ~1.25%/mo

# --- risk-appetite presets: set the RALC lambda AND the hard guardrails -----
# max_cover caps how much of 6-month demand you may LOCK physically (you keep the
# rest flexible because the demand forecast itself is uncertain); max_hedge caps
# how much of the remaining floating volume you may protect with options.
PRESETS = {
    "conservative": {"lambda": 1.5, "max_cover": 0.85, "max_hedge": 0.80, "auto_cap_cr": 60},
    "balanced":     {"lambda": 0.8, "max_cover": 0.60, "max_hedge": 0.50, "auto_cap_cr": 40},
    "aggressive":   {"lambda": 0.3, "max_cover": 0.40, "max_hedge": 0.30, "auto_cap_cr": 20},
}
RISK_APPETITE = "balanced"   # the council's choice for this run

# --- the commodity basket the platform covers ------------------------------
# convert(): native price -> all-in INR landed cost per unit
FX = {}  # filled after we load FX series

def _palm_convert(p):     # MYR/tonne -> INR/tonne  (FX + freight + 27.5% duty)
    usd = p / FX["usdmyr"] + FX["freight_usd_palm"]
    return usd * FX["usdinr"] * 1.275

def _crude_convert(p):    # USD/barrel -> INR/barrel
    return p * FX["usdinr"]

def _silver_convert(p):   # USD/ounce -> INR/ounce
    return p * FX["usdinr"]

# Supply-chain inputs per commodity (these drive the demand/inventory logic):
#   annual_demand  : how much we consume in a year (in the commodity's unit)
#   inventory      : how much we already hold today
#   lead_m         : lead time in months (order -> ship -> arrive)
#   safety_months  : months of demand we want to keep as a safety buffer
#   supplier_share : max share of demand our suppliers can commit as forwards
#                    (caps how much we can physically lock -> a supply constraint)
#   origins        : where it is sourced from (concentration = a supply risk)
COMMODITIES = {
    "Palm oil (CPO)": {
        "spot": "Mayank_KO1_Line Chart.xlsx", "f3": "Mayank_KO3_Line Chart.xlsx",
        "f6": "Mayank_KO6_Line Chart.xlsx", "ccy": "MYR", "unit": "tonne",
        "annual_demand": 120_000, "inventory": 15_000, "lead_m": 1.5,
        "safety_months": 1.0, "supplier_share": 0.80, "n_suppliers": 4,
        "origins": "Malaysia & Indonesia", "convert": _palm_convert, "flagship": True,
    },
    "Crude oil (Brent)": {
        "spot": "Mayank_CO1_Line Chart.xlsx", "f3": "Mayank_CO3_Line Chart.xlsx",
        "f6": "Mayank_CO6_Line Chart.xlsx", "ccy": "USD", "unit": "barrel",
        "annual_demand": 600_000, "inventory": 60_000, "lead_m": 1.0,
        "safety_months": 0.75, "supplier_share": 0.90, "n_suppliers": 6,
        "origins": "Middle East & West Africa", "convert": _crude_convert, "flagship": False,
    },
    "Silver": {
        "spot": "Mayank_XAGUSD_Line Chart.xlsx", "f3": "Mayank_SI3_Line Chart.xlsx",
        "f6": "Mayank_SI6_Line Chart.xlsx", "ccy": "USD", "unit": "ounce",
        "annual_demand": 500_000, "inventory": 50_000, "lead_m": 1.0,
        "safety_months": 0.75, "supplier_share": 0.90, "n_suppliers": 5,
        "origins": "Global bullion market", "convert": _silver_convert, "flagship": False,
    },
}


# ---------------------------------------------------------------------------
# SUPPLY CHAIN  -  turn demand, inventory, lead time & suppliers into volumes
# ---------------------------------------------------------------------------
def supply_chain(c):
    """
    Work out how much we ACTUALLY need to procure, netting off what we already
    hold, plus the classic inventory triggers (safety stock & reorder point).
    """
    monthly = c["annual_demand"] / 12.0
    horizon_demand = monthly * HORIZON_M          # what we will consume this window
    inv = c["inventory"]
    # safety stock: if we have REAL demand volatility (CV) from the sales file, size it
    # statistically (z * CV * demand * sqrt(lead) ~ 95% service); else use fixed months.
    cv = c.get("demand_cv")
    if cv is not None:
        safety = 1.65 * cv * monthly * (c["lead_m"] ** 0.5)
    else:
        safety = c["safety_months"] * monthly     # buffer we always want to keep
    reorder_point = c["lead_m"] * monthly + safety  # classic ROP = lead demand + safety
    must_cover_now = max(0.0, reorder_point - inv)  # immediate top-up to stay safe
    usable_inv = max(0.0, inv - safety)           # stock we can burn down (above safety)
    net_procurement = max(0.0, horizon_demand - usable_inv)  # what we must buy this window
    return {
        "monthly": monthly, "horizon_demand": horizon_demand, "inventory": inv,
        "months_cover": inv / monthly, "safety_stock": safety,
        "reorder_point": reorder_point, "below_reorder": inv < reorder_point,
        "must_cover_now": must_cover_now, "usable_inventory": usable_inv,
        "net_procurement": net_procurement, "monthly_proc": net_procurement / HORIZON_M,
        "supplier_share": c["supplier_share"], "n_suppliers": c["n_suppliers"],
        "origins": c["origins"], "lead_m": c["lead_m"], "safety_months": c["safety_months"],
        "unit": c["unit"], "demand_cv": c.get("demand_cv"),
        "demand_source": "real sales file" if c.get("demand_cv") is not None else "assumption",
    }


# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------
def load_series(path):
    df = pd.read_excel(path, sheet_name="Sheet1", header=0)
    df.columns = [str(c).strip() for c in df.columns]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Last Price"] = pd.to_numeric(df["Last Price"], errors="coerce")
    df = df.dropna(subset=["Date", "Last Price"]).sort_values("Date")
    return df.set_index("Date")["Last Price"]


# Real demand from the company's sales file. We take ONLY the two things the
# buy/hedge core needs: the demand run-rate and how volatile demand is (CV).
# Everything else in the file (customers, SKUs, regions, reps) is ignored on purpose.
# use the real sales file locally if present, else the anonymised sample (public repo)
SALES_FILE = "Lens_Sales_Data.xlsx" if os.path.exists("Lens_Sales_Data.xlsx") else "Lens_Sales_Sample.xlsx"

def demand_from_sales(path=None):
    path = path or SALES_FILE
    raw = pd.read_excel(path, sheet_name=0, header=None)
    r = raw.iloc[2:]                                   # skip label row + grand-total row
    date = pd.to_datetime(r[1], format="%d.%m.%Y", errors="coerce")
    units = pd.to_numeric(r[25], errors="coerce")
    s = pd.DataFrame({"date": date, "units": units}).dropna()
    monthly = s.set_index("date").resample("MS")["units"].sum()
    full = monthly.iloc[:-1]                            # drop the partial final month
    m, sd = float(full.mean()), float(full.std())
    return {"annual_demand": round(m * 12), "monthly": round(m),
            "demand_cv": round(sd / m, 2), "n_months": int(len(full)),
            "trend_up": bool(full.iloc[-3:].mean() > full.iloc[:3].mean())}


def load_fx():
    usdmyr = load_series("Mayank_USDMYR_Line Chart.xlsx")
    usdinr = load_series("Mayank_USDINR_Line Chart.xlsx")
    bdiy   = load_series("Priya_BDIY_Line Chart.xlsx")
    freight = 35.0 * float(bdiy.iloc[-1]) / float(bdiy.tail(PCT_WINDOW).mean())
    FX.update({"usdmyr": float(usdmyr.iloc[-1]), "usdinr": float(usdinr.iloc[-1]),
               "freight_usd_palm": freight,
               "usdinr_mom": float(usdinr.iloc[-1] / usdinr.iloc[-22] - 1) * 100})


# ---------------------------------------------------------------------------
# 1) SENSE  -  signals for one commodity
# ---------------------------------------------------------------------------
def sense(c):
    spot = load_series(c["spot"]); f3 = load_series(c["f3"]); f6 = load_series(c["f6"])
    px, p3, p6 = float(spot.iloc[-1]), float(f3.iloc[-1]), float(f6.iloc[-1])
    ret = np.log(spot / spot.shift(1)).dropna()
    vol = float(ret.tail(VOL_WINDOW).std() * np.sqrt(252) * 100)
    pctile = float((spot.tail(PCT_WINDOW) <= px).mean() * 100)
    mom = float((spot.iloc[-1] / spot.iloc[-22] - 1) * 100) if len(spot) > 22 else 0.0
    curve = (p6 / px - 1) * 100                      # +contango / -backwardation
    landed = c["convert"](px)
    return {
        "spot": px, "f3": p3, "f6": p6, "ccy": c["ccy"], "unit": c["unit"],
        "vol": round(vol, 1), "percentile": round(pctile, 1),
        "momentum": round(mom, 2), "curve": round(curve, 2),
        "landed": round(landed, 1),
        "low52": round(float(spot.tail(PCT_WINDOW).min()), 2),
        "high52": round(float(spot.tail(PCT_WINDOW).max()), 2),
        "_spot_series": spot,   # kept for the backtest
    }


# ---------------------------------------------------------------------------
# 2) SCORE  -  buy-now score (transparent 0-100 blend)
# ---------------------------------------------------------------------------
def clamp(x, lo=0, hi=100): return max(lo, min(hi, x))

def score(s):
    value = 100 - s["percentile"]                    # cheap -> high
    momo  = clamp(50 + s["momentum"] * 10)           # rising -> high
    curv  = clamp(50 + s["curve"] * 10)              # contango -> high
    fx    = clamp(50 + FX["usdinr_mom"] * 10)        # rupee weaker -> high
    parts = {"value": value, "momentum": momo, "curve": curv, "fx": fx}
    w = {"value": .35, "momentum": .20, "curve": .25, "fx": .20}
    total = sum(parts[k] * w[k] for k in w)
    action = "BUY NOW" if total >= 60 else ("PHASE IN" if total >= 45 else "WAIT")
    return {"score": round(total, 1), "action": action,
            "parts": {k: round(v, 1) for k, v in parts.items()}}


# ---------------------------------------------------------------------------
# 3) DECIDE  -  Monte-Carlo cost distribution + RALC optimisation
# ---------------------------------------------------------------------------
def simulate_landed_paths(c, s):
    """
    Monte-Carlo monthly landed-cost paths over the horizon (GBM).
    Drift = 0 (martingale): we do NOT assume we can predict direction, so the
    expected future spot = today's spot. The forward curve is then treated as the
    CARRY COST of locking (contango = it costs to lock; backwardation = you are
    paid to lock) - which is exactly how practitioners read the curve.
    """
    sigma = s["vol"] / 100.0
    dt = 1 / 12.0
    z = np.random.normal(size=(N_PATHS, HORIZON_M))
    steps = np.exp((-0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z)
    native_paths = s["spot"] * np.cumprod(steps, axis=1)      # (paths, months)
    landed_paths = c["convert"](native_paths)
    return landed_paths


def strategy_cost(c, s, sc, landed_paths, cover, hedge):
    """
    Total procurement cost distribution for a strategy over the horizon.
      cover = fraction of the NET requirement locked now via physical forward
      hedge = fraction of the REMAINING volume protected with a call/cap option
              (keeps downside, caps upside, costs a premium)
    NOTE: volumes are the NET procurement (demand minus usable inventory) from the
    supply-chain step - so what we already hold reduces what we buy.
    Returns array of total costs (one per path).
    """
    monthly = sc["monthly_proc"]                 # net monthly buy (after inventory)
    total_units = sc["net_procurement"]          # net over the whole horizon
    T = HORIZON_M / 12.0
    # lock price = the 6-month forward "strip" average (~ mean of spot..f6).
    # In contango this is ABOVE today's spot -> locking carries a real cost;
    # in backwardation it is BELOW spot -> you are paid to lock.
    strip_native = (s["spot"] + s["f6"]) / 2.0
    lock_landed = c["convert"](strip_native)         # forward lock price / unit
    strike = lock_landed                             # ATM-forward option strike
    premium = 0.4 * lock_landed * (s["vol"] / 100) * np.sqrt(T)   # option premium/unit

    # covered volume: fixed at the forward lock price
    covered_cost = cover * total_units * lock_landed

    # floating volume, spread evenly across the months
    float_per_m = (1 - cover) * monthly
    spot = landed_paths                               # (paths, months)
    hedged_unit = np.minimum(spot, strike) + premium  # option cap on the upside
    unhedged_unit = spot
    float_unit = hedge * hedged_unit + (1 - hedge) * unhedged_unit
    floating_cost = float_per_m * float_unit.sum(axis=1)

    return covered_cost + floating_cost


def optimise(c, s, sc):
    """Score a grid of strategies on RALC = E + lambda*sd; pick the best inside caps."""
    preset = PRESETS[RISK_APPETITE]
    lam, cap_h = preset["lambda"], preset["max_hedge"]
    # cover cap = the SMALLER of the appetite cap and what suppliers can commit
    # (a real supply constraint - you cannot lock more than suppliers will sell forward)
    cap_c = min(preset["max_cover"], sc["supplier_share"])
    paths = simulate_landed_paths(c, s)

    grid, frontier = [], []
    for cover in (0, .2, .4, .6, .8, 1.0):
        for hedge in (0, .25, .5, .75, 1.0):
            if cover > cap_c + 1e-9 or hedge > cap_h + 1e-9:
                continue
            costs = strategy_cost(c, s, sc, paths, cover, hedge)
            E, sd = float(costs.mean()), float(costs.std())
            car95 = float(np.percentile(costs, 95))
            ralc = E + lam * sd
            grid.append({"cover": cover, "hedge": hedge, "E": E, "sd": sd,
                         "car95": car95, "ralc": ralc})

    best = min(grid, key=lambda g: g["ralc"])
    naive = next(g for g in grid if g["cover"] == 0 and g["hedge"] == 0)

    # efficient frontier = points not dominated (no other point cheaper AND steadier)
    for g in grid:
        if not any((o["E"] <= g["E"] and o["sd"] < g["sd"]) or
                   (o["E"] < g["E"] and o["sd"] <= g["sd"]) for o in grid):
            frontier.append(g)
    frontier.sort(key=lambda g: g["sd"])

    # instrument: options if price is already dear (keep upside), else forwards
    instrument = ("Physical forwards (cover) + call options/caps (hedge)"
                  if s["percentile"] >= 70 else
                  "Physical forwards for both cover and hedge")

    # cost distribution (crore) for naive vs chosen -> feeds the explainer chart
    naive_costs = strategy_cost(c, s, sc, paths, 0, 0) / 1e7
    best_costs = strategy_cost(c, s, sc, paths, best["cover"], best["hedge"]) / 1e7
    lo = float(min(naive_costs.min(), best_costs.min()))
    hi = float(max(naive_costs.max(), best_costs.max()))
    edges = np.linspace(lo, hi, 31)
    centers = ((edges[:-1] + edges[1:]) / 2).round(1).tolist()
    dist = {"centers": centers,
            "naive": np.histogram(naive_costs, bins=edges)[0].tolist(),
            "engine": np.histogram(best_costs, bins=edges)[0].tolist(),
            "naive_E": round(float(naive_costs.mean()), 0),
            "engine_E": round(float(best_costs.mean()), 0),
            "engine_car95": round(float(np.percentile(best_costs, 95)), 0),
            "naive_car95": round(float(np.percentile(naive_costs, 95)), 0)}

    # translate cover% + hedge% into a 100% split so it never looks like "60+50=110"
    cov, hed = best["cover"], best["hedge"]
    split = {"locked_pct": round(cov * 100),                       # physical forwards
             "option_pct": round((1 - cov) * hed * 100),           # hedged with options
             "unhedged_pct": round((1 - cov) * (1 - hed) * 100)}   # left floating
    caps = {"cover_cap": cap_c, "hedge_cap": cap_h,
            "cover_at_cap": abs(cov - cap_c) < 1e-9,
            "hedge_at_cap": abs(hed - cap_h) < 1e-9,
            "supplier_share": sc["supplier_share"],
            "appetite_cover_cap": preset["max_cover"]}

    return {"lambda": lam, "chosen": best, "naive": naive, "split": split, "caps": caps,
            "grid": grid, "frontier": frontier, "instrument": instrument, "dist": dist,
            "savings_vs_naive": round(naive["E"] - best["E"], 0),
            "risk_cut_pct": round((1 - best["sd"] / naive["sd"]) * 100, 0)}


def triggers(c, s, sc):
    lo, hi = s["low52"], s["high52"]
    buy = round(lo + .25 * (hi - lo), 1); slow = round(lo + .75 * (hi - lo), 1)
    return [
        {"if": f"price <= {buy:,.0f} {s['ccy']}", "then": "accelerate cover / add to mid bucket"},
        {"if": f"price >= {slow:,.0f} {s['ccy']}", "then": "slow buying, lean on inventory + hedges"},
        {"if": f"volatility > {max(20, s['vol'] + 5):.0f}%", "then": "raise the hedge ratio"},
        {"if": f"USDINR > {FX['usdinr'] + 1:.1f}", "then": "add an FX forward"},
        {"if": f"inventory < reorder point ({sc['reorder_point']:,.0f} {sc['unit']}s)",
         "then": f"MANDATORY buy of {sc['must_cover_now']:,.0f} {sc['unit']}s (supply continuity)"},
        {"if": "a key supplier / origin is disrupted (e.g. export ban)",
         "then": "raise safety stock & diversify origins before price-optimising"},
    ]


# ---------------------------------------------------------------------------
# 4) ACT  -  guardrails: auto-execute inside caps, else escalate
# ---------------------------------------------------------------------------
def act(c, s, sc, opt):
    preset = PRESETS[RISK_APPETITE]
    lock_landed = c["convert"]((s["spot"] + s["f6"]) / 2.0)
    # the immediate slice = the near month of the covered plan, but never less than
    # the supply-continuity top-up needed to get back above the reorder point
    plan_slice = opt["chosen"]["cover"] * sc["monthly_proc"]
    immediate_units = max(plan_slice, sc["must_cover_now"])
    order_value_cr = immediate_units * lock_landed / 1e7        # INR crore
    within_caps = (opt["chosen"]["hedge"] <= preset["max_hedge"] + 1e-9 and
                   order_value_cr <= preset["auto_cap_cr"])
    return {
        "immediate_order_units": round(immediate_units, 0),
        "immediate_order_value_cr": round(order_value_cr, 1),
        "must_cover_now": round(sc["must_cover_now"], 0),
        "auto_execute_cap_cr": preset["auto_cap_cr"],
        "decision": "AUTO-EXECUTE" if within_caps else "ESCALATE TO COUNCIL",
        "reason": ("inside all guardrails (hedge <= cap, order <= auto-cap)"
                   if within_caps else
                   "order size or hedge ratio exceeds the auto-execute cap"),
    }


# ---------------------------------------------------------------------------
# BACKTEST  -  illustrative historical replay vs naive buying
# ---------------------------------------------------------------------------
def backtest(c, s, opt):
    """Replay: how would locking part of demand ~3M forward have smoothed cost?"""
    landed_hist = c["convert"](s["_spot_series"]).dropna()
    lag = 63  # ~3 trading months = the forward-strip averaging window
    if len(landed_hist) <= lag + 20:
        return None
    naive = landed_hist.iloc[lag:].values
    # covered volume behaves like buying at the trailing forward-strip average
    # (dollar-cost-averaged forward locks), which smooths the cost line
    locked_ref = landed_hist.rolling(lag).mean().iloc[lag:].values
    eff_lock = opt["chosen"]["cover"] + (1 - opt["chosen"]["cover"]) * opt["chosen"]["hedge"] * 0.7
    engine = eff_lock * locked_ref + (1 - eff_lock) * naive

    def stats(x):
        return {"avg": round(float(np.mean(x)), 0), "vol": round(float(np.std(x)), 0),
                "car95": round(float(np.percentile(x, 95)), 0),
                "worst": round(float(np.max(x)), 0)}
    n, e = stats(naive), stats(engine)
    return {"naive": n, "engine": e, "eff_lock_pct": round(eff_lock * 100, 0),
            "vol_reduction_pct": round((1 - e["vol"] / n["vol"]) * 100, 0) if n["vol"] else 0,
            "cost_diff_pct": round((e["avg"] / n["avg"] - 1) * 100, 2)}


# ---------------------------------------------------------------------------
# BUY TIMING  -  when to buy (physical, with holding cost & lead time) vs hedge
# ---------------------------------------------------------------------------
def buy_timing(c, s, sc):
    """
    Decide the cheapest way to have the commodity WHEN it is needed, on a weekly
    grid, including LEAD TIME and HOLDING COST:

      * a Wagner-Whitin DYNAMIC PROGRAM finds the optimal order week for each
        week of demand on the market's expected (forward) price path, trading the
        forward price against the holding cost of carrying it early;
      * every candidate policy is then priced over the Monte-Carlo paths (so it
        carries real price risk) and ranked on RALC = E + lambda*SD;
      * finally we compare the best PHYSICAL plan against the FINANCIAL HEDGE
        (lock the forward, no holding, no price risk) and recommend the cheaper.
    """
    lam = PRESETS[RISK_APPETITE]["lambda"]
    W = 26                                    # weeks in the 6-month horizon
    wpm = 52 / 12.0                           # weeks per month (~4.33)
    lead_w = max(1, round(sc["lead_m"] * wpm))
    h = HOLDING_MONTHLY / wpm                 # holding cost per week (fraction of value)
    sigma = s["vol"] / 100.0
    dt = 1 / 52.0

    # weekly Monte-Carlo landed-price paths (martingale, same engine as before)
    z = np.random.normal(size=(N_PATHS, W))
    native = s["spot"] * np.cumprod(np.exp(-0.5 * sigma ** 2 * dt + sigma * np.sqrt(dt) * z), axis=1)
    L = c["convert"](native)                  # (paths, weeks) realised landed prices
    L0 = c["convert"](s["spot"])              # today's landed price (known)
    F = c["convert"](s["spot"] + (s["f6"] - s["spot"]) * (np.arange(1, W + 1) / W))  # forward path

    cons = list(range(lead_w, W))             # weeks whose demand we time here
    dw = sc["net_procurement"] / W            # demand per week

    # --- Wagner-Whitin DP: best order week b* for each consumption week u ------
    # cost of ordering at b to consume at u = forward price(b) grown by holding
    # for the (u-lead-b) weeks it then sits in stock. Pick the cheapest feasible b.
    sched = {}
    for u in cons:
        best_b, best_c = u - lead_w, F[u - lead_w]
        for b in range(0, u - lead_w + 1):
            cc = F[b] * (1 + h * (u - lead_w - b))
            if cc < best_c:
                best_c, best_b = cc, b
        sched[u] = best_b

    def dist(cost_paths):
        E, sd = float(cost_paths.mean()), float(cost_paths.std())
        return {"E": E, "sd": sd, "car95": float(np.percentile(cost_paths, 95)),
                "ralc": E + lam * sd}

    # --- candidate policies, each priced over ALL Monte-Carlo paths -----------
    jit = dw * np.stack([L[:, u - lead_w] for u in cons], axis=1).sum(axis=1)
    buynow = dw * np.stack([np.full(N_PATHS, L0 * (1 + h * (u - lead_w))) for u in cons], axis=1).sum(axis=1)
    ww = dw * np.stack([L[:, sched[u]] * (1 + h * (u - lead_w - sched[u])) for u in cons], axis=1).sum(axis=1)
    hedge = np.full(N_PATHS, dw * float(sum(F[u] for u in cons)))   # locked, deterministic

    pols = [{"name": "Buy just-in-time", "kind": "physical", **dist(jit)},
            {"name": "Buy now & hold", "kind": "physical", **dist(buynow)},
            {"name": "DP-optimal schedule", "kind": "physical", **dist(ww)},
            {"name": "Hedge (lock forward)", "kind": "hedge", **dist(hedge)}]
    best = min(pols, key=lambda p: p["ralc"])
    phys_best = min((p for p in pols if p["kind"] == "physical"), key=lambda p: p["ralc"])
    hedge_p = next(p for p in pols if p["kind"] == "hedge")
    verdict = "HEDGE" if hedge_p["ralc"] <= phys_best["ralc"] else "BUY PHYSICAL"

    # schedule summary: what share of timed demand is ordered in which week
    from collections import Counter
    cnt = Counter(sched.values())
    schedule = [{"order_week": int(b), "pct": round(100 * n / len(cons))}
                for b, n in sorted(cnt.items())]

    return {
        "lead_weeks": lead_w, "holding_monthly_pct": HOLDING_MONTHLY * 100, "weeks": W,
        "timed_units": round(dw * len(cons)),
        "policies": [{k: (round(v / 1e7, 1) if k in ("E", "sd", "car95", "ralc") else v)
                      for k, v in p.items()} for p in pols],
        "recommended": best["name"], "verdict": verdict,
        "phys_best": phys_best["name"],
        "hedge_ralc_cr": round(hedge_p["ralc"] / 1e7, 1),
        "phys_best_ralc_cr": round(phys_best["ralc"] / 1e7, 1),
        "schedule": schedule,
    }


# ---------------------------------------------------------------------------
# PORTFOLIO  -  correlation & natural-hedge (diversification) benefit
# ---------------------------------------------------------------------------
def portfolio(results, series_map):
    names = list(results.keys())
    rets = pd.DataFrame({n: np.log(series_map[n] / series_map[n].shift(1))
                         for n in names}).dropna()
    corr = rets.corr()

    E = np.array([results[n]["optimise"]["chosen"]["E"] for n in names])
    sd = np.array([results[n]["optimise"]["chosen"]["sd"] for n in names])
    C = corr.loc[names, names].values
    port_sd = float(np.sqrt(sd @ C @ sd))            # correlated portfolio risk
    add_sd = float(sd.sum()) or 1.0                   # if risks just added up (guard)
    lam = PRESETS[RISK_APPETITE]["lambda"]
    return {
        "commodities": names,
        "corr": {a: {b: round(float(corr.loc[a, b]), 2) for b in names} for a in names},
        "total_spend_cr": round(float(E.sum()) / 1e7, 0),
        "portfolio_sd_cr": round(port_sd / 1e7, 1),
        "additive_sd_cr": round(add_sd / 1e7, 1),
        "diversification_benefit_pct": round((1 - port_sd / add_sd) * 100, 0),
        "portfolio_ralc_cr": round((float(E.sum()) + lam * port_sd) / 1e7, 0),
    }


# ---------------------------------------------------------------------------
# ORCHESTRATE
# ---------------------------------------------------------------------------
def run():
    load_fx()
    # pull REAL demand + demand volatility from the company's sales file and feed it
    # into the flagship (replaces the made-up demand & assumed uncertainty).
    sales = None
    try:
        sales = demand_from_sales()
        flag = next(k for k, v in COMMODITIES.items() if v["flagship"])
        COMMODITIES[flag]["annual_demand"] = sales["annual_demand"]
        COMMODITIES[flag]["demand_cv"] = sales["demand_cv"]
    except Exception as e:
        print(f"(sales file not used: {e})")

    results, series_map = {}, {}
    for name, c in COMMODITIES.items():
        s = sense(c)
        scq = score(s)
        supply = supply_chain(c)                      # <-- demand / inventory / suppliers
        opt = optimise(c, s, supply)
        trg = triggers(c, s, supply)
        action = act(c, s, supply, opt)
        bt = backtest(c, s, opt)
        timing = buy_timing(c, s, supply)            # <-- when to buy vs hedge (DP + holding)
        series_map[name] = s.pop("_spot_series")     # remove series before JSON
        results[name] = {"sense": s, "score": scq, "supply_chain": supply, "optimise": opt,
                         "triggers": trg, "act": action, "backtest": bt, "timing": timing,
                         "commodity": {"unit": c["unit"], "annual_demand": c["annual_demand"],
                                       "flagship": c["flagship"]}}
    port = portfolio(results, series_map)

    report(results, port)
    out = {"config": {"horizon_m": HORIZON_M, "n_paths": N_PATHS,
                      "risk_appetite": RISK_APPETITE, "preset": PRESETS[RISK_APPETITE],
                      "fx": FX, "sales": sales},
           "commodities": results, "portfolio": port}
    with open("copilot_results.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("\nSaved -> copilot_results.json\n")
    return out


def report(results, port):
    print("=" * 78)
    print(f"  COMMODITY COPILOT  |  appetite = {RISK_APPETITE}  "
          f"(lambda={PRESETS[RISK_APPETITE]['lambda']})  |  {N_PATHS:,} Monte-Carlo paths")
    print("=" * 78)
    for name, r in results.items():
        s, sc, opt, act_, bt = r["sense"], r["score"], r["optimise"], r["act"], r["backtest"]
        sup = r["supply_chain"]; sp = opt["split"]; ch = opt["chosen"]
        flag = "  * flagship" if r["commodity"]["flagship"] else ""
        print(f"\n--- {name}{flag} ---")
        print(f"  SENSE : spot {s['spot']:,.0f} {s['ccy']}/{s['unit']} | "
              f"pctile {s['percentile']:.0f} | vol {s['vol']:.0f}% | "
              f"curve {s['curve']:+.1f}% | landed Rs {s['landed']:,.0f}")
        cvtxt = (f" | demand vol CV {sup['demand_cv']*100:.0f}% (from {sup['demand_source']})"
                 if sup['demand_cv'] is not None else "")
        print(f"  SUPPLY: demand {sup['horizon_demand']:,.0f} - usable inv "
              f"{sup['usable_inventory']:,.0f} = net buy {sup['net_procurement']:,.0f} {s['unit']}s "
              f"| {sup['months_cover']:.1f} mo cover | must-cover {sup['must_cover_now']:,.0f}{cvtxt}")
        print(f"  SCORE : buy-now {sc['score']:.0f}/100 -> {sc['action']}   {sc['parts']}")
        print(f"  DECIDE: split of net need = {sp['locked_pct']:.0f}% locked + "
              f"{sp['option_pct']:.0f}% option + {sp['unhedged_pct']:.0f}% floating = 100% "
              f"| {opt['instrument']}")
        print(f"          E[cost] Rs {ch['E']/1e7:,.0f} Cr | risk(sd) Rs {ch['sd']/1e7:,.1f} Cr "
              f"| CaR95 Rs {ch['car95']/1e7:,.0f} Cr | risk cut {opt['risk_cut_pct']:.0f}% vs naive")
        print(f"  ACT   : {act_['decision']} - near order Rs {act_['immediate_order_value_cr']:.1f} Cr "
              f"(auto-cap Rs {act_['auto_execute_cap_cr']} Cr) [{act_['reason']}]")
        if bt:
            print(f"  BACKTEST: cost-vol Rs {bt['engine']['vol']:,.0f}/{s['unit']} (engine) vs "
                  f"Rs {bt['naive']['vol']:,.0f}/{s['unit']} (naive) -> "
                  f"{bt['vol_reduction_pct']:.0f}% steadier at {bt['cost_diff_pct']:+.1f}% cost")
        tm = r["timing"]
        print(f"  TIMING: lead {tm['lead_weeks']}w, holding {tm['holding_monthly_pct']:.2f}%/mo -> "
              f"{tm['verdict']} (best physical '{tm['phys_best']}' RALC {tm['phys_best_ralc_cr']:.0f} vs "
              f"hedge RALC {tm['hedge_ralc_cr']:.0f} Cr)")
        for p in tm["policies"]:
            print(f"        {p['name']:<24} E {p['E']:>6.0f} | SD {p['sd']:>4.1f} | "
                  f"CaR95 {p['car95']:>6.0f} | RALC {p['ralc']:>6.0f} Cr  ({p['kind']})")
    print("\n" + "-" * 78)
    print("  PORTFOLIO VIEW")
    print(f"  Total 6-mo spend  : Rs {port['total_spend_cr']:,.0f} Cr")
    print(f"  Risk if added up  : Rs {port['additive_sd_cr']:,.1f} Cr")
    print(f"  Risk with netting : Rs {port['portfolio_sd_cr']:,.1f} Cr  "
          f"-> {port['diversification_benefit_pct']:.0f}% natural-hedge benefit")
    print(f"  Correlations      :")
    for a in port["commodities"]:
        print("     " + a[:14].ljust(15) +
              "  ".join(f"{b[:5]}:{port['corr'][a][b]:+.2f}" for b in port["commodities"]))


if __name__ == "__main__":
    run()
