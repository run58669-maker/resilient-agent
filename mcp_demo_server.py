"""Tiny MCP server for the demo.

Exposes one `lookup_status(item_id)` tool that returns a deterministic
status string tagged with the server's name so we can see in logs which
server actually served a given call. Run two instances on different ports
to demo MCP-side failover and breaker behaviour.

Usage:
    set MCP_TAG=primary
    set MCP_PORT=8011
    python mcp_demo_server.py
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

TAG = os.environ.get("MCP_TAG", "default")
PORT = int(os.environ.get("MCP_PORT", "8011"))
HOST = os.environ.get("MCP_HOST", "127.0.0.1")

mcp = FastMCP(
    f"status-lookup-{TAG}",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def lookup_status(item_id: str) -> str:
    """Return a short status line for an item id. Used by the demo agent."""
    return f"item={item_id} status=OK served_by={TAG}"


if __name__ == "__main__":
    import uvicorn

    print(f"mcp-demo-server[{TAG}] on http://{HOST}:{PORT}/mcp/")
    uvicorn.run(mcp.streamable_http_app(), host=HOST, port=PORT, log_level="warning")
