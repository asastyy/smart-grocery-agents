"""Build the paged catalogue index from local inputs; full download is opt-in."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from smart_grocery.catalog.database import DEFAULT_DB, RAW, SEED, build_database
from smart_grocery.catalog.foodcom import download_csv


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--download',action='store_true',help='Fetch full public Food.com v2 CSV without credentials')
    p.add_argument('--raw',type=Path)
    p.add_argument('--database',type=Path,default=DEFAULT_DB)
    p.add_argument('--write-seed',action='store_true',help='Save 5000 original rows for offline bundled demo')
    p.add_argument('--report',type=Path,default=ROOT/'outputs/full_catalog_report.json')
    args=p.parse_args()
    if args.download:download_csv(RAW.parent)
    source=args.raw or (RAW if RAW.exists() else SEED)
    if not source.exists():p.error('No Food.com input found; use --download or provide --raw')
    report=build_database(args.database,foodcom_path=source,seed_output=SEED if args.write_seed else None)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
