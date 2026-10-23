"""Run role 1 + role 2 + role 3 against the actual prepared Food.com data."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_grocery.workflow.foodcom import run_foodcom_workflow

if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fixtures/request_foodcom.json"
    result = run_foodcom_workflow(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2))
