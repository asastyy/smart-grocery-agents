"""Replay captured public responses without network or refreshed timestamps."""
from datetime import datetime
import json
from pathlib import Path

from smart_grocery.retail.vkusvill import VkusVillProvider
from smart_grocery.tools.grocery_provider import ProviderUnavailable


DEFAULT_CAPTURE = Path(__file__).resolve().parents[3] / "fixtures" / "retail" / "vkusvill_capture.json"


class ReplayClient:
    def __init__(self, path: Path):
        capture = json.loads(path.read_text(encoding="utf-8"))
        self.records = capture["records"]
        self.last_retrieved_at = datetime.fromisoformat(self.records[0]["retrieved_at"])

    def call_tool(self, name: str, arguments: dict) -> dict:
        for record in self.records:
            if record["tool"] == name and record["arguments"] == arguments:
                self.last_retrieved_at = datetime.fromisoformat(record["retrieved_at"])
                result = record["response"]
                payload = json.loads(result["content"][0]["text"])
                return payload["data"]
        raise ProviderUnavailable("response_not_in_snapshot")

    def close(self):
        pass


def snapshot_provider(path: Path = DEFAULT_CAPTURE) -> VkusVillProvider:
    client = ReplayClient(path)
    return VkusVillProvider(client, clock=lambda: client.last_retrieved_at)
