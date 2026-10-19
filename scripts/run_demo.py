"""Run the real workflow with a JSON request, without Streamlit."""
import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env", override=False)

from smart_grocery.schemas.models import PlanningRequest
from smart_grocery.workflow.runner import run_workflow_with_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", nargs="?", type=Path, default=ROOT / "examples/request.json")
    args = parser.parse_args()
    try:
        request = PlanningRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("Cannot read a valid request JSON.", file=sys.stderr)
        return 2
    run = run_workflow_with_trace(request)
    print(json.dumps(run.model_dump(), ensure_ascii=False, indent=2))
    return 0 if run.result is not None and run.result.valid and run.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
