# Resilient Agent — DevNetwork 2026 "Resilient Agents" Track

Submission for the **TrueFoundry** challenge at DevNetwork [AI + ML] Hackathon
2026: *"How does your agent behave when an MCP server starts erroring out?
An LLM server goes down? OpenAI or Claude errors out or browns out?"*

We treat that question as an **engineering** question, not a config question:
we built a client-side resilience layer in front of the TrueFoundry AI Gateway
that survives every layer of failure we can throw at it — including the
TrueFoundry Gateway itself going down.

## TL;DR

The same resilience pattern is applied to **both** legs of the challenge
prompt — LLM brownouts and MCP server errors — by two parallel classes
that share Scorecard / breaker / retry plumbing:

```
   ┌─ ResilientLLM ─────────────┐    ┌─ ResilientMCP ─────────────┐
   │  retry → breaker → chain   │    │  retry → breaker → chain   │
   └────────┬───────────────────┘    └────────┬───────────────────┘
            ▼                                  ▼
   tfy-groq-8b  tfy-groq-70b  raw-groq-8b      mcp-primary  mcp-fallback
   (TF GW)      (TF GW)       (direct)         (port 8011)  (port 8012)
            │                                   │
            └─────────► TrueFoundry Request Traces ◄────── (LLM side)
```

3 layers of defense, every attempt observable in the TF dashboard:

| Layer | What it does | Configured per-target? |
| --- | --- | --- |
| **Retry + exponential backoff** | Re-attempt transient errors with jitter | yes |
| **Circuit breaker** | Stop hammering a target after N consecutive failures, cool down, half-open probe | yes |
| **Fallback chain** | If a target's breaker is open or it exhausts retries, the next target picks up | priority-ordered |

The chain ends in a **raw provider** target on purpose: if the TrueFoundry
Gateway itself goes down (the "OpenAI or Claude errors out" scenario), the
agent can still answer.

## Quick start

```bash
git clone https://github.com/run58669-maker/resilient-agent.git
cd resilient-agent
pip install -r requirements.txt
cp .env.example .env  # fill in GROQ_API_KEY + TFY_API_KEY
python demo.py
```

You'll see three LLM scenarios run end-to-end:

1. **Clean baseline** — no chaos, primary serves everything
2. **Burst chaos on primary** — primary hard-fails 4× → breaker opens → fallback to secondary
3. **Gateway brownout** — 60% random failure on both TF targets → raw provider picks up

Then run the MCP counterpart — two local MCP servers (primary + fallback) under
the same resilience layer:

```bash
python demo_mcp.py
```

Three MCP-side scenarios:

1. **Clean baseline** — primary MCP serves everything
2. **Primary MCP errors out** — `MCPToolFault` raises 4× → breaker opens → fallback MCP picks up
3. **Primary MCP brownout** — `MCPTimeoutFault` injects 2 s latency on first attempt

Each scenario prints a **Resilience Scorecard**:

```
─── Resilience Scorecard ───
  total calls          : 3
  success rate         : 100.0%
  user latency p50/p95 :    430 /   1976 ms
  avg user latency     :     903 ms
  fallback trigger rate: 100.0%
  MTTR (recovered calls):    661 ms
  by target:
    tfy-groq-70b           served=  3  attempts=  3
    tfy-groq-8b            served=  0  attempts=  3
```

## Files

```
resilient_llm.py    ← LLM core: Target / ResilientLLM / _Breaker / Scorecard
resilient_mcp.py    ← MCP core: MCPTarget / ResilientMCP (reuses _Breaker, Scorecard)
chaos.py            ← BurstFault / RandomFault / BrownoutFault (LLM)
                      MCPToolFault / MCPTimeoutFault (MCP)
demo.py             ← 3-scenario runner for the LLM side
demo_mcp.py         ← 3-scenario runner for the MCP side (spawns local servers)
mcp_demo_server.py  ← tiny FastMCP server with a lookup_status tool
.env.example        ← credentials template
```

## How the chain configuration looks

```python
TARGETS = [
    Target(
        name="tfy-groq-8b",
        base_url=TFY_URL,                       # TrueFoundry Gateway
        api_key=TFY_KEY,                        # PAT from Access page
        model="groq/llama-3.1-8b-instant",
        max_retries=2,
        breaker_threshold=3,
        breaker_cooldown_s=15.0,
    ),
    Target(
        name="tfy-groq-70b",
        base_url=TFY_URL,
        api_key=TFY_KEY,
        model="groq/llama-3.3-70b-versatile",
    ),
    Target(
        name="raw-groq-8b",                     # TF-bypass last resort
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_KEY,
        model="llama-3.1-8b-instant",
    ),
]
```

Order = priority. Add or reorder targets; nothing else changes.

## Observability

Every attempt — successes *and* failures — flows through the TrueFoundry AI
Gateway and shows up in **AI Monitoring → Request Traces**. The dashboard is
how a developer (or a hackathon judge) verifies a posteriori which model
actually served a given user request, and how long the retry/fallback path
took. The client-side scorecard answers the same question quantitatively
across many calls.

## Why this is the right shape for the challenge

The challenge asks *"how does your agent behave when an MCP server / LLM server
errors out or browns out?"* — that is a runtime-behavior question. We answer
it three ways:

1. **Fault injection is built-in** (`chaos.py`). A reviewer can flip on any of
   three fault patterns (burst, random, brownout) and watch recovery happen,
   not just read about it.
2. **Recovery is quantified** (`Scorecard`). MTTR, success rate, p95 latency,
   and per-target serve counts mean "did it work?" has a numeric answer.
3. **Survival of the gateway itself**. Because the last target bypasses TF and
   talks directly to the provider, the agent answers even if the gateway is
   the thing that's down. That's the strict reading of the challenge prompt
   — and a path that disappears the moment you bind to a single endpoint.
