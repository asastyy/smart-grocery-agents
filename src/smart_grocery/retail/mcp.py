"""Bounded MCP HTTP client. No order/payment/account tools are exposed."""
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from smart_grocery.tools.grocery_provider import ProviderUnavailable


PUBLIC_TOOLS = frozenset({
    "vkusvill_products_search", "vkusvill_product_details", "vkusvill_product_analogs",
    "vkusvill_products_discount", "vkusvill_cart_link_create",
})


def decode_rpc(text: str) -> dict:
    """Streamable HTTP can return ordinary JSON or SSE data events."""
    try:
        value = json.loads(text)
    except ValueError:
        events = text.replace("\r\n", "\n").split("\n\n")
        value = None
        for event in events:
            data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
            if not data:
                continue
            try:
                candidate = json.loads(data)
            except ValueError:
                continue
            if isinstance(candidate, dict) and ("result" in candidate or "error" in candidate):
                value = candidate
                break
    if not isinstance(value, dict):
        raise ProviderUnavailable("invalid_mcp_response")
    return value


class MCPClient:
    def __init__(self, endpoint: str = "https://mcp.vkusvill.ru/mcp", *, token: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use an HTTPS MCP endpoint without credentials or query parameters")
        self.endpoint = endpoint
        self._client = httpx.Client(timeout=20, follow_redirects=False, transport=transport)
        self._headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = "Bearer " + token
        self._started = False
        self._id = 0
        self.responses: list[dict] = []  # public result payloads; never request headers or auth responses

    def close(self):
        self._client.close()

    def _post(self, method: str, params: dict | None = None, *, notification: bool = False) -> dict:
        self._id += 1
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notification:
            body["id"] = self._id
        try:
            response = self._client.post(self.endpoint, headers=self._headers, json=body)
            if response.status_code in (401, 403):
                raise ProviderUnavailable("authorization_required")
            if response.status_code == 429:
                raise ProviderUnavailable("rate_limited")
            response.raise_for_status()
            if response.headers.get("Mcp-Session-Id"):
                self._headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
            if notification:
                return {}
            data = decode_rpc(response.text)
            if data.get("id") != body["id"] or "error" in data or "result" not in data:
                raise ProviderUnavailable("mcp_protocol_error")
            return data["result"]
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise ProviderUnavailable("mcp_transport_error") from None

    def start(self):
        if not self._started:
            self._post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                      "clientInfo": {"name": "smart-grocery-retail", "version": "0.1.0"}})
            self._post("notifications/initialized", notification=True)
            self._started = True

    def list_tools(self) -> list[dict]:
        self.start()
        result = self._post("tools/list", {})
        if not isinstance(result.get("tools"), list):
            raise ProviderUnavailable("invalid_tool_inventory")
        return result["tools"]

    def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in PUBLIC_TOOLS:
            raise ValueError("Tool is outside the retail allowlist")
        self.start()
        result = self._post("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise ProviderUnavailable("mcp_tool_error")
        payload = result.get("structuredContent")
        if payload is None:
            blocks = result.get("content", [])
            text = "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")
            try:
                payload = json.loads(text)
            except (ValueError, TypeError):
                raise ProviderUnavailable("invalid_tool_payload") from None
        if not isinstance(payload, dict) or payload.get("ok") is False:
            raise ProviderUnavailable("invalid_tool_payload")
        self.responses.append({"tool": name, "arguments": arguments, "response": result,
                               "retrieved_at": datetime.now(timezone.utc).isoformat()})
        return payload.get("data", payload)
