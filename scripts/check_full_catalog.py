"""Validate the searchable index and report measured search time, without LLM."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from smart_grocery.catalog.database import DEFAULT_DB,connect_readonly,database_report,get_recipe,search_catalog
from smart_grocery.catalog.foodcom import iter_rows,parse_foodcom


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,default=DEFAULT_DB)
    p.add_argument('--raw',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'outputs/full_catalog_validation.json')
    args=p.parse_args()
    report=database_report(args.database)
    with connect_readonly(args.database) as c:
        assert c.execute('SELECT count(*) FROM recipes').fetchone()[0]==report['catalog_records']
        assert c.execute('SELECT count(*) FROM recipe_search').fetchone()[0]==report['catalog_records']
        ready=c.execute('SELECT recipe_id FROM recipes WHERE planning_ready=1').fetchall()
    assert report['allergens_confirmed']==0
    for row in ready:
        r=get_recipe(row['recipe_id'],args.database)
        assert r['allergens'] is None and r['allergens_status']=='unknown'
    results={'records':report['catalog_records'],'planning_ready':len(ready),'allergens_confirmed':0,'searches':[]}
    for query in ['chicken rice','pasta tomato','vegan']:
        start=time.perf_counter();count,rows=search_catalog(query,path=args.database)
        results['searches'].append({'query':query,'matches':count,'seconds':round(time.perf_counter()-start,4),'page_size':len(rows)})
        assert len(rows)<=50
        if rows:
            record=get_recipe(rows[0]['recipe_id'],args.database)
            assert record['instructions'] and record['ingredient_details']
    if args.raw:
        checked=0
        for row in iter_rows(args.raw):
            try:expected=parse_foodcom(row)
            except ValueError:continue
            actual=get_recipe(expected['recipe_id'],args.database)
            if actual:
                assert expected==actual,expected['recipe_id'];checked+=1
            if checked==100:break
        results['source_rows_reparsed']=checked
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
