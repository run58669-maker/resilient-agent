"""Demo: ResilientMCP under MCP server failure.

Spawns two `mcp_demo_server.py` instances on different ports (the "primary"
and "fallback" MCP servers), then runs three scenarios:

  1) Clean baseline — both servers up, traffic stays on primary
  2) Primary errors out — burst MCP errors trip the breaker, fallback takes over
  3) Primary brownout — high latency on first attempts, retries pick up the slack

This is the MCP-side counterpart to demo.py. The two scorecards together cover
the full challenge prompt: "how does your agent behave when an MCP server starts
erroring out? An LLM server goes down?".
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from chaos import MCPTimeoutFault, MCPToolFault
from resilient_mcp import MCPTarget, ResilientMCP, Scorecard

logging.basicConfig(level=logging.INFO, format="%(message)s")

ROOT = Path(__file__).parent
PY = sys.executable

PRIMARY_PORT = 8011
FALLBACK_PORT = 8012


def spawn_server(tag: str, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["MCP_TAG"] = tag
    env["MCP_PORT"] = str(port)
    p = subprocess.Popen(
        [PY, str(ROOT / "mcp_demo_server.py")],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # poll until the port answers
    import socket
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return p
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"mcp server {tag}:{port} did not come up in 10s")


async def run_scenario(label: str, targets: list[MCPTarget], fault_hook=None, n: int = 3):
    print(f"\n══════ {label} ══════")
    scorecard = Scorecard()
    client = ResilientMCP(targets, scorecard=scorecard, fault_hook=fault_hook)
    for i in range(n):
        result, rec = await client.call_tool("lookup_status", {"item_id": f"ITEM-{i+1:03}"})
        chain = " → ".join(f"{a.target}({'ok' if a.ok else a.err_type})" for a in rec.attempts)
        if rec.ok:
            # MCP result is a structured response — pull the text
            try:
                txt = result.content[0].text if result and result.content else ""
            except Exception:
                txt = str(result)[:90]
            print(f"  call {i+1}: OK via {rec.final_target} in {rec.user_latency_ms:.0f}ms — {chain}")
            print(f"          └─ {txt[:90]}")
        else:
            print(f"  call {i+1}: FAIL after {rec.user_latency_ms:.0f}ms — {chain}")
    print(scorecard.render())


async def main():
    print("spawning mcp servers...")
    primary = spawn_server("primary", PRIMARY_PORT)
    fallback = spawn_server("fallback", FALLBACK_PORT)
    print(f"  primary  :{PRIMARY_PORT}  pid={primary.pid}")
    print(f"  fallback :{FALLBACK_PORT}  pid={fallback.pid}")

    targets = [
        MCPTarget(name="mcp-primary",  url=f"http://127.0.0.1:{PRIMARY_PORT}/mcp/",
                  max_retries=2, breaker_threshold=3, breaker_cooldown_s=15.0),
        MCPTarget(name="mcp-fallback", url=f"http://127.0.0.1:{FALLBACK_PORT}/mcp/",
                  max_retries=1),
    ]

    try:
        # Scenario 1 — clean
        await run_scenario("1) Clean baseline (both servers up)", targets, n=2)

        # Scenario 2 — primary errors out (chaos hook raises before the real call)
        burst = MCPToolFault(target_name="mcp-primary", count=4,
                             error_message="primary MCP returning 500")
        await run_scenario(
            "2) Primary MCP errors out (breaker should open)",
            targets, fault_hook=burst, n=3,
        )

        # Scenario 3 — primary brownout (slow first attempts)
        slow = MCPTimeoutFault(target_name="mcp-primary", latency_s=2.0)
        await run_scenario(
            "3) Primary MCP brownout (high latency on first attempt)",
            targets, fault_hook=slow, n=3,
        )
    finally:
        for p in (primary, fallback):
            try: p.terminate(); p.wait(timeout=3)
            except Exception: p.kill()
        print("\nservers stopped.")


if __name__ == "__main__":
    asyncio.run(main())
