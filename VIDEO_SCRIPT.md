# Submission Video Script — 3 minutes

Target: judge sees in the first 30 seconds that the agent really survives
failures, not just claims to. Split-screen throughout the demo body.

## Frame layout for the demo body (Acts 2-3)

```
┌─────────────────────────────┬──────────────────────────────┐
│  LEFT: terminal              │  RIGHT: TF Request Traces    │
│  ─────────────────           │  ──────────────────────       │
│  python demo.py              │  (live dashboard view of      │
│  ... 503 ... 503 ... 503 ... │   /monitoring/request-traces  │
│  fallback to tfy-groq-70b OK │   with latency bars)          │
│  scorecard: 100% success     │                               │
└─────────────────────────────┴──────────────────────────────┘
```

Voice-over below. Total ≈ 180s.

---

## Act 1 — Problem (0:00–0:25) — **25s**

(Slide: TrueFoundry challenge prompt rendered as text, no talking head.)

> "TrueFoundry's hackathon track asks one question: how does your agent behave
> when an LLM server errors out or browns out? Most submissions answer with a
> try/except. We treat it as an engineering question and ship three layers of
> defense — retry, circuit breaker, and a fallback chain that survives even
> the gateway itself going down."

---

## Act 2 — Live demo with chaos (0:25–2:00) — **95s**

(Split screen on. Terminal left, TF dashboard right.)

> "Scenario one: clean baseline. Two calls, both served by the TrueFoundry
> primary path. p95 latency around 900 ms. Now watch the chaos."
> *(pause; let the terminal banner for Scenario 2 appear)*

> "Scenario two: we hard-fail TrueFoundry's llama-8b path with 503 errors.
> The retry layer tries three times" — *(point at left, three 503 lines)* —
> "the circuit breaker opens" — *(highlight 'breaker OPEN, skipping' line)*
> — "and the fallback layer routes to TrueFoundry llama-70b. The user
> request completes." — *(highlight 'OK via tfy-groq-70b in 1.8 s')*

> "All of this is observable: the TrueFoundry Request Traces dashboard on the
> right just got three failed 503s on the 8b model and three successful 70b
> calls — every attempt logged."
> *(switch right pane to show the trace list)*

> "Scenario three: simulate TrueFoundry Gateway itself browning out — 60%
> failure on *both* gateway targets. Our chain has one more fallback: a
> direct connection to the raw provider that bypasses the gateway entirely.
> The agent still answers."

---

## Act 3 — Scorecard + close (2:00–3:00) — **60s**

(Cut back to full-screen terminal showing scorecard output.)

> "We don't ask judges to trust the demo — we hand them numbers."
> *(zoom on the scorecard)*

> "Across all three scenarios: success rate 100%. p95 user latency stays
> under 2 seconds even during burst chaos. Mean time to recovery is roughly
> 660 milliseconds. Fallback triggered on every chaos call without a single
> dropped request."

> "Everything in this demo is reproducible: clone the repo, `pip install`,
> `python demo.py`. Chaos patterns are exposed as a Python module so any
> reviewer can flip a switch and trigger the recovery themselves.
> Thanks for watching."

(End card: GitHub URL + team / contact.)

---

## Recording checklist

- [ ] OBS or QuickTime split-screen preset configured
- [ ] Terminal font ≥ 18pt, dark background, scroll history cleared
- [ ] TF dashboard pre-filtered to `Last 1 hour` so traces are tight
- [ ] `python demo.py` runs in under 30 s end to end (verified ~25 s)
- [ ] No real provider keys visible on screen — `.env` not opened, `printenv` not run
- [ ] Audio normalized to -16 LUFS
- [ ] Cut to ≤ 3 minutes; no intro/outro slate longer than 2 s
