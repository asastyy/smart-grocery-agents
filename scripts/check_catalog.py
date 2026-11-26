"""Check the extended catalogue, reproduce source transforms and strict profile."""
import argparse
import gzip
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from smart_grocery.catalog.wikibooks import build_catalog
from smart_grocery.catalog.loader import load_catalog,planning_recipes
from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild',action='store_true')
    args=parser.parse_args()
    folder=ROOT/'data/catalog'
    report=json.loads((folder/'quality_report.json').read_text())
    records=load_catalog()
    assert len(records)==report['catalog_records']
    assert len({r['recipe_id'] for r in records})==len(records)
    assert all(r['allergens_status']=='unknown' and r['allergens'] is None for r in records)
    case,provider=load_golden_case()
    result=run_integration_workflow(case.profile,case.inventory,planning_recipes(),provider,days=case.days,mock_planner=True)
    assert not result.valid and any(v.code=='no_candidates' for v in result.violations)
    report['golden_case']={'valid':result.valid,'reason':'All imported recipes have unverified allergens; strict peanut profile must not select them.'}
    if args.rebuild:
        with gzip.open(folder/'source-pages.jsonl.gz','rt') as f:pages=[json.loads(line) for line in f if line.strip()]
        with tempfile.TemporaryDirectory() as tmp:
            build_catalog(pages,Path(tmp))
            names=['catalog.jsonl','recipes.jsonl','review_50.jsonl','ingredients.jsonl','rejected.jsonl','quality_report.json']
            for name in names:
                assert (folder/name).read_bytes()==(Path(tmp)/name).read_bytes(),name
        report['offline_rebuild']='identical'
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
