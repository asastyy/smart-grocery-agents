"""Atomic streaming SQLite index with paged full-text search for large catalogues."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import tempfile
import os
from collections import Counter,defaultdict
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from smart_grocery.catalog.foodcom import file_sha256,iter_rows,parse_foodcom
from smart_grocery.catalog.loader import DEFAULT_CATALOG

ROOT=Path(__file__).resolve().parents[3]
DEFAULT_DB=ROOT/'outputs/catalog.sqlite'
SEED=ROOT/'data/catalog/foodcom/sample-rows.jsonl.gz'
RAW=ROOT/'data/raw/foodcom/recipes.csv'


@contextmanager
def connect_readonly(path: Path):
    connection=sqlite3.connect('file:'+quote(str(path.resolve()),safe='/')+'?mode=ro',uri=True,timeout=20)
    connection.row_factory=sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def build_database(path: Path, *, wiki_path: Path = DEFAULT_CATALOG, foodcom_path: Path | None = None, seed_output: Path | None = None, seed_limit: int = 5000) -> dict:
    """Publish a complete new database only after successful validation/commit."""
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.building.sqlite',dir=path.parent)
    os.close(fd)
    temporary=Path(name)
    connection=sqlite3.connect(temporary)
    source_rows=Counter();accepted=Counter();issues=Counter();rejected=Counter();samples=[]
    stats=defaultdict(Counter);digest=hashlib.sha256();seed_count=0
    seed_raw=seed_zip=None
    if seed_output:
        seed_output.parent.mkdir(parents=True,exist_ok=True)
        seed_raw=seed_output.with_suffix('.part').open('wb')
        seed_zip=gzip.GzipFile(filename='',mode='wb',fileobj=seed_raw,mtime=0)
    try:
        connection.executescript('''
          PRAGMA journal_mode=DELETE;
          PRAGMA synchronous=NORMAL;
          CREATE TABLE recipes(recipe_id TEXT PRIMARY KEY,provider TEXT NOT NULL,title TEXT NOT NULL,
              cook_minutes INTEGER,servings TEXT,fully_quantified INTEGER NOT NULL,
              planning_ready INTEGER NOT NULL,content_sha TEXT NOT NULL UNIQUE,record_json TEXT NOT NULL);
          CREATE VIRTUAL TABLE recipe_search USING fts5(title,ingredient_text,tokenize='unicode61 remove_diacritics 2');
          CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        def ingest(record,provider):
            details=record['ingredient_details']
            complete=bool(details) and all(x.get('normalized') is not None for x in details)
            ready=record['quality']['planning_ready'] is True
            serialized=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            fingerprint=hashlib.sha256(json.dumps([
                [x['text'].casefold() for x in details],record['instructions'],record['servings'],record['cook_minutes']
            ],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            try:
                cursor=connection.execute('INSERT INTO recipes VALUES (?,?,?,?,?,?,?,?,?)',(
                    record['recipe_id'],provider,record['title'],record['cook_minutes'],record['servings'],int(complete),int(ready),fingerprint,serialized))
            except sqlite3.IntegrityError:
                reason='duplicate_id' if connection.execute('SELECT 1 FROM recipes WHERE recipe_id=?',(record['recipe_id'],)).fetchone() else 'duplicate_content'
                rejected[provider+':'+reason]+=1
                if len(samples)<30:samples.append({'recipe_id':record['recipe_id'],'reason':reason})
                return
            connection.execute('INSERT INTO recipe_search(rowid,title,ingredient_text) VALUES (?,?,?)',(
                cursor.lastrowid,record['title'],' '.join(x.get('source_name') or x.get('canonical_name') or x['text'] for x in details)))
            accepted[provider]+=1
            s=stats[provider];s['records']+=1;s['has_instructions']+=bool(record['instructions']);s['fully_quantified']+=complete;s['planning_ready']+=ready
            for field in ['servings','cook_minutes','cuisine','meal_type']:s['has_'+field]+=record.get(field) is not None
            s['has_nutrition_source']+=bool(record.get('nutrition_source'))
            s['allergens_confirmed']+=record['allergens_status']=='confirmed'
            issues.update(record['quality']['issues'])
            digest.update((serialized+'\n').encode())
        with wiki_path.open(encoding='utf-8') as f:
            for line in f:
                if line.strip():source_rows['Wikibooks']+=1;ingest(json.loads(line),'Wikibooks')
        if foodcom_path:
            for row in iter_rows(foodcom_path):
                source_rows['Food.com']+=1
                if seed_zip is not None and seed_count<seed_limit:
                    # Keep original recipe fields needed for replay, omit external image URLs.
                    seed_row={k:v for k,v in row.items() if k!='Images'}
                    seed_zip.write((json.dumps(seed_row,ensure_ascii=False,sort_keys=True)+'\n').encode());seed_count+=1
                try:record=parse_foodcom(row)
                except (ValueError,TypeError,KeyError) as exc:
                    rejected['Food.com:invalid_source_record']+=1
                    if len(samples)<30:samples.append({'recipe_id':row.get('RecipeId'),'reason':'invalid_source_record','error_type':type(exc).__name__})
                    continue
                ingest(record,'Food.com')
                if source_rows['Food.com']%25000==0:print(f"Indexed {source_rows['Food.com']} Food.com source rows",flush=True)
        connection.executescript('''
          CREATE INDEX recipe_filters ON recipes(provider,planning_ready,fully_quantified,cook_minutes,servings);
          CREATE INDEX recipe_title ON recipes(title,recipe_id);
          INSERT INTO recipe_search(recipe_search) VALUES ('optimize');
        ''')
        report={'schema_version':1,'source_rows':dict(source_rows),'accepted_by_source':dict(accepted),'catalog_records':sum(accepted.values()),
                'rejected_or_duplicate':sum(rejected.values()),'rejection_reasons':dict(rejected),'rejection_samples':samples,
                'by_source':{k:dict(v) for k,v in stats.items()},'quality_issues':dict(issues),'logical_sha256':digest.hexdigest(),
                'allergens_confirmed':sum(s['allergens_confirmed'] for s in stats.values()),'human_reviewed':0,'seed_source_rows':seed_count,
                'foodcom_input_sha256':file_sha256(foodcom_path) if foodcom_path else None,
                'wiki_input_sha256':file_sha256(wiki_path),'source_scope':'Food.com v2 full local CSV' if foodcom_path and not foodcom_path.name.endswith('.jsonl.gz') else 'Bundled Food.com sample; full Wikibooks snapshot'}
        connection.execute('INSERT INTO metadata VALUES (?,?)',('report',json.dumps(report,ensure_ascii=False,sort_keys=True)))
        connection.commit()
        assert connection.execute('SELECT count(*) FROM recipes').fetchone()[0]==report['catalog_records']
        assert connection.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        connection.close()
        temporary.replace(path)
        if seed_zip:
            seed_zip.close();seed_zip=None;seed_raw.close();seed_raw=None
            seed_output.with_suffix('.part').replace(seed_output)
        return report
    except BaseException:
        connection.close()
        if seed_zip:seed_zip.close()
        if seed_raw:seed_raw.close()
        if temporary.exists():temporary.unlink()
        raise


def ensure_database(path: Path = DEFAULT_DB) -> Path:
    if not path.exists(): build_database(path,foodcom_path=SEED if SEED.exists() else None)
    return path


def database_report(path: Path = DEFAULT_DB) -> dict:
    with connect_readonly(path) as c:
        return json.loads(c.execute('SELECT value FROM metadata WHERE key=?',('report',)).fetchone()[0])


def search_catalog(query: str = '',provider: str | None = None,quality: str = 'all',*,page: int = 1,page_size: int = 50,path: Path = DEFAULT_DB) -> tuple[int,list[dict]]:
    if page<1 or not 1<=page_size<=100:raise ValueError('invalid_page')
    terms=re.findall(r'[^\W_]+',query[:300],re.UNICODE)[:12]
    conditions=[];params=[];join=''
    if terms:
        join=' JOIN recipe_search ON recipe_search.rowid=r.rowid'
        conditions.append('recipe_search MATCH ?');params.append(' AND '.join('"'+word+'"*' for word in terms))
    if provider:conditions.append('r.provider=?');params.append(provider)
    if quality=='metadata':conditions.append('r.cook_minutes IS NOT NULL AND r.servings IS NOT NULL')
    elif quality=='quantified':conditions.append('r.fully_quantified=1')
    elif quality=='ready':conditions.append('r.planning_ready=1')
    elif quality!='all':raise ValueError('invalid_quality')
    where=' WHERE '+' AND '.join(conditions) if conditions else ''
    with connect_readonly(path) as c:
        if terms and provider is None and quality=='all':
            # Rank/limit row IDs in the compact FTS index BEFORE touching large JSON rows.
            count=c.execute('SELECT count(*) FROM recipe_search WHERE recipe_search MATCH ?',params).fetchone()[0]
            rows=c.execute('''WITH matches AS MATERIALIZED (
                SELECT rowid,rank AS score FROM recipe_search WHERE recipe_search MATCH ?
                ORDER BY rank,rowid LIMIT ? OFFSET ?
            ) SELECT r.recipe_id,r.title,r.provider FROM matches m JOIN recipes r ON r.rowid=m.rowid
              ORDER BY m.score,m.rowid''',params+[page_size,(page-1)*page_size]).fetchall()
        else:
            count=c.execute('SELECT count(*) FROM recipes r'+join+where,params).fetchone()[0]
            rows=c.execute('SELECT r.recipe_id,r.title,r.provider FROM recipes r'+join+where+' ORDER BY r.title,r.recipe_id LIMIT ? OFFSET ?',params+[page_size,(page-1)*page_size]).fetchall()
        return count,[dict(row) for row in rows]


def get_recipe(recipe_id: str,path: Path = DEFAULT_DB) -> dict | None:
    with connect_readonly(path) as c:
        row=c.execute('SELECT record_json FROM recipes WHERE recipe_id=?',(recipe_id,)).fetchone()
        return json.loads(row[0]) if row else None
