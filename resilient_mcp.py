"""ResilientMCP — the resilience layer applied to MCP tool calls.

Same three concentric layers as ResilientLLM (retry → breaker → fallback chain),
just wrapping `ClientSession.call_tool` over streamable-http instead of a chat
completions call. Shares Scorecard / _Breaker / AttemptRecord / CallRecord with
resilient_llm so the demo reports a unified set of metrics across MCP failures
and LLM failures.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from resilient_llm import AttemptRecord, CallRecord, Scorecard, _Breaker

log = logging.getLogger("resilient_mcp")


@dataclass
class MCPTarget:
    """One MCP server in the fallback chain. URL points at /mcp/ endpoint."""
    name: str
    url: str
    max_retries: int = 2
    base_delay_s: float = 0.4
    breaker_threshold: int = 3
    breaker_cooldown_s: float = 30.0


# Fault hook signature matches the LLM side so chaos.py functions can target
# either layer uniformly. The hook can raise to simulate a failure or sleep
# to simulate a brownout.
MCPFaultHook = Callable[[MCPTarget, int], None]


class ResilientMCP:
    """Multi-server MCP client with retry → breaker → fallback chain."""

    def __init__(
        self,
        targets: list[MCPTarget],
        scorecard: Optional[Scorecard] = None,
        fault_hook: Optional[MCPFaultHook] = None,
    ):
        if not targets:
            raise ValueError("need at least one MCP target")
        self.targets = targets
        self.scorecard = scorecard or Scorecard()
        self.fault_hook = fault_hook
        self._breakers: dict[str, _Breaker] = {
            t.name: _Breaker(t.breaker_threshold, t.breaker_cooldown_s) for t in targets
        }

    async def _call_one(self, target: MCPTarget, tool_name: str, args: dict) -> Any:
        async with streamablehttp_client(target.url) as (read, write, _meta):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, args)

    async def call_tool(
        self, tool_name: str, arguments: dict
    ) -> tuple[Optional[Any], CallRecord]:
        """Invoke an MCP tool across the chain. Returns (result, CallRecord)."""
        call_start = time.monotonic()
        rec = CallRecord(ok=False, user_latency_ms=0.0, final_target=None, final_model=None)

        for tgt_idx, tgt in enumerate(self.targets):
            breaker = self._breakers[tgt.name]
            if not breaker.allow():
                log.info("[%s] breaker OPEN, skipping", tgt.name)
                continue

            for attempt in range(1, tgt.max_retries + 2):
                t0 = time.monotonic()
                err_type: Optional[str] = None
                err_msg: Optional[str] = None
                result: Any = None

                try:
                    if self.fault_hook is not None:
                        self.fault_hook(tgt, attempt)
                    result = await self._call_one(tgt, tool_name, arguments)
                except Exception as e:
                    err_type, err_msg = type(e).__name__, str(e)[:160]

                latency_ms = (time.monotonic() - t0) * 1000
                ok = err_type is None
                rec.attempts.append(
                    AttemptRecord(tgt.name, tool_name, attempt, ok, latency_ms, err_type, err_msg)
                )

                if ok:
                    breaker.record_success()
                    rec.ok = True
                    rec.final_target = tgt.name
                    rec.final_model = tool_name
                    rec.fallback_jumps = tgt_idx
                    rec.user_latency_ms = (time.monotonic() - call_start) * 1000
                    self.scorecard.calls.append(rec)
                    return result, rec

                breaker.record_failure()
                if attempt <= tgt.max_retries:
                    sleep_s = tgt.base_delay_s * (2 ** (attempt - 1)) + random.uniform(0, 0.1)
                    log.info(
                        "[%s] try %d failed (%s); retry in %.2fs",
                        tgt.name, attempt, err_type, sleep_s,
                    )
                    await asyncio.sleep(sleep_s)

        rec.user_latency_ms = (time.monotonic() - call_start) * 1000
        rec.fallback_jumps = len(self.targets) - 1
        self.scorecard.calls.append(rec)
        return None, rec
