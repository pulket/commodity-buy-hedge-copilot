# Commodity Copilot — an AI Buy / Hedge Decision Engine

A transparent **Sense → Score → Decide → Act** engine that helps a procurement team
decide **what to buy, when, how much, and whether to hedge** across a basket of
commodities — combining a **financial track** and a **supply-chain track**, and choosing
the cheapest path on a **risk-adjusted (RALC)** basis.

> Illustrative decision-support tool — **not financial advice**.

## What it does

| Stage | What happens |
|---|---|
| **Sense** | Reads 6 market signals per commodity (price %ile, momentum, volatility, forward curve, FX, freight) **and** the supply-chain inputs (demand & its volatility from a sales file, inventory, lead time, suppliers). |
| **Score** | Blends the signals into a 0–100 **Buy-Now score** → buy / phase / wait. |
| **Decide** | Runs a **Monte-Carlo** (20k price paths) and picks the cover% + hedge% mix that minimises **RALC = E\[Cost] + λ·SD\[Cost]** on the efficient frontier. A **Wagner-Whitin dynamic program** then decides *when* to buy (physical, with holding cost & lead time) vs **hedge**. |
| **Act** | Auto-executes inside the council's caps, else escalates; supply-continuity (must-cover) comes first. |

It runs for palm oil, crude and silver, then **nets the risk across the portfolio**.

## Run the web app

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open <http://localhost:8501>. Use the sidebar to set the risk appetite, holding cost
and horizon, optionally **upload your own sales file**, and click **Run**.

### Deploy for free (any browser, anywhere)
Push this repo to GitHub and connect it on **[share.streamlit.io](https://share.streamlit.io)**
(main file: `app.py`). You get a public URL you can open anytime.

## Run the model from the command line

```bash
python commodity_copilot.py     # prints the full decision report, writes copilot_results.json
python copilot_html.py          # builds the explainer + Kearney-style slides (HTML)
python copilot_audit.py         # builds the full audit document (every number, traced)
python make_ppt_editable.py     # builds an editable PowerPoint of the slides
```

## Files

| File | Purpose |
|---|---|
| `commodity_copilot.py` | The model — signals, Monte-Carlo, RALC, supply chain, timing DP, portfolio. |
| `app.py` | Streamlit web interface. |
| `copilot_html.py` | Builds the detailed explainer + the 2-slide deck (HTML). |
| `copilot_audit.py` | Builds the audit document — every number traced to the raw data. |
| `make_ppt.py` / `make_ppt_editable.py` | Export the slides to PowerPoint (image / fully-editable). |
| `Mayank_*.xlsx`, `Priya_BDIY_*.xlsx` | Daily price / FX / freight series. |
| `Lens_Sales_Sample.xlsx` | **Anonymised sample** sales file (demand). |
| `Palm Oil World Supply and Distribution.csv` | Supply-demand fundamentals. |

## A note on data
The sales file in this repo (`Lens_Sales_Sample.xlsx`) is **fully synthetic / anonymised** —
only its monthly demand run-rate and volatility resemble reality. No real customer, sales-rep
or revenue data is included. To use your own data, upload your sales file in the app.

---
Built as a case-study prototype. Market/price series are illustrative.
