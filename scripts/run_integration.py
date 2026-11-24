"""Print the Golden Test Case result without external calls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow


if __name__ == "__main__":
    case, provider = load_golden_case()
    result = run_integration_workflow(
        case.profile, case.inventory, case.recipes, provider, days=case.days, mock_planner=True,
    )
    print(result.model_dump_json(indent=2))
    sys.exit(0 if result.valid else 1)
