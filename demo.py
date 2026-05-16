"""Demo: 3 scenarios that exercise ResilientLLM and print a scorecard.

Run with one Groq free-tier key (no card needed). Two real Groq models +
one deliberately broken target form the fallback chain.

Usage:
    cp .env.example .env   # fill in GROQ_API_KEY
    pip install -r requirements.txt
    python demo.py
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from chaos import BurstFault, RandomFault
from resilient_llm import ResilientLLM, Scorecard, Target

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(message)s")
# Silence the noisy httpx INFO log on every Groq POST — it crowds the screen
# recording and adds nothing the resilience story needs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
TFY_URL = os.environ.get("TFY_GATEWAY_URL", "https://gateway.truefoundry.ai")
TFY_KEY = os.environ.get("TFY_API_KEY", "")
if not GROQ_KEY or not TFY_KEY:
    print("ERROR: set GROQ_API_KEY and TFY_API_KEY in .env")
    sys.exit(1)


# Fallback chain priority — TF Gateway first, raw Groq as last resort.
# This is the hackathon story: sponsor product is primary path, but the agent
# *also* survives if TF Gateway itself browns out.
#   1. TF Gateway → groq/llama-3.1-8b-instant   (fast primary, traces in TF UI)
#   2. TF Gateway → groq/llama-3.3-70b-versatile (slower but smarter via TF)
#   3. raw groq llama-3.1-8b-instant            (direct provider — TF-bypass)
TARGETS = [
    Target(
        name="tfy-groq-8b",
        base_url=TFY_URL,
        api_key=TFY_KEY,
        model="groq/llama-3.1-8b-instant",
        max_retries=2,
        base_delay_s=0.4,
        breaker_threshold=3,
        breaker_cooldown_s=15.0,
    ),
    Target(
        name="tfy-groq-70b",
        base_url=TFY_URL,
        api_key=TFY_KEY,
        model="groq/llama-3.3-70b-versatile",
        max_retries=1,
    ),
    Target(
        name="raw-groq-8b",
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_KEY,
        model="llama-3.1-8b-instant",
        max_retries=1,
    ),
]

PROMPT = [
    {"role": "system", "content": "You are terse. One short sentence."},
    {"role": "user", "content": "Define resilience in one sentence."},
]


def run_scenario(label: str, fault_hook=None, n: int = 3) -> Scorecard:
    print(f"\n══════ {label} ══════")
    scorecard = Scorecard()
    client = ResilientLLM(TARGETS, scorecard=scorecard, fault_hook=fault_hook)
    for i in range(n):
        resp, rec = client.chat(PROMPT, max_tokens=40)
        chain = " → ".join(f"{a.target}({'ok' if a.ok else a.err_type})" for a in rec.attempts)
        if rec.ok:
            content = resp.choices[0].message.content.strip().replace("\n", " ")
            print(f"  call {i+1}: OK via {rec.final_target} in {rec.user_latency_ms:.0f}ms — {chain}")
            print(f"          └─ {content[:90]}")
        else:
            print(f"  call {i+1}: FAIL after {rec.user_latency_ms:.0f}ms — {chain}")
    print(scorecard.render())
    return scorecard


def main() -> None:
    # Scenario 1 — Clean baseline: should land on primary every time.
    run_scenario("1) Clean baseline (no chaos)", n=2)

    # Scenario 2 — Burst fault: TF primary hard-fails for 4 calls, breaker trips,
    # traffic shifts to TF secondary.
    burst = BurstFault(target_name="tfy-groq-8b", count=4, status_code=503)
    run_scenario("2) Burst chaos on TF primary (breaker should open)", fault_hook=burst, n=3)

    # Scenario 3 — Both TF Gateway models brown out → fall through to raw provider.
    # This is the "TF Gateway itself went down" story.
    rand = RandomFault(targets={"tfy-groq-8b", "tfy-groq-70b"}, p=0.6, seed=42)
    run_scenario("3) 60% failure across both TF targets (raw-groq saves the day)", fault_hook=rand, n=4)


if __name__ == "__main__":
    main()
