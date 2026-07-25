# Commodity Copilot — Solution Design (Kearney Case 4)

*An AI copilot that helps a cross-functional buying council decide **what, when, how much, and whether to hedge** across multiple commodities — acting autonomously inside hard guardrails.*

---

## 0. Built from your choices

| # | Design lever | Your choice | How it shows up in the solution |
|---|---|---|---|
| 1 | Core thesis | **AI copilot for buyers** | Product framed as a copilot that augments human judgment + speed |
| 2 | Audience | **Cross-functional council** | Procurement + Finance/Treasury + Risk jointly govern; council sets the guardrails |
| 3 | Scope | **Multi-commodity platform** | One engine, many commodities (palm, crude, silver, FX, freight); portfolio view |
| 4 | AI autonomy | **Autonomous within guardrails** | Copilot auto-executes inside caps; humans handle exceptions |
| 5 | Diagnosis | **4 decisions (spine) × risk types (cross-cut)** | Problem framed by what/when/how-much/hedge, each mapped to the risks it manages |
| 6 | Framework | **Sense → Score → Decide → Act** (spine) + **4 questions** (the "Decide" output) | Pipeline shows *how* it works; 4 answers show *what* it produces |
| 7 | Auto-scope | **Full within caps** | Everything inside volume/price/hedge caps runs automatically; council reviews exceptions |
| 8 | Horizon | **Rolling 6-month**, re-optimized | Coverage plan for the next 6 months, re-solved each week |
| 9 | Scenario method | **Probabilistic (Monte Carlo)** | Thousands of price paths → full cost distribution, not 3 points |
| 10 | Headline metric | **Composite: cost + stability** | New metric **RALC** (below) that trades expected cost against cost stability |
| 11 | Risk appetite | **3 presets** | Conservative / Balanced / Aggressive → set the risk-aversion dial + the caps |
| 12 | Proof | **Backtest on history** | Replay the engine on past data; show it beats naive buying |

---

## 1. The product in one line

**"Commodity Copilot"** — a Sense→Score→Decide→Act engine that turns market noise into
governed buy & hedge decisions across a portfolio of commodities, and executes them
automatically inside limits the council sets.

## 2. Problem diagnosis (the "where it breaks today")

Spine = the **four decisions**; cross-cut = the **five risk exposures** each one carries.

| Decision | Breaks down today because… | Risks it must manage |
|---|---|---|
| **What** to buy | grade/origin picked on habit, not landed economics | price, supply |
| **When** to buy | timing is gut-feel; buyers chase or freeze | price, FX |
| **How much** to cover | one-size coverage; no link to demand/inventory | demand, supply |
| **Whether** to hedge | hedging is ad-hoc, no policy, no budget link | price, FX, freight |

*One-line so-what:* reactive buying leaks margin **and** makes the budget unpredictable —
the copilot fixes both at once.

## 3. Architecture — Sense → Score → Decide → Act

```
        ┌───────────────── AI COPILOT LAYER (wraps every stage) ─────────────────┐
        │  market sensing · probabilistic forecasting · anomaly alerts · NL Q&A   │
        └────────────────────────────────────────────────────────────────────────┘
 SENSE            SCORE                 DECIDE                     ACT
 ─────            ─────                 ──────                     ───
 prices, curve →  6 signals per     →  the 4 answers:         →  auto-execute
 FX, freight,     commodity →           • buy now / wait          within caps;
 fundamentals,    0-100 sub-scores      • coverage % (near/mid)   escalate
 demand, stock    per commodity         • hedge ratio+instrument  exceptions to
 (multi-cmdty)                          • trigger playbook        the council
                                        run per commodity +       + monitor &
                                        across the portfolio      back-test
```

- **Multi-commodity:** the same pipeline runs per commodity, then a **portfolio layer**
  nets correlated and natural-hedge positions (e.g. crude ↔ freight, palm ↔ substitutes).
- **Rolling 6-month:** the plan is re-solved weekly; only the *delta* is acted on.

## 4. How AI works in it (copilot + autonomous-in-caps)

- **Copilot** (always): senses news/reports (MPOB, USDA, duty notices), assigns
  probabilities to scenarios, explains every call in plain English, answers "what-if" Q&A.
- **Autonomous within caps** (the guardrails): the copilot **auto-executes** any buy or
  hedge that sits **inside** the council's caps (max hedge %, max horizon, max single-order
  size, Cost-at-Risk limit). Anything outside → **proposed to the council** (1-click approve).
- **Accountability:** every auto-action is logged with its rationale; a **kill-switch** and
  daily exposure report keep the council in control.

## 5. The headline metric — RALC (your "cost + stability" ask)

You said: *don't optimize profit/cost alone — stability matters too; combine the two.*
So the engine optimizes a **certainty-equivalent cost**:

> **RALC (Risk-Adjusted Landed Cost) = E[Cost] + λ · σ[Cost]**

- `E[Cost]` = expected total procurement cost (mean of the Monte-Carlo distribution)
- `σ[Cost]` = its volatility (the stability term)
- `λ` = risk-aversion dial, **set by the 3 presets**: Conservative ≈ 1.5, Balanced ≈ 0.8,
  Aggressive ≈ 0.3

The engine **picks the strategy that minimizes RALC** (subject to the caps). This literally
trades cheap-but-jumpy against slightly-dearer-but-steady, tuned to appetite.

**Slide-ready visual:** an **efficient frontier of buying strategies** — plot each candidate
(do-nothing, phase+hedge, lock-all, …) on *Expected Cost* (x) vs *Cost Volatility* (y); the
engine chooses the point on the frontier that matches the preset's λ. For communication we
also show a 0-100 **Buy-Quality Score** = how much cost-risk the chosen plan removes vs naive
spot buying.

## 6. Risk appetite → guardrails (3 presets)

| Preset | λ (RALC) | Max hedge ratio | Max horizon | Auto-execute cap |
|---|---|---|---|---|
| Conservative | 1.5 | 80% | 6 mo | larger auto-band |
| Balanced | 0.8 | 50% | 6 mo | medium |
| Aggressive | 0.3 | 30% | 3 mo | small (more human sign-off) |

The council picks the preset per commodity; the preset sets both the optimizer's λ **and**
the hard caps the autonomy runs inside.

## 7. Proof — backtest

Replay the engine on the last 1–2 years of the real data files and report, vs a
**naive "buy spot each month"** baseline: (a) average landed cost, (b) cost volatility,
(c) Cost-at-Risk, (d) worst-month, (e) % of trigger calls that were right. Target headline:
*"same-or-lower cost at materially lower risk."*

## 8. Governance & operating model

- **Decision rights:** copilot acts inside caps; council approves out-of-band; CFO signs
  anything above the hedge-policy ceiling.
- **Cadence:** weekly full re-solve + real-time trigger alerts + monthly back-test review.
- **Audit:** every decision stores its signals, RALC, and rationale.

---

## DEFAULTS I filled for the 8 unanswered questions (change any)

| Open question | My default |
|---|---|
| Implementation roadmap | Crawl-walk-run: 1 commodity pilot → 3 commodities → portfolio + autonomy |
| Data foundation | ERP demand/inventory + market feed (Bloomberg/Refinitiv) + news/alt-data for AI |
| "Next-gen" differentiator | The portfolio RALC optimizer + agentic auto-execution in caps |
| Governance depth | Council + policy caps + kill-switch + audit trail (as above) |
| Deck flow | Thesis → diagnosis → architecture → analytics/RALC → impact/backtest → roadmap |
| Slide count | 2 dense Kearney slides (as you're building), or 5-6 if allowed |
| Success KPIs | Landed cost, Cost-at-Risk, budget variance, % auto-executed, decision cycle time |
| Title-slide lead | Lead with the copilot thesis + the RALC "cost *and* stability" hook |
