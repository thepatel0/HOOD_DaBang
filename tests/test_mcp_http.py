import json
import unittest

import httpx

from src.mcp_http import HttpMCPTransport, MCPHttpError
from src.mcp_client import RobinhoodMCPClient


def make_handler(tools=None, tool_results=None, sse=False):
    tools = tools or ["get_account_info", "get_quote", "place_order"]
    tool_results = tool_results or {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body.get("method")
        headers = {"Mcp-Session-Id": "sess-123"}

        if method == "notifications/initialized":
            return httpx.Response(202, headers=headers)

        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {},
                      "serverInfo": {"name": "robinhood", "version": "1.0"}}
        elif method == "tools/list":
            result = {"tools": [{"name": t} for t in tools]}
        elif method == "tools/call":
            name = body["params"]["name"]
            payload = tool_results.get(name, {"ok": True})
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
        else:
            return httpx.Response(404, json={"error": "unknown"})

        envelope = {"jsonrpc": "2.0", "id": body.get("id"), "result": result}
        if sse:
            text = f"event: message\ndata: {json.dumps(envelope)}\n\n"
            return httpx.Response(200, text=text,
                                  headers={**headers, "content-type": "text/event-stream"})
        return httpx.Response(200, json=envelope, headers=headers)

    return handler


def transport(**kw):
    client = httpx.Client(transport=httpx.MockTransport(make_handler(**kw)))
    return HttpMCPTransport(client=client)


class TestHttpMCP(unittest.TestCase):
    def test_initialize_and_session(self):
        t = transport()
        t.initialize()
        self.assertTrue(t._initialized)
        self.assertEqual(t._session_id, "sess-123")

    def test_list_tools(self):
        t = transport()
        self.assertIn("place_order", t.list_tools())

    def test_call_parses_json_content(self):
        t = transport(tool_results={"get_account_info":
                                    {"cash": 1500.0, "equity": 1500.0,
                                     "buying_power": 1500.0}})
        out = t.call("get_account_info", {})
        self.assertEqual(out["equity"], 1500.0)

    def test_sse_response_parsed(self):
        t = transport(sse=True, tool_results={"get_quote":
                                              {"bid": 99.9, "ask": 100.1, "last": 100.0}})
        out = t.call("get_quote", {"ticker": "AAPL"})
        self.assertEqual(out["last"], 100.0)

    def test_integrates_with_mcp_client(self):
        # the real wrapper drives the HTTP transport end to end
        t = transport(tool_results={"get_account_info":
                                    {"cash": 1500.0, "equity": 1500.0,
                                     "buying_power": 1500.0}})
        client = RobinhoodMCPClient(t)
        acct = client.get_account()
        self.assertEqual(acct.equity, 1500.0)
        # discovery flags tools the mock server doesn't expose (§34 safety)
        missing = client.validate_tool_map()
        self.assertIn("place_stop_order", missing)
        self.assertNotIn("get_account", missing)

    def test_http_error_raises(self):
        def handler(request):
            return httpx.Response(500, text="boom")
        c = httpx.Client(transport=httpx.MockTransport(handler))
        t = HttpMCPTransport(client=c)
        with self.assertRaises(MCPHttpError):
            t.initialize()


if __name__ == "__main__":
    unittest.main()
