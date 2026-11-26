import gzip
import json
from pathlib import Path

import pytest

from smart_grocery.catalog.foodcom import parse_r_vector,parse_foodcom,iso_minutes
from smart_grocery.catalog.database import build_database,search_catalog,get_recipe,database_report


def row(recipe_id='1',title='Chicken rice'):
    return {'RecipeId':recipe_id,'Name':title,'RecipeIngredientParts':'c("milk", "eggs")',
            'RecipeIngredientQuantities':'c("1", "2")','RecipeInstructions':'c("Mix.", "Cook.")',
            'RecipeServings':'2','TotalTime':'PT1H20M','Keywords':'c("Italian", "Dinner")','RecipeCategory':'Chicken'}


@pytest.mark.parametrize('value,expected',[
 ('c("a", NA, "b")',['a',None,'b']),('c("a", NULL, "b")',['a',None,'b']),
 ('"milk"',['milk']),('NA',[None]),('character(0)',[]),('c()',[]),
 ('c("one", \\n"two")',['one','two']),('c("it\\\'s good")',["it's good"]),
 ('c("one, two", "three")',['one, two','three']),
])
def test_r_vectors_preserve_positions(value,expected):
    assert parse_r_vector(value)==expected


@pytest.mark.parametrize('value',['c("a",)','c("a" "b")','c(system("x"))','c("a") trailing','c("a", MISSING)'])
def test_invalid_r_vectors_are_never_executed_or_silently_shifted(value):
    with pytest.raises(ValueError):parse_r_vector(value)


@pytest.mark.parametrize('value,expected', [('PT25M',25),('PT4H25M',265),('P1DT2H',1560),('PT1S',1),('PT0M',None),('NA',None),('PT',None)])
def test_iso_total_time(value,expected):assert iso_minutes(value)==expected


def test_foodcom_does_not_invent_units_even_for_eggs():
    r=parse_foodcom(row())
    assert r['ingredients']==[]
    assert all(x['normalized'] is None for x in r['ingredient_details'])
    assert r['allergens'] is None and r['allergens_status']=='unknown'
    assert r['cook_minutes']==80 and r['cuisine']=='Italian'
    assert not r['quality']['planning_ready']


def test_missing_quantity_slot_keeps_alignment():
    raw=row();raw['RecipeIngredientQuantities']='c(NA, "2")'
    r=parse_foodcom(raw)
    assert r['ingredient_details'][0]['source_quantity'] is None
    assert r['ingredient_details'][1]['source_quantity']=='2'


def test_mismatched_arrays_are_flagged_without_zip_truncation():
    raw=row();raw['RecipeIngredientQuantities']='c("1", NA, "2")'
    r=parse_foodcom(raw)
    assert len(r['ingredient_details'])==2
    assert 'ingredient_quantity_alignment' in r['quality']['issues']
    assert all(x['source_quantity'] is None for x in r['ingredient_details'])


def test_empty_ingredient_list_rejected():
    raw=row();raw['RecipeIngredientParts']='c(NA)'
    with pytest.raises(ValueError):parse_foodcom(raw)


def write_rows(path,rows):
    with gzip.open(path,'wt') as f:
        for r in rows:f.write(json.dumps(r)+'\n')


def test_database_pagination_filters_and_safe_search(tmp_path):
    wiki=tmp_path/'wiki.jsonl';wiki.write_text('')
    source=tmp_path/'rows.jsonl.gz'
    write_rows(source,[row(str(i),f'Chicken rice {i:03d}') for i in range(125)])
    db=tmp_path/'catalog.sqlite'
    # Same contents, portions and steps deduplicate despite different names/IDs.
    report=build_database(db,wiki_path=wiki,foodcom_path=source)
    assert report['catalog_records']==1 and report['rejection_reasons']['Food.com:duplicate_content']==124
    total,rows=search_catalog('chicken',path=db)
    assert total==1 and rows[0]['provider']=='Food.com'
    assert search_catalog('chicken',quality='ready',path=db)[0]==0
    assert search_catalog('" OR 1=1 --',path=db)[0]==0
    assert get_recipe(rows[0]['recipe_id'],db)['instructions']==['Mix.','Cook.']
    assert get_recipe("'; DROP TABLE recipes; --",db) is None
    assert database_report(db)['catalog_records']==1


def test_multiple_pages_do_not_load_full_records(tmp_path):
    wiki=tmp_path/'wiki.jsonl';wiki.write_text('');source=tmp_path/'rows.jsonl.gz'
    data=[]
    for i in range(125):
        r=row(str(i),f'Chicken rice {i:03d}');r['RecipeInstructions']=json.dumps(f'Cook batch {i}.');data.append(r)
    write_rows(source,data);db=tmp_path/'catalog.sqlite';build_database(db,wiki_path=wiki,foodcom_path=source)
    total,a=search_catalog('rice',page=1,path=db);_,b=search_catalog('rice',page=2,path=db)
    assert total==125 and len(a)==len(b)==50
    assert not {x['recipe_id'] for x in a}&{x['recipe_id'] for x in b}
    assert 'record_json' not in a[0]


def test_failed_build_preserves_previous_database(tmp_path):
    wiki=tmp_path/'wiki.jsonl';wiki.write_text('');source=tmp_path/'rows.jsonl.gz';write_rows(source,[row()])
    db=tmp_path/'catalog.sqlite';build_database(db,wiki_path=wiki,foodcom_path=source)
    before=db.read_bytes();wiki.write_text('{broken')
    with pytest.raises(ValueError):build_database(db,wiki_path=wiki,foodcom_path=source)
    assert db.read_bytes()==before


def test_seed_is_deterministic_and_does_not_copy_images(tmp_path):
    wiki=tmp_path/'wiki.jsonl';wiki.write_text('');source=tmp_path/'rows.jsonl.gz';r=row();r['Images']='private-image-not-copied';write_rows(source,[r])
    seed=tmp_path/'seed.jsonl.gz';build_database(tmp_path/'db.sqlite',wiki_path=wiki,foodcom_path=source,seed_output=seed)
    with gzip.open(seed,'rt') as f:assert 'Images' not in json.loads(next(f))


def test_full_namespace_fetch_preserves_cached_revisions_and_fetches_only_missing(tmp_path,monkeypatch):
    import httpx
    from smart_grocery.catalog.wikibooks import fetch_pages
    cache=tmp_path/'pages.gz'
    original={'pageid':42,'title':'Cookbook:Existing','revisions':[{'revid':9}]}
    with gzip.open(cache,'wt') as f:f.write(json.dumps(original)+'\n')
    requests=[]
    def handler(request):
        params=dict(request.url.params);requests.append(params)
        if params.get('list')=='allpages':
            return httpx.Response(200,json={'query':{'allpages':[{'pageid':42},{'pageid':43}]}})
        assert params['pageids']=='43'
        return httpx.Response(200,json={'query':{'pages':[{'pageid':43,'title':'Cookbook:New','revisions':[{'revid':10}]}]}})
    real_client=httpx.Client
    monkeypatch.setattr('smart_grocery.catalog.wikibooks.httpx.Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    pages=fetch_pages(100,cache,all_pages=True)
    assert [p['pageid'] for p in pages]==[42,43]
    assert pages[0]['revisions'][0]['revid']==9
    assert len(requests)==2


def test_database_reader_is_readonly_and_closes_connection(tmp_path):
    import sqlite3
    from smart_grocery.catalog.database import connect_readonly
    db=tmp_path/'small.sqlite'
    with sqlite3.connect(db) as c:c.execute('CREATE TABLE t(x)')
    with connect_readonly(db) as c:
        with pytest.raises(sqlite3.OperationalError):c.execute('INSERT INTO t VALUES (1)')
    with pytest.raises(sqlite3.ProgrammingError):c.execute('SELECT 1')
