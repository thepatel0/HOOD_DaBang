"""
HOOD DaBang — live MCP HTTP transport (Brief §34).

Speaks MCP JSON-RPC 2.0 over streamable HTTP to the Robinhood Agentic MCP at
https://agent.robinhood.com/mcp/trading. Implements the handshake (initialize ->
notifications/initialized), tools/list, and tools/call. Conforms to the
MCPTransport protocol so it drops into RobinhoodMCPClient unchanged.

IMPORTANT (§34 — verify, never assume): the ACTUAL tool names and parameter
schemas must be confirmed against the live server via `client.discover()` +
`client.validate_tool_map()` before any real order. This transport handles the
protocol; it does not assume tool names.

Auth: the Robinhood Agentic MCP is added to Claude Code via
`claude mcp add robinhood-trading --transport http ...`. For a standalone Python
client the operator supplies the bearer token / headers configured for their
account (passed via `headers`). Tested here against httpx.MockTransport so the
JSON-RPC framing is verified without network.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


class MCPHttpError(RuntimeError):
    pass


class HttpMCPTransport:
    def __init__(self, url: str = "https://agent.robinhood.com/mcp/trading",
                 headers: Optional[Dict[str, str]] = None, client=None,
                 timeout: float = 30.0):
        import httpx
        self.url = url
        self._id = 0
        self._session_id: Optional[str] = None
        self._initialized = False
        base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        base_headers.update(headers or {})
        self.http = client or httpx.Client(timeout=timeout, headers=base_headers)

    # ----- JSON-RPC plumbing -------------------------------------------- #
    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        resp = self.http.post(self.url, json=payload, headers=headers)
        # capture session id from the initialize response
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        if resp.status_code >= 400:
            raise MCPHttpError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        # notifications return 202/204 with no body
        if resp.status_code in (202, 204) or not (resp.content or b"").strip():
            return {}
        return self._parse_body(resp)

    @staticmethod
    def _parse_body(resp) -> Dict[str, Any]:
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            # parse SSE: take the last `data:` JSON line
            data_obj = {}
            for line in resp.text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    try:
                        data_obj = json.loads(line[5:].strip())
                    except ValueError:
                        continue
            return data_obj
        return resp.json()

    def _request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        body = self._post({"jsonrpc": "2.0", "id": self._next_id(),
                           "method": method, "params": params or {}})
        if "error" in body and body["error"]:
            raise MCPHttpError(f"{method} error: {body['error']}")
        return body.get("result", {})

    def _notify(self, method: str, params: Dict[str, Any] = None) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params or {}})

    # ----- handshake ----------------------------------------------------- #
    def initialize(self) -> Dict[str, Any]:
        result = self._request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "hood-dabang", "version": "1.0.0"},
        })
        self._notify("notifications/initialized")
        self._initialized = True
        return result

    def _ensure_init(self) -> None:
        if not self._initialized:
            self.initialize()

    # ----- MCPTransport protocol ---------------------------------------- #
    def list_tools(self) -> List[str]:
        self._ensure_init()
        result = self._request("tools/list")
        return [t["name"] for t in result.get("tools", [])]

    def call(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_init()
        result = self._request("tools/call", {"name": tool, "arguments": params})
        # MCP returns content blocks; structured tools usually include a JSON block.
        content = result.get("content", [])
        for block in content:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (ValueError, KeyError):
                    return {"text": block.get("text", "")}
        # some servers return structuredContent directly
        if "structuredContent" in result:
            return result["structuredContent"]
        return result
