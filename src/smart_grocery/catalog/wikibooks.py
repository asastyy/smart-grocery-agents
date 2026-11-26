"""Conservative Cookbook import. Unknowns stay nullable; no density guesses."""
from __future__ import annotations

import gzip
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

import httpx
import mwparserfromhell as mw

from smart_grocery.schemas.foodcom import Recipe

API = "https://en.wikibooks.org/w/api.php"
LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"
FRACTIONS = {"½":"1/2", "¼":"1/4", "¾":"3/4", "⅓":"1/3", "⅔":"2/3", "⅛":"1/8", "⅜":"3/8", "⅝":"5/8", "⅞":"7/8"}
UNITS = {"g":("g","1"), "gram":("g","1"), "grams":("g","1"), "kg":("g","1000"), "kilograms":("g","1000"), "mg":("g","0.001"), "oz":("g","28.349523125"), "ounce":("g","28.349523125"), "ounces":("g","28.349523125"), "lb":("g","453.59237"), "lbs":("g","453.59237"), "pound":("g","453.59237"), "pounds":("g","453.59237"), "ml":("ml","1"), "milliliter":("ml","1"), "millilitres":("ml","1"), "l":("ml","1000"), "liter":("ml","1000"), "litre":("ml","1000"), "liters":("ml","1000"), "litres":("ml","1000"), "dl":("ml","100")}
ALIASES = {
 "rice":"rice", "white rice":"rice", "рис":"rice",
 "egg":"egg", "eggs":"egg", "яйцо":"egg", "яйца":"egg",
 "chicken breast":"chicken_breast", "chicken breasts":"chicken_breast", "куриная грудка":"chicken_breast",
 "milk":"milk", "cow milk":"milk", "молоко":"milk",
 "tomato":"tomato", "tomatoes":"tomato", "помидоры":"tomato", "помидор":"tomato",
 "olive oil":"olive_oil", "оливковое масло":"olive_oil",
 "salt":"salt", "table salt":"salt", "соль":"salt",
 "water":"water", "вода":"water", "butter":"butter", "unsalted butter":"unsalted_butter",
 "all-purpose flour":"all_purpose_flour", "all purpose flour":"all_purpose_flour",
 "garlic":"garlic", "onion":"onion", "onions":"onion", "лук":"onion",
 "lemon":"lemon", "lemons":"lemon", "potato":"potato", "potatoes":"potato",
}
# These IDs have a reviewed unit at the retail/inventory boundary.
EXPECTED_UNITS = {"rice":"g", "egg":"pcs", "chicken_breast":"g", "milk":"ml", "tomato":"g", "olive_oil":"ml"}
COUNTABLE = {"egg", "egg_white", "egg_whites", "egg_yolk", "egg_yolks", "lemon", "onion", "potato", "tomato"}
CUISINES = {"Italian", "French", "Greek", "Spanish", "Chinese", "Japanese", "Korean", "Thai", "Indian", "Nigerian", "American", "British", "Mexican", "Turkish", "Lebanese", "Vietnamese", "Russian", "Malaysian"}
NUMBER = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"


def canonical_id(name: str) -> tuple[str, str]:
    key = " ".join(unicodedata.normalize("NFKC", name).casefold().replace("ё", "е").split())
    if key in ALIASES:
        return ALIASES[key], "reviewed_alias"
    value = re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()).strip("_")
    return (value or "ingredient_" + hashlib.sha256(key.encode()).hexdigest()[:12]), "source_name"


def plain(value: str) -> str:
    code = mw.parse(value)
    for tag in list(code.filter_tags()):
        if str(tag.tag).lower() in {"ref", "gallery", "math"}:
            code.replace(tag, "")
    for template in list(code.filter_templates(recursive=False)):
        name = re.sub(r"[ _]", "", str(template.name)).lower()
        args = [str(p.value) for p in template.params if not p.showkey]
        if name in {"convert", "cvt"} and len(args) >= 2:
            replacement = f"{args[0]} {args[1]}"
        elif name in {"frac", "fraction"} and len(args) in {2, 3}:
            replacement = (args[0] + " " if len(args) == 3 else "") + "/".join(args[-2:])
        else:
            replacement = " [unresolved template] "
        code.replace(template, replacement)
    return " ".join(html.unescape(code.strip_code(normalize=True, collapse=True)).replace("\xa0", " ").split())


def decimal_number(value: str) -> Decimal | None:
    try:
        parts = value.strip().replace(",", ".").split()
        total = Decimal(0)
        for p in parts:
            if "/" in p:
                a, b = p.split("/")
                total += Decimal(a) / Decimal(b)
            else:
                total += Decimal(p)
        return total if total.is_finite() and total > 0 else None
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def parse_ingredient(raw: str, volume_units: dict | None = None) -> dict:
    text = plain(raw).strip("*# ")
    for symbol, replacement in FRACTIONS.items():
        text = text.replace(symbol, " " + replacement + " ")
    text = " ".join(text.split())
    result = {"raw":raw, "text":text, "normalized":None, "issues":[]}
    # Never silently select one alternative, optional ingredient, range or unit.
    if re.search(r"\b(or|optional|approximately|about|to taste|as needed|heaped|heaping)\b|\[unresolved template\]", text, re.I):
        result["issues"].append("ambiguous_or_unquantified"); return result
    if re.match(rf"^{NUMBER}\s*[–—-]\s*\d", text):
        result["issues"].append("quantity_range"); return result
    # A metric equivalent explicitly provided by the source takes precedence.
    metric = re.search(rf"\(\s*({NUMBER})\s*(kg|mg|g|ml|dl|l)\b[^)]*\)", text, re.I)
    m = re.match(rf"^({NUMBER})\s*(?P<rest>[A-Za-z].*)$", text)
    if not m:
        result["issues"].append("missing_quantity"); return result
    qty = decimal_number(metric.group(1) if metric else m.group(1))
    rest = m.group("rest")
    unit_match = re.match(r"([A-Za-z]+)\.?\s+(.+)$", rest)
    if metric:
        if re.match(r"^(?:cans?|packages?|packs?|pieces?|bottles?|jars?)\b", rest, re.I) and decimal_number(m.group(1)) != 1:
            result["issues"].append("ambiguous_multipack_quantity"); return result
        unit, factor = UNITS[metric.group(2).lower()]
        rest = re.sub(r"^.*?\([^)]*\)\s*", "", rest)
        result["quantity_source"] = "explicit_metric_equivalent"
    elif unit_match and unit_match.group(1).lower() in {**UNITS, **(volume_units or {})}:
        unit, factor = {**UNITS, **(volume_units or {})}[unit_match.group(1).lower()]
        rest = unit_match.group(2)
        result["quantity_source"] = "explicit_source_unit"
        if unit_match.group(1).lower() in (volume_units or {}):
            result["measurement_basis"] = "Wikibooks unit glossary linked by this recipe; volume only, never density conversion"
    else:
        unit, factor = "pcs", "1"
        result["quantity_source"] = "explicit_count"
    # Remove preparation after commas, but never discard unknown quantity words.
    name = re.sub(r"\([^)]*\)", "", rest.split(",", 1)[0]).strip()
    name = re.sub(r"^(?:of\s+)", "", name, flags=re.I)
    if not name:
        result["issues"].append("missing_ingredient_name"); return result
    iid, status = canonical_id(name)
    result.update(ingredient_id=iid, canonical_name=name, canonical_status=status)
    if not qty:
        result["issues"].append("invalid_quantity"); return result
    if unit == "pcs" and iid not in COUNTABLE:
        result["issues"].append("unknown_unit_or_count_basis"); return result
    if iid in EXPECTED_UNITS and unit != EXPECTED_UNITS[iid]:
        result["issues"].append("incompatible_canonical_unit"); return result
    result["normalized"] = {"ingredient_id":iid, "quantity":str((qty * Decimal(factor)).normalize()), "unit":unit}
    return result


def scalar(value: str) -> str:
    return re.sub(r"[ _]", "", value).casefold()


def time_minutes(value: str) -> int | None:
    text = plain(value).casefold()
    if not re.fullmatch(r"\s*\d+(?:\.\d+)?\s*(?:hours?|hrs?|h|minutes?|mins?|m)(?:\s*(?:and\s*)?\d+\s*(?:minutes?|mins?|m))?\s*", text):
        return None
    total = sum(float(n) * (60 if u.startswith("h") else 1) for n,u in re.findall(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)", text))
    return int(total) if total > 0 and total.is_integer() else None


def parse_page(page: dict) -> dict:
    revision = page["revisions"][0]
    raw = revision["slots"]["main"]["content"]
    code = mw.parse(raw)
    categories = [str(x.title).split(":",1)[1].strip() for x in code.filter_wikilinks() if str(x.title).lower().startswith("category:")]
    fields = {}
    nutrition_source = []
    for template in code.filter_templates():
        if scalar(str(template.name)) in {"nutritionsummary", "nutrition"}:
            nutrition_source.append({str(p.name).strip(): plain(str(p.value)) for p in template.params})
        if scalar(str(template.name)) in {"recipesummary", "recipe"}:
            for param in template.params:
                if param.showkey:
                    key=scalar(str(param.name)); value=plain(str(param.value))
                    if value:
                        if key in fields and fields[key] != value: fields[key] = "[conflicting source values]"
                        else: fields[key] = value
    servings_text = fields.get("servings", "")
    serving_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:people|servings?|persons?)?", servings_text, re.I)
    servings = decimal_number(serving_match.group(1)) if serving_match else None
    minutes = time_minutes(fields.get("time", ""))
    volume_units = {}
    linked_units = {str(link.title).strip().casefold() for link in code.filter_wikilinks()}
    # Interpret kitchen measures only when this page explicitly links their definition.
    if "cookbook:cup" in linked_units:
        volume_units.update({key:("ml", "236.5882365") for key in ["cup", "cups"]})
    if "cookbook:teaspoon" in linked_units:
        volume_units.update({key:("ml", "5") for key in ["tsp", "teaspoon", "teaspoons"]})
    # The source describes tablespoon volumes as approximate and region dependent.
    # Leave tablespoons unresolved rather than pick a default.
    ingredients, instructions = [], []
    ingredient_structure_issue = False
    for section in code.get_sections(levels=[2], include_lead=False, include_headings=True):
        headings=section.filter_headings()
        if not headings: continue
        heading=plain(str(headings[0].title)).casefold()
        body=str(section).split("\n",1)[-1]
        if heading in {"ingredients", "ingredient"}:
            ingredient_structure_issue = "{|" in body or "<onlyinclude" in body
            ingredients.extend(parse_ingredient(line,volume_units) for line in body.splitlines() if re.match(r"^\s*\*", line))
        if re.match(r"^(procedure|preparation|directions|method|instructions)(\b|s\b)", heading) and not instructions:
            instructions=[plain(re.sub(r"^\s*(?:#+|\d+[.)])\s*", "", line)) for line in body.splitlines() if re.match(r"^\s*(?:#+|\d+[.)])", line)]
            instructions=[x for x in instructions if x]
    issues=[]
    if not ingredients: issues.append("missing_ingredients")
    if ingredient_structure_issue: issues.append("unsupported_ingredient_structure")
    if any(x["normalized"] is None for x in ingredients): issues.append("unresolved_quantities_or_units")
    if not instructions: issues.append("missing_instructions")
    if any("[unresolved template]" in step for step in instructions): issues.append("unresolved_instruction_template")
    if minutes is not None and re.search(r"\b(?:overnight|(?:chill|rest|refrigerat|marinat|soak)[^.!?]{0,100}\d+[^.!?]{0,20}hours?)", " ".join(instructions), re.I): issues.append("additional_wait_time_requires_review")
    if servings is None: issues.append("unknown_servings")
    if minutes is None: issues.append("unknown_total_time")
    if any(scalar(str(t.name)) in {"incompleterecipe", "copyvio", "delete", "speedydelete"} for t in code.filter_templates()): issues.append("source_quality_warning")
    tags=[]
    if "Vegetarian recipes" in categories: tags.append("vegetarian")
    if "Vegan recipes" in categories: tags.extend(["vegan", "vegetarian"])
    meal_type=next((meal for meal in ("breakfast", "lunch", "dinner") if any(meal in c.casefold().split() for c in categories)), None)
    cuisine=fields.get("cuisine") or next((c.split()[0] for c in categories if c.endswith(" recipes") and c.split()[0] in CUISINES), None)
    url="https://en.wikibooks.org/wiki/"+quote(page["title"].replace(" ","_"),safe=":/")
    record={"recipe_id":f"wb_{page['pageid']}","title":page["title"].removeprefix("Cookbook:"),"servings":str(servings) if servings else None,"cook_minutes":minutes,"tags":sorted(set(tags)),"ingredients":[x["normalized"] for x in ingredients if x["normalized"]],"instructions":instructions or None,"cuisine":cuisine,"meal_type":meal_type,"dish_type":fields.get("category"),"nutrition":None,"allergens_status":"unknown","allergens":None,"source":url,"provenance":{"provider":"Wikibooks Cookbook","page_id":page["pageid"],"revision_id":revision["revid"],"revision_timestamp":revision["timestamp"],"revision_url":f"https://en.wikibooks.org/w/index.php?oldid={revision['revid']}","authors_url":url+"?action=history","license":"CC-BY-SA-4.0","license_url":LICENSE,"source_sha256":hashlib.sha256(raw.encode()).hexdigest(),"changes":"Wiki markup cleaned; structured fields extracted; units normalized conservatively; no images copied."},"source_fields":fields,"nutrition_source":nutrition_source,"ingredient_details":ingredients,"quality":{"issues":sorted(set(issues)),"planning_ready":not issues,"human_review":"pending","allergen_safety":"not_verified"},"categories":categories}
    if not issues:
        Recipe.model_validate(record)
    return record


def fetch_pages(limit: int, cache: Path, refresh: bool = False, all_pages: bool = False) -> list[dict]:
    known = {}
    if cache.exists() and not refresh:
        with gzip.open(cache,"rt",encoding="utf-8") as f: cached = [json.loads(line) for line in f if line.strip()]
        if not all_pages: return cached[:limit]
        known = {p["pageid"]:p for p in cached}
    pages=[]; members=[]; continuation={}
    with httpx.Client(timeout=30, headers={"User-Agent":"SmartGroceryAgents/0.1 (academic Cookbook catalog; https://github.com/asastyy/smart-grocery-agents)"}, follow_redirects=False) as client:
        def request(params):
            r=client.get(API,params={"format":"json","formatversion":2,"maxlag":5,**params});r.raise_for_status();d=r.json()
            if "error" in d: raise RuntimeError("MediaWiki error: "+str(d["error"].get("code")))
            return d
        while len(members)<limit:
            params = ({"action":"query","list":"allpages","apnamespace":102,"apfilterredir":"nonredirects","aplimit":min(500,limit-len(members))} if all_pages else {"action":"query","list":"categorymembers","cmtitle":"Category:Recipes","cmnamespace":102,"cmlimit":min(500,limit-len(members))})
            data=request({**params,**continuation})
            members.extend(data["query"]["allpages" if all_pages else "categorymembers"])
            continuation=data.get("continue",{})
            if not continuation: break
        pages = [known[p["pageid"]] for p in members if p["pageid"] in known]
        missing = [p for p in members if p["pageid"] not in known]
        for start in range(0,len(missing),50):
            ids="|".join(str(p["pageid"]) for p in missing[start:start+50])
            data=request({"action":"query","pageids":ids,"prop":"revisions","rvprop":"ids|timestamp|content","rvslots":"main"})
            pages.extend(p for p in data["query"]["pages"] if p.get("revisions"))
            print(f"Fetched {len(pages)}/{len(members)} Cookbook pages",flush=True)
    cache.parent.mkdir(parents=True,exist_ok=True)
    # Deterministic gzip header permits exact offline reproduction.
    with cache.open("wb") as raw_file:
        with gzip.GzipFile(filename="",mode="wb",fileobj=raw_file,mtime=0) as f:
            for page in sorted(pages,key=lambda x:x["pageid"]): f.write((json.dumps(page,ensure_ascii=False,sort_keys=True)+"\n").encode())
    return sorted(pages,key=lambda x:x["pageid"])


def build_catalog(pages: list[dict], output: Path) -> dict:
    output.mkdir(parents=True,exist_ok=True)
    records=[]; rejected=[]; seen_ids=set();seen_content={}
    for page in pages:
        try: record=parse_page(page)
        except (ValueError,KeyError,TypeError) as exc:
            rejected.append({"page_id":page.get("pageid"),"reason":"invalid_source_record","error_type":type(exc).__name__});continue
        rid=record["recipe_id"]
        if rid in seen_ids:
            rejected.append({"page_id":page["pageid"],"reason":"duplicate_source_id"});continue
        seen_ids.add(rid)
        if not record["ingredient_details"] or not record["instructions"]:
            rejected.append({"page_id":page["pageid"],"reason":"missing_ingredients_or_instructions"});continue
        fingerprint=hashlib.sha256(json.dumps([[(x['text'].casefold()) for x in record['ingredient_details']],record['instructions']],sort_keys=True).encode()).hexdigest()
        if fingerprint in seen_content:
            rejected.append({"page_id":page["pageid"],"reason":"duplicate_content","duplicate_of":seen_content[fingerprint]});continue
        seen_content[fingerprint]=rid; records.append(record)
    records.sort(key=lambda r:r["recipe_id"])
    ready=[Recipe.model_validate(r).model_dump(mode="json") for r in records if r["quality"]["planning_ready"]]
    review=sorted(records,key=lambda r:(len(r["quality"]["issues"]),-len(r["ingredients"]),r["recipe_id"]))[:50]
    issues=Counter(issue for r in records for issue in r["quality"]["issues"])
    def write_jsonl(name, rows):
        (output/name).write_text("".join(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n" for row in rows))
    write_jsonl("catalog.jsonl",records);write_jsonl("recipes.jsonl",ready);write_jsonl("review_50.jsonl",review)
    write_jsonl("rejected.jsonl",rejected)
    ingredient_names={}
    for r in records:
        for item in r["ingredient_details"]:
            if item.get("ingredient_id") and "unknown_unit_or_count_basis" not in item["issues"]:
                row=ingredient_names.setdefault(item['ingredient_id'],{"ingredient_id":item['ingredient_id'],"names":set(),"units":set(),"canonical_status":item['canonical_status']})
                row['names'].add(item['canonical_name'])
                if item['normalized']: row['units'].add(item['normalized']['unit'])
    write_jsonl("ingredients.jsonl",[{**v,"names":sorted(v['names']),"units":sorted(v['units'])} for _,v in sorted(ingredient_names.items())])
    report={"source_pages":len(pages),"catalog_records":len(records),"rejected_or_duplicate":len(rejected),"planning_ready":len(ready),"review_queue":len(review),"human_reviewed":0,"allergens_confirmed":0,"has_instructions":sum(bool(r['instructions']) for r in records),"has_servings":sum(r['servings'] is not None for r in records),"has_total_time":sum(r['cook_minutes'] is not None for r in records),"has_cuisine":sum(r['cuisine'] is not None for r in records),"has_meal_type":sum(r['meal_type'] is not None for r in records),"has_nutrition_source":sum(bool(r["nutrition_source"]) for r in records),"has_nutrition":sum(r['nutrition'] is not None for r in records),"fully_quantified":sum(len(r['ingredients'])==len(r['ingredient_details']) for r in records),"ingredient_ids":len(ingredient_names),"quality_issues":dict(sorted(issues.items())),"rejection_reasons":dict(Counter(x['reason'] for x in rejected)),"license":"CC-BY-SA-4.0","license_url":LICENSE,"source_snapshot_sha256":hashlib.sha256(json.dumps(pages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    (output/'quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    return report
