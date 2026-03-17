#!/bin/bash
# Startup script for the FastMCP research hub.

export FASTMCP_TRANSPORT="${FASTMCP_TRANSPORT:-http}"
export FASTMCP_HOST="${FASTMCP_HOST:-0.0.0.0}"
export FASTMCP_PORT="${FASTMCP_PORT:-9000}"

exec python -m mcp_servers.research_hub.server
