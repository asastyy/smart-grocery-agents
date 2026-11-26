"""Download Cookbook once, then rebuild the extended catalogue offline."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from smart_grocery.catalog.wikibooks import build_catalog, fetch_pages


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=5000)
    parser.add_argument('--cache',type=Path,default=ROOT/'data/catalog/source-pages.jsonl.gz')
    parser.add_argument('--output',type=Path,default=ROOT/'data/catalog')
    parser.add_argument('--refresh',action='store_true',help='Explicitly replace source snapshot from API')
    args=parser.parse_args()
    if not 1<=args.limit<=5000: parser.error('limit must be between 1 and 5000')
    pages=fetch_pages(args.limit,args.cache,args.refresh)
    print(json.dumps(build_catalog(pages,args.output),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
