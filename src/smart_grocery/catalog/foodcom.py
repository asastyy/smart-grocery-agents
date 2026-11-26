"""Streaming Food.com import: R-vector positions preserved; absent units unknown."""
from __future__ import annotations

import csv
import gzip
import hashlib
import html
import json
import re
import shutil
import zipfile
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path

import httpx

from smart_grocery.catalog.wikibooks import CUISINES, NUMBER, UNITS, parse_ingredient

DATASET = 'https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews/versions/2'
DOWNLOAD = 'https://www.kaggle.com/api/v1/datasets/download/irkaal/foodcom-recipes-and-reviews/recipes.csv?datasetVersionNumber=2'
EXPLICIT_UNIT = re.compile(rf'^{NUMBER}\s*(?:'+ '|'.join(sorted(UNITS,key=len,reverse=True))+r')\b',re.I)
NUTRITION = ['Calories','FatContent','SaturatedFatContent','CholesterolContent','SodiumContent','CarbohydrateContent','FiberContent','SugarContent','ProteinContent']


def parse_r_vector(value: str) -> list[str | None]:
    """Parse flat R c(...) data, including NA slots, without evaluating code."""
    text=(value or '').strip()
    if text in {'', 'character(0)', 'c()'}: return []
    if text.startswith('c('):
        if not text.endswith(')'): raise ValueError('unterminated_vector')
        text=text[2:-1]
    text=text.replace("\\'", "'")
    decoder=json.JSONDecoder(); values=[]; pos=0
    def skip(i):
        while i<len(text):
            if text[i].isspace(): i+=1
            elif text.startswith('\\n',i) or text.startswith('\\r',i): i+=2
            else: break
        return i
    while True:
        pos=skip(pos)
        if pos==len(text):
            if values: raise ValueError('trailing_separator')
            return []
        if text[pos]=='"':
            item,end=decoder.raw_decode(text,pos)
            if not isinstance(item,str): raise ValueError('not_string')
            values.append(item);pos=end
        else:
            match=re.match(r'(?:NA|NULL)(?![A-Za-z_])',text[pos:])
            if not match: raise ValueError('invalid_vector_token')
            values.append(None);pos+=match.end()
        pos=skip(pos)
        if pos==len(text): return values
        if text[pos]!=',': raise ValueError('missing_separator')
        pos+=1


def clean(text: str) -> str:
    return ' '.join(html.unescape(text or '').split())


def iso_minutes(value: str) -> int | None:
    match=re.fullmatch(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?',value or '')
    if not match or not any(match.groups()): return None
    days,hours,minutes,seconds=[Decimal(x or 0) for x in match.groups()]
    total=days*1440+hours*60+minutes+seconds/60
    return int(total.to_integral_value(rounding=ROUND_CEILING)) if total>0 else None


def positive(value: str) -> str | None:
    try:
        result=Decimal(value)
        return str(result.normalize()) if result.is_finite() and result>0 else None
    except (InvalidOperation,ValueError,TypeError): return None


def parse_foodcom(row: dict) -> dict:
    source_id=str(row.get('RecipeId',''))
    if not source_id.isdecimal(): raise ValueError('invalid_recipe_id')
    title=clean(row.get('Name',''))
    parts=parse_r_vector(row.get('RecipeIngredientParts',''))
    amounts=parse_r_vector(row.get('RecipeIngredientQuantities',''))
    steps=parse_r_vector(row.get('RecipeInstructions',''))
    if not title or not any(parts) or not any(steps): raise ValueError('missing_title_ingredients_or_instructions')
    keywords=[clean(x) for x in parse_r_vector(row.get('Keywords','')) if x]
    aligned=len(parts)==len(amounts)
    details=[]
    for i,name in enumerate(parts):
        amount=amounts[i] if aligned else None
        text=clean((amount+' ' if amount else '')+(name or ''))
        # Numeric amounts in this CSV do NOT contain the original recipe's units.
        # Even an egg quantity might refer to a volume; no automatic pcs fallback.
        explicit=bool(amount and EXPLICIT_UNIT.match(amount))
        if explicit and name:
            item=parse_ingredient(text)
        else:
            item={'raw':text,'text':text,'normalized':None,'issues':['unit_not_provided' if amount else 'quantity_not_provided']}
        item.update(source_name=name,source_quantity=amount)
        if not aligned: item['issues'].append('ingredient_quantity_alignment')
        details.append(item)
    servings=positive(row.get('RecipeServings',''))
    minutes=iso_minutes(row.get('TotalTime',''))
    instructions=[clean(x) for x in steps if x and clean(x)]
    if not instructions: raise ValueError('missing_instructions')
    issues=[]
    if not aligned: issues.append('ingredient_quantity_alignment')
    if any(x['normalized'] is None for x in details): issues.append('unresolved_quantities_or_units')
    if not servings: issues.append('unknown_servings')
    if minutes is None: issues.append('unknown_total_time')
    if any(x is None for x in parts): issues.append('unknown_ingredient')
    if any(x is None for x in steps): issues.append('partial_instructions')
    exact={k.casefold() for k in keywords}
    category=clean(row.get('RecipeCategory','')) or None
    cuisines={x.casefold():x for x in CUISINES}
    cuisine=next((cuisines[x.casefold()] for x in [category or '',*keywords] if x.casefold() in cuisines),None)
    meals=sorted(exact.intersection({'breakfast','lunch','dinner'}))
    nutrition={k:row[k] for k in NUTRITION if row.get(k) not in {None,'','NA'}}
    source_hash=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'recipe_id':'fc_'+source_id,'title':title,'description':clean(row.get('Description','')),'language':'en',
            'servings':servings,'cook_minutes':minutes,'tags':sorted(exact.intersection({'vegan','vegetarian'})),
            'ingredients':[x['normalized'] for x in details if x['normalized']], 'ingredient_details':details,
            'instructions':instructions,'cuisine':cuisine,'meal_type':meals[0] if len(meals)==1 else None,
            'source_meal_types':meals,'dish_type':category,'nutrition':None,'nutrition_source':[nutrition] if nutrition else [],
            'allergens_status':'unknown','allergens':None,'source':DATASET,
            'source_fields':{'cook_time':row.get('CookTime'),'prep_time':row.get('PrepTime'),'total_time':row.get('TotalTime'),
                             'yield':row.get('RecipeYield'),'keywords':keywords,'quantities_aligned':aligned},
            'quality':{'issues':sorted(set(issues)),'planning_ready':not issues,'human_review':'pending','allergen_safety':'not_verified'},
            'provenance':{'provider':'Food.com','dataset':DATASET,'dataset_version':2,'original_recipe_id':source_id,
                          'author':row.get('AuthorName'),'date_published':row.get('DatePublished'),
                          'license':'CC0-1.0 (Kaggle uploader declaration)','license_url':'https://creativecommons.org/publicdomain/zero/1.0/',
                          'source_sha256':source_hash,'changes':'Parsed flat R vectors preserving NA slots; extracted source instructions; absent units and allergen data remain unknown. Images omitted.'}}


def iter_rows(path: Path):
    if path.name.endswith('.jsonl.gz'):
        with gzip.open(path,'rt',encoding='utf-8') as f:
            for line in f:
                if line.strip(): yield json.loads(line)
    else:
        csv.field_size_limit(10_000_000)
        with path.open(newline='',encoding='utf-8-sig') as f:
            yield from csv.DictReader(f)


def file_sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def download_csv(folder: Path) -> Path:
    """Public pinned-version download, no Kaggle account files or tokens read."""
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'recipes.csv'
    if target.exists(): return target
    archive=folder/'recipes-download.bin'
    if not archive.exists():
        temporary=archive.with_suffix('.part')
        with httpx.Client(timeout=60,follow_redirects=True) as client:
            with client.stream('GET',DOWNLOAD) as response:
                response.raise_for_status();size=0
                with temporary.open('wb') as output:
                    for block in response.iter_bytes(1024*1024):
                        size+=len(block)
                        if size>512*1024*1024: raise ValueError('download_size_limit')
                        output.write(block)
        temporary.replace(archive)
    with zipfile.ZipFile(archive) as z:
        names=[n for n in z.namelist() if Path(n).name=='recipes.csv']
        if len(names)!=1 or z.getinfo(names[0]).file_size>2*1024*1024*1024:raise ValueError('unexpected_archive')
        temporary=target.with_suffix('.part')
        with z.open(names[0]) as source,temporary.open('wb') as output:shutil.copyfileobj(source,output)
        temporary.replace(target)
    return target
