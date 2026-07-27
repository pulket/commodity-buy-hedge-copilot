"""
Commodity Copilot - web interface (Streamlit).

Run locally:   streamlit run app.py
Deploy free:   push this repo to GitHub, then connect it on share.streamlit.io

Lets you tweak the settings, upload your own sales file, run the model, see the
decisions & charts, and download the full reports and the PowerPoint.
"""
import os
import tempfile
import pandas as pd
import streamlit as st

import commodity_copilot as cc
import copilot_html as ch

st.set_page_config(page_title="Commodity Copilot", page_icon="\U0001F4E6", layout="wide")

PURPLE = "#4C1D95"

st.markdown(
    f"<h1 style='color:{PURPLE};margin-bottom:0'>\U0001F4E6 Commodity Copilot</h1>"
    "<p style='color:#555;margin-top:4px'>An AI buy / hedge decision engine — "
    "Sense → Score → Decide → Act, across a basket of commodities, with a "
    "supply-chain track and a buy-timing DP. Set the options, (optionally) upload your "
    "sales file, and run.</p>",
    unsafe_allow_html=True)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    appetite = st.selectbox("Risk appetite", ["conservative", "balanced", "aggressive"],
                            index=1, help="Sets the RALC risk dial (λ) and the hard caps.")
    holding = st.slider("Holding cost (% per month)", 0.0, 3.0, 1.25, 0.05,
                        help="Finance + storage + insurance for inventory bought early.")
    horizon = st.slider("Planning horizon (months)", 3, 12, 6, 1)
    n_paths = st.select_slider("Monte-Carlo paths", [2000, 5000, 10000, 20000], value=10000)

    st.markdown("---")
    st.caption("Demand & its volatility are read from a sales file. Leave empty to use the "
               "built-in anonymised sample.")
    sales_up = st.file_uploader("Your sales file (.xlsx)", type=["xlsx"])

    with st.expander("Advanced: replace price files"):
        st.caption("Optional. Each is a 2-column sheet (Date, Last Price). "
                   "Leave empty to use the bundled series.")
        up_palm = st.file_uploader("Palm oil spot (KO1)", type=["xlsx"], key="palm")
        up_crude = st.file_uploader("Crude oil spot (CO1)", type=["xlsx"], key="crude")
        up_silver = st.file_uploader("Silver spot (XAGUSD)", type=["xlsx"], key="silver")

    run = st.button("▶  Run the model", type="primary", use_container_width=True)


def _save(upload):
    """Persist an uploaded file to a temp path and return it."""
    suffix = os.path.splitext(upload.name)[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(upload.getbuffer()); tmp.close()
    return tmp.name


@st.cache_data(show_spinner=False)
def run_model(appetite, holding, horizon, n_paths, sales_path, palm_p, crude_p, silver_p):
    """Configure the engine globals from the UI and run it."""
    cc.RISK_APPETITE = appetite
    cc.HOLDING_MONTHLY = holding / 100.0
    cc.HORIZON_M = horizon
    cc.N_PATHS = n_paths
    if sales_path:
        cc.SALES_FILE = sales_path
    if palm_p:   cc.COMMODITIES["Palm oil (CPO)"]["spot"] = palm_p
    if crude_p:  cc.COMMODITIES["Crude oil (Brent)"]["spot"] = crude_p
    if silver_p: cc.COMMODITIES["Silver"]["spot"] = silver_p
    return cc.run()


if run or "results" not in st.session_state:
    with st.spinner("Running Monte-Carlo, DP and portfolio…"):
        results = run_model(
            appetite, holding, horizon, n_paths,
            _save(sales_up) if sales_up else None,
            _save(up_palm) if up_palm else None,
            _save(up_crude) if up_crude else None,
            _save(up_silver) if up_silver else None)
    st.session_state["results"] = results

res = st.session_state["results"]
C = res["commodities"]; port = res["portfolio"]; cfg = res["config"]
flag = next(n for n, r in C.items() if r["commodity"]["flagship"])
P = C[flag]; opt = P["optimise"]; sup = P["supply_chain"]; tm = P["timing"]


# ---------------------------------------------------------------- KPIs
st.subheader("Portfolio at a glance")
k = st.columns(5)
k[0].metric("6-month spend", f"₹{port['total_spend_cr']:,.0f} Cr")
k[1].metric("Risk if siloed", f"₹{port['additive_sd_cr']:,.0f} Cr")
k[2].metric("Risk if netted", f"₹{port['portfolio_sd_cr']:,.0f} Cr",
            f"-{port['diversification_benefit_pct']:.0f}% natural hedge")
k[3].metric("Flagship risk cut", f"-{opt['risk_cut_pct']:.0f}%")
k[4].metric("Demand (from sales)", f"{cfg['sales']['annual_demand']:,.0f}/yr",
            f"CV {cfg['sales']['demand_cv']*100:.0f}%")


# ---------------------------------------------------------------- decisions table
st.subheader("Per-commodity decisions")
rows = []
for n, r in C.items():
    s = r["sense"]; o = r["optimise"]; sp = o["split"]
    rows.append({
        "Commodity": n, "Spot": f"{s['spot']:,.0f} {s['ccy']}",
        "%ile": f"{s['percentile']:.0f}", "Vol": f"{s['vol']:.0f}%",
        "Curve": f"{s['curve']:+.1f}%", "Buy-now": r["score"]["action"],
        "Lock/Opt/Float": f"{sp['locked_pct']:.0f}/{sp['option_pct']:.0f}/{sp['unhedged_pct']:.0f}",
        "Risk cut": f"-{o['risk_cut_pct']:.0f}%",
        "Timing": r["timing"]["verdict"],
        "Act": "AUTO" if r["act"]["decision"] == "AUTO-EXECUTE" else "ESCALATE"})
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.caption("**Lock/Opt/Float** = % locked (forwards) / option-hedged / floating — adds to 100%. "
           "**Timing** = physical buy-and-hold vs hedge, incl. holding cost.")


# ---------------------------------------------------------------- flagship deep-dive
st.subheader(f"Deep dive — {flag}")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Efficient frontier** (each dot = a strategy; engine picks the frontier point)")
    svg = ch.frontier_scatter(opt["grid"], opt["frontier"], opt["chosen"])
    st.components.v1.html(f"<div style='background:#fff'>{svg}</div>", height=320)
with c2:
    st.markdown("**Pay-off distribution** (do-nothing vs engine plan)")
    svg = ch.dist_chart(opt["dist"])
    st.components.v1.html(f"<div style='background:#fff'>{svg}</div>", height=260)

st.markdown("**When to buy — physical (with holding cost) vs hedge**")
tdf = pd.DataFrame([{"Plan": p["name"], "Type": p["kind"], "E[cost] (Cr)": p["E"],
                     "Risk SD (Cr)": p["sd"], "CaR95 (Cr)": p["car95"], "RALC (Cr)": p["ralc"]}
                    for p in tm["policies"]])
st.dataframe(tdf, use_container_width=True, hide_index=True)
verdict_col = "#C0243B" if tm["verdict"] == "HEDGE" else "#15803D"
st.markdown(
    f"**Verdict: <span style='color:{verdict_col}'>{tm['verdict']}</span>** — best physical plan "
    f"'{tm['phys_best']}' (RALC ₹{tm['phys_best_ralc_cr']:.0f} Cr) vs hedge "
    f"₹{tm['hedge_ralc_cr']:.0f} Cr, at {tm['holding_monthly_pct']:.2f}%/mo holding & "
    f"{tm['lead_weeks']}-week lead.", unsafe_allow_html=True)


# ---------------------------------------------------------------- supply chain + narrative
with st.expander("Supply-chain detail"):
    st.write(f"- Demand over horizon: **{sup['horizon_demand']:,.0f} {sup['unit']}** "
             f"(net of usable inventory → buy **{sup['net_procurement']:,.0f}**)")
    st.write(f"- Months of cover on hand: **{sup['months_cover']:.1f}** "
             f"({'below' if sup['below_reorder'] else 'above'} reorder point {sup['reorder_point']:,.0f})")
    st.write(f"- Mandatory must-cover-now: **{sup['must_cover_now']:,.0f} {sup['unit']}** "
             f"(supply continuity, before price-optimising)")
    st.write(f"- Suppliers: **{sup['n_suppliers']}** ({sup['origins']}), forward-commit cap "
             f"**{sup['supplier_share']*100:.0f}%**")

with st.expander("Why this recommendation (plain English)"):
    for line in [
        f"{flag} is at the {P['sense']['percentile']:.0f}th percentile of its year, vol "
        f"{P['sense']['vol']:.0f}%, curve {P['sense']['curve']:+.1f}%.",
        f"Buy-now score {P['score']['score']:.0f}/100 → {P['score']['action']}.",
        f"Plan: {opt['split']['locked_pct']:.0f}% locked + {opt['split']['option_pct']:.0f}% option "
        f"+ {opt['split']['unhedged_pct']:.0f}% floating (=100%), cutting risk {opt['risk_cut_pct']:.0f}%.",
        f"Timing: {tm['verdict']} once holding cost is included.",
        f"Portfolio: managing the basket together nets {port['diversification_benefit_pct']:.0f}% of the risk away."]:
        st.write("- " + line)


# ---------------------------------------------------------------- downloads
st.subheader("Download")
palm_series = cc.load_series(cc.COMMODITIES[flag]["spot"]).tail(252)
ps = ([d.strftime("%Y-%m-%d") for d in palm_series.index], [round(float(v), 2) for v in palm_series.values])
ch.build_explainer(res, ps, "copilot_model_explained.html")
import copilot_audit
copilot_audit.build(copilot_audit.compute_audit())

d1, d2, d3 = st.columns(3)
with open("copilot_model_explained.html") as f:
    d1.download_button("\U0001F4C4  Full explainer (HTML)", f.read(), "copilot_model_explained.html", "text/html")
with open("copilot_audit.html") as f:
    d2.download_button("\U0001F9FE  Audit document (HTML)", f.read(), "copilot_audit.html", "text/html")
import json
d3.download_button("\U0001F4C1  Results (JSON)", json.dumps(res, indent=2, default=str),
                   "copilot_results.json", "application/json")

st.caption("Illustrative decision-support tool — not financial advice.")
