import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from smart_grocery.catalog.wikibooks import (
    build_catalog, canonical_id, decimal_number, fetch_pages, parse_ingredient,
    parse_page, time_minutes,
)
from smart_grocery.catalog.loader import planning_recipes
from smart_grocery.schemas.foodcom import Recipe
from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow

ROOT=Path(__file__).resolve().parents[1]


def page(body=None):
    body=body or '''{{Recipe summary|servings=2|time=20 minutes|category=Main dishes}}
==Ingredients==
* 200 g [[Cookbook:Rice|rice]]
* 500 ml [[Cookbook:Water|water]]
* 2 [[Cookbook:Egg|eggs]]
==Procedure==
# Cook rice in water.
# Add eggs and cook through.
[[Category:Japanese recipes]]
'''
    return {'pageid':42,'title':'Cookbook:Test rice','revisions':[{'revid':9,'timestamp':'2026-11-01T00:00:00Z','slots':{'main':{'content':body}}}]}


@pytest.mark.parametrize('raw,qty,unit',[
 ('200 g rice','200','g'),('0.5 kg rice','500','g'),('100g rice','100','g'),
 ('1 l milk','1000','ml'),('250 mL milk','250','ml'),('2 eggs','2','pcs'),
 ('½ kg rice','500','g'),('1 1/2 kg rice','1500','g'),
 ('1 cup (240 ml) milk','240','ml'),
 ('1 cup (200 g) rice','200','g'),('1 can (400 g) tomato','400','g'),
 ('{{convert|8|oz|g}} flour','226.796185','g'),
])
def test_explicit_source_quantities(raw,qty,unit):
    result=parse_ingredient(raw)
    assert result['normalized'] is not None,result
    assert decimal_number(result['normalized']['quantity'])==decimal_number(qty)
    assert result['normalized']['unit']==unit


@pytest.mark.parametrize('raw',[
 'rice','1 rice','1 cup rice','salt to taste','2–3 eggs','2 or 3 eggs',
 '1 can tomato','1 teaspoon salt','1 optional egg','2 cans (400 g) tomato',
 '200 g milk','0 g rice','1/0 kg rice','2 tbsp olive oil',
])
def test_unknown_or_ambiguous_is_never_fake_pieces(raw):
    assert parse_ingredient(raw)['normalized'] is None


@pytest.mark.parametrize('value,expected',[
 ('20 minutes',20),('1 hour 30 minutes',90),('1.5 hours',90),
 ('20–30 minutes',None),('',None),('Prep: 10 minutes; cook: 20 minutes',None),
])
def test_time_does_not_choose_range_or_invent_total(value,expected):
    assert time_minutes(value)==expected


def test_aliases_do_not_mix_product_forms():
    assert canonical_id('Куриная грудка')[0]=='chicken_breast'
    assert canonical_id('рис')[0]=='rice'
    assert canonical_id('rice flour')[0]!='rice'
    assert canonical_id('chicken')[0]!='chicken_breast'


def test_shared_recipe_provenance_and_unknown_allergens():
    record=parse_page(page())
    assert record['quality']['planning_ready']
    shared=Recipe.model_validate(record)
    assert shared.instructions and shared.cuisine=='Japanese'
    assert shared.allergens is None and shared.allergens_status=='unknown'
    assert record['provenance']['revision_id']==9
    assert record['provenance']['source_sha256']
    assert record['quality']['human_review']=='pending'


def test_missing_metadata_is_not_defaulted():
    record=parse_page(page('==Ingredients==\n* 100 g rice\n==Procedure==\n# Cook.'))
    assert record['servings'] is None and record['cook_minutes'] is None
    assert not record['quality']['planning_ready']


def test_chilling_is_not_hidden_by_short_summary_time():
    source=page()['revisions'][0]['slots']['main']['content']
    record=parse_page(page(source.replace('Cook rice in water.','Refrigerate for 4 hours.')))
    assert 'additional_wait_time_requires_review' in record['quality']['issues']
    assert not record['quality']['planning_ready']


def test_tables_are_not_silently_dropped():
    source=page()['revisions'][0]['slots']['main']['content'].replace('* 200 g', '{|\n| rice\n|}\n* 200 g')
    assert 'unsupported_ingredient_structure' in parse_page(page(source))['quality']['issues']


def test_missing_steps_rejected_and_duplicate_content_audited(tmp_path):
    a=page();b=deepcopy(a);b['pageid']=43;b['title']='Cookbook:Copy'
    bad=page('==Ingredients==\n* 100 g rice');bad['pageid']=44
    report=build_catalog([a,a,b,bad],tmp_path)
    assert report['catalog_records']==1
    assert report['rejection_reasons']=={'duplicate_source_id':1,'duplicate_content':1,'missing_ingredients_or_instructions':1}


def test_offline_snapshot_requires_no_network(tmp_path,monkeypatch):
    cache=tmp_path/'pages.gz'
    with gzip.open(cache,'wt') as f:f.write(json.dumps(page())+'\n')
    monkeypatch.setattr('smart_grocery.catalog.wikibooks.httpx.Client',lambda **kw:pytest.fail('network attempted'))
    assert fetch_pages(100,cache)[0]['pageid']==42


def test_rebuild_is_deterministic(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b'
    assert build_catalog([page()],a)==build_catalog([page()],b)
    assert {p.name:p.read_bytes() for p in a.iterdir()}=={p.name:p.read_bytes() for p in b.iterdir()}


def test_real_exports_match_shared_contract_and_strict_allergy(tmp_path):
    records=[json.loads(line) for line in (ROOT/'data/catalog/catalog.jsonl').read_text().splitlines()]
    assert len(records)>=500
    assert len({r['recipe_id'] for r in records})==len(records)
    assert all(r['allergens'] is None and r['allergens_status']=='unknown' for r in records)
    assert all(r['instructions'] and r['source'] and r['provenance']['license']=='CC-BY-SA-4.0' for r in records)
    ready=planning_recipes()
    case,provider=load_golden_case()
    result=run_integration_workflow(case.profile,case.inventory,ready,provider,days=case.days,mock_planner=True)
    assert not result.valid and result.violations[0].code=='no_candidates'


def test_catalog_ui_exposes_instructions_without_llm():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    app.toggle(key='recipe_catalog').set_value(True).run()
    assert not app.exception
    assert app.metric[0].value
    assert any('Приготовление' in x.value for x in app.markdown)


def test_volume_glossary_is_used_only_when_linked_by_source():
    body=page()['revisions'][0]['slots']['main']['content'].replace('* 200 g [[Cookbook:Rice|rice]]','* 1 [[Cookbook:Cup|cup]] [[Cookbook:Flour|flour]]')
    result=parse_page(page(body))
    amount=result['ingredient_details'][0]
    assert amount['normalized']['unit']=='ml'
    assert amount['normalized']['quantity']=='236.5882365'
    assert 'measurement_basis' in amount
    assert parse_ingredient('1 cup flour')['normalized'] is None


def test_missing_ingredient_name_is_not_generated_hash():
    assert parse_ingredient('100 g (unknown)')['normalized'] is None
