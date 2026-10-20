"""Build data files (ingredients.csv, recipes.jsonl, prices.csv) from real Food.com data.

Downloads Kaggle dataset automatically if not present.

Usage:
    python scripts/build_from_foodcom.py
    python scripts/build_from_foodcom.py --max-recipes 100 --max-ingredients 200
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW_DIR = DATA / "raw"
RAW_CSV = RAW_DIR / "recipes.csv"

# ---------- Constants ----------

DESCRIPTORS = {
    'large', 'small', 'medium', 'fresh', 'dried', 'chopped', 'diced',
    'minced', 'sliced', 'ground', 'whole', 'canned', 'frozen', 'raw',
    'cooked', 'grated', 'shredded', 'melted', 'softened', 'cubed',
    'crushed', 'peeled', 'thinly', 'finely', 'coarsely', 'plain',
    'extra', 'virgin', 'boneless', 'skinless', 'all', 'purpose',
    'organic', 'unsalted', 'salted', 'sweet', 'hot', 'cold',
}

UNIT_TO_FAMILY = {
    'g': ('weight', 1.0), 'gr': ('weight', 1.0), 'gram': ('weight', 1.0),
    'grams': ('weight', 1.0), 'kg': ('weight', 1000.0),
    'oz': ('weight', 28.35), 'ounce': ('weight', 28.35),
    'ounces': ('weight', 28.35), 'lb': ('weight', 453.6),
    'pound': ('weight', 453.6), 'pounds': ('weight', 453.6),
    'ml': ('volume', 1.0), 'milliliter': ('volume', 1.0),
    'milliliters': ('volume', 1.0), 'l': ('volume', 1000.0),
    'liter': ('volume', 1000.0), 'liters': ('volume', 1000.0),
    'cup': ('volume', 240.0), 'cups': ('volume', 240.0),
    'tbsp': ('volume', 15.0), 'tablespoon': ('volume', 15.0),
    'tablespoons': ('volume', 15.0), 'tsp': ('volume', 5.0),
    'teaspoon': ('volume', 5.0), 'teaspoons': ('volume', 5.0),
    'pint': ('volume', 473.0), 'pints': ('volume', 473.0),
    'quart': ('volume', 946.0), 'quarts': ('volume', 946.0),
    'pcs': ('count', 1.0), 'pc': ('count', 1.0), 'piece': ('count', 1.0),
    'pieces': ('count', 1.0), 'clove': ('count', 1.0), 'cloves': ('count', 1.0),
    'slice': ('count', 1.0), 'slices': ('count', 1.0),
    'large': ('count', 1.0), 'small': ('count', 1.0), 'medium': ('count', 1.0),
}

DENSITY = {
    'flour': 0.53, 'sugar': 0.85, 'rice': 0.85, 'oat': 0.4,
    'salt': 1.2, 'butter': 0.95, 'honey': 1.4, 'peanut': 0.6,
    'lentil': 0.85, 'chickpea': 0.85, 'bean': 0.85, 'cheese': 1.0,
    'mushroom': 0.3, 'spinach': 0.1, 'lettuce': 0.1,
    'cocoa': 0.5, 'bread': 0.5, 'cracker': 0.4,
}

EXCLUDE_CATEGORIES = {
    'dessert', 'desserts', 'frozen desserts', 'cakes', 'cookies',
    'cookies and brownies', 'candies', 'beverages', 'pies', 'pies and tarts',
    'pastries', 'breads', 'muffins', 'scones', 'biscuits', 'brownies',
    'ice cream', 'puddings', 'frostings', 'sauces', 'condiments',
    'jams', 'jellies', 'preserves', 'snacks', 'appetizers',
}

PREFER_CATEGORIES = {
    'main dish', 'main dishes', 'side dish', 'side dishes',
    'soups', 'stews', 'salads', 'vegetable', 'vegetables',
    'vegetarian', 'one dish meal', 'casseroles', 'rice', 'pasta',
    'beans', 'lunch', 'dinner',
}

CATEGORY_PRICES = {
    'grain': 0.002, 'protein': 0.01, 'dairy': 0.005, 'fat': 0.008,
    'vegetable': 0.003, 'fruit': 0.4, 'sauce': 0.005, 'spice': 0.02,
    'other': 0.005,
}

REQUIRED_INGREDIENTS = [
    'water', 'salt', 'sugar', 'pepper', 'flour', 'rice', 'egg', 'onion',
    'garlic', 'tomato', 'potato', 'carrot', 'pasta', 'oil', 'olive oil',
    'vegetable oil', 'milk', 'butter', 'cheese', 'soy sauce', 'lemon',
    'banana', 'apple', 'bread', 'oat', 'lentil', 'chickpea', 'bean',
    'spinach', 'mushroom', 'bell pepper', 'cucumber', 'lettuce', 'broccoli',
    'zucchini', 'corn', 'pea', 'honey', 'curry powder', 'cumin', 'paprika',
    'basil', 'oregano', 'tomato paste', 'coconut milk', 'peanut', 'tofu',
    'cabbage', 'pumpkin', 'avocado', 'yogurt', 'noodle', 'couscous',
    'baking powder', 'vanilla', 'cinnamon', 'almond', 'walnut',
]

UNICODE_FRACTIONS = {'½': 0.5, '¼': 0.25, '¾': 0.75,
                     '⅓': 1/3, '⅔': 2/3, '⅛': 0.125}

# ---------- Helpers ----------

def singularize(name: str) -> str:
    if name.endswith('ies') and len(name) > 3:
        return name[:-3] + 'y'
    if name.endswith('oes') and len(name) > 3:
        return name[:-2]
    if name.endswith('es') and len(name) > 3 and name[-3] in 'sxzhc':
        return name[:-2]
    if name.endswith('s') and not name.endswith('ss') and len(name) > 2:
        return name[:-1]
    return name


def clean_ingredient(raw: str) -> str:
    name = str(raw).lower().strip()
    name = re.sub(r'\([^)]*\)', ' ', name)
    name = re.sub(r'[^a-z0-9\s-]', ' ', name)
    words = [w for w in name.split() if w and w not in DESCRIPTORS]
    if not words:
        return ''
    return singularize(' '.join(words).strip())


def to_id(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def parse_c_list(value: str) -> list[str]:
    if value is None:
        return []
    return re.findall(r'"((?:[^"\\]|\\.)*)"', str(value))


def parse_number(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    for u, v in UNICODE_FRACTIONS.items():
        s = s.replace(u, f' {v} ')
    s = s.strip().replace(',', '.')
    if ' ' in s:
        total = 0.0
        for part in s.split():
            v = parse_number(part)
            if v is None:
                return None
            total += v
        return total
    if '/' in s:
        n, d = s.split('/', 1)
        try:
            return float(n) / float(d)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_qty_unit(text: str) -> tuple[float, str] | None:
    text = str(text).strip().lower()
    m = re.match(r'^([\d\s./\u00BD\u00BC\u00BE\u2153\u2154\u215B-]+)', text)
    if not m:
        return None
    qty = parse_number(m.group(1))
    if qty is None or qty <= 0:
        return None
    rest = text[m.end():].strip()
    if not rest:
        return qty, 'pcs'
    first_word = rest.split()[0].rstrip('s.,')
    if first_word in UNIT_TO_FAMILY:
        return qty, first_word
    return qty, 'pcs'


def iso_to_minutes(value: str) -> int | None:
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', str(value or ''))
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def categorize(ing_id: str) -> str:
    if 'oil' in ing_id:
        return 'fat'
    if any(k in ing_id for k in
           ['rice', 'pasta', 'noodle', 'flour', 'oat', 'bread',
            'tortilla', 'couscous', 'bulgur', 'quinoa']):
        return 'grain'
    if any(k in ing_id for k in
           ['egg', 'chicken', 'beef', 'pork', 'fish', 'tofu',
            'lentil', 'bean', 'chickpea', 'cheese', 'yogurt', 'almond', 'walnut', 'peanut']):
        return 'protein'
    if 'milk' in ing_id:
        return 'dairy'
    if any(k in ing_id for k in
           ['salt', 'pepper', 'cumin', 'paprika', 'oregano', 'basil',
            'thyme', 'cinnamon', 'chili', 'turmeric', 'ginger', 'vanilla']):
        return 'spice'
    if any(k in ing_id for k in
           ['sauce', 'paste', 'vinegar', 'honey', 'syrup']):
        return 'sauce'
    if any(k in ing_id for k in
           ['banana', 'apple', 'lemon', 'lime', 'avocado', 'orange']):
        return 'fruit'
    if any(k in ing_id for k in
           ['tomato', 'onion', 'garlic', 'potato', 'carrot', 'broccoli',
            'spinach', 'cucumber', 'pepper', 'mushroom', 'zucchini',
            'cabbage', 'corn', 'pea', 'lettuce', 'pumpkin']):
        return 'vegetable'
    return 'other'


def convert_to_base(qty: float, unit: str, base_unit: str, ing_name: str) -> float | None:
    family, factor = UNIT_TO_FAMILY.get(unit, ('unknown', None))
    if factor is None:
        return None
    if family == 'weight' and base_unit == 'g':
        return qty * factor
    if family == 'weight' and base_unit == 'ml':
        density = 1.0
        for key, val in DENSITY.items():
            if key in ing_name:
                density = val
                break
        return qty * factor / density
    if family == 'weight' and base_unit == 'pcs':
        return None
    if family == 'volume' and base_unit == 'ml':
        return qty * factor
    if family == 'volume' and base_unit == 'g':
        density = 1.0
        for key, val in DENSITY.items():
            if key in ing_name:
                density = val
                break
        return qty * factor * density
    if family == 'volume' and base_unit == 'pcs':
        return None
    if family == 'count' and base_unit == 'pcs':
        return qty * factor
    if family == 'count':
        return None
    return None


# ---------- Main pipeline ----------

def download_if_missing():
    if RAW_CSV.exists():
        print(f"Raw data exists: {RAW_CSV} ({RAW_CSV.stat().st_size / 1e6:.1f} MB)")
        return
    print("Downloading Food.com dataset from Kaggle...")
    try:
        import kagglehub
    except ImportError:
        print("ERROR: kagglehub not installed. Run: pip install kagglehub")
        sys.exit(1)
    try:
        ds_path = Path(kagglehub.dataset_download("irkaal/foodcom-recipes-and-reviews"))
    except Exception as e:
        print(f"ERROR downloading: {e}")
        print("Make sure ~/.kaggle/kaggle.json exists (chmod 600).")
        sys.exit(1)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    src = ds_path / "recipes.csv"
    if not src.exists():
        for p in ds_path.rglob("recipes.csv"):
            src = p
            break
    import shutil
    shutil.copy(src, RAW_CSV)
    print(f"Saved: {RAW_CSV} ({RAW_CSV.stat().st_size / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default=str(RAW_CSV))
    ap.add_argument('--max-recipes', type=int, default=100)
    ap.add_argument('--max-ingredients', type=int, default=400)
    ap.add_argument('--min-recipes', type=int, default=50)
    args = ap.parse_args()

    download_if_missing()

    raw_path = Path(args.raw)
    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found")
        sys.exit(1)

    print(f"\nScanning {raw_path} ...")

    # ---- Pass 1: collect candidates and ingredient stats ----
    ingredient_freq: Counter = Counter()
    ingredient_units: dict[str, Counter] = defaultdict(Counter)
    candidates: list[dict] = []

    with open(raw_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        NON_VEG_KEYWORDS = {
            'chicken', 'beef', 'pork', 'fish', 'salmon', 'tuna', 'shrimp', 'prawn',
            'bacon', 'ham', 'sausage', 'lamb', 'turkey', 'duck', 'anchovy',
            'sardine', 'mackerel', 'crab', 'lobster', 'oyster', 'clam', 'mussel',
            'scallop', 'squid', 'octopus', 'veal', 'goat', 'venison', 'rabbit',
            'gelatin', 'gelatine', 'lard', 'tallow', 'meat', 'poultry', 'seafood',
            'mince', 'steak', 'rib', 'wing', 'thigh', 'breast',
        }

        for i, row in enumerate(reader, 1):
            category = str(row.get('RecipeCategory', '')).strip().lower()
            if category in EXCLUDE_CATEGORIES:
                continue
            minutes = iso_to_minutes(row.get('CookTime'))
            if minutes is None or not (10 <= minutes <= 30):
                continue

            parts = parse_c_list(row.get('RecipeIngredientParts'))
            qtys = parse_c_list(row.get('RecipeIngredientQuantities'))
            if not parts or len(parts) != len(qtys) or len(parts) < 3:
                continue

            ingredients_lower = ' ' + ' '.join(p.lower() for p in parts) + ' '
            if any(f' {kw} ' in ingredients_lower for kw in NON_VEG_KEYWORDS):
                continue

            parsed = []
            ok = True
            for part, qty_text in zip(parts, qtys):
                cleaned = clean_ingredient(part)
                if not cleaned:
                    ok = False
                    break
                qu = parse_qty_unit(qty_text)
                if qu is None:
                    ok = False
                    break
                qty, unit = qu
                parsed.append({
                    'name': cleaned,
                    'id': to_id(cleaned),
                    'qty': qty,
                    'unit': unit,
                })
                ingredient_freq[cleaned] += 1
                ingredient_units[cleaned][unit] += 1
            if not ok:
                continue

            candidates.append({'row': row, 'parsed': parsed, 'minutes': minutes})
            if i % 50000 == 0:
                print(f"  scanned {i} rows, {len(candidates)} candidates")

    print(f"\nScan done: {len(candidates)} candidate recipes, "
          f"{len(ingredient_freq)} unique ingredients")

    # ---- Determine base_unit per ingredient ----
    ingredient_base: dict[str, str] = {}
    ingredient_category: dict[str, str] = {}

    for name in ingredient_freq:
        units = ingredient_units[name]
        weight = sum(c for u, c in units.items() if UNIT_TO_FAMILY.get(u, ('',0))[0] == 'weight')
        volume = sum(c for u, c in units.items() if UNIT_TO_FAMILY.get(u, ('',0))[0] == 'volume')
        count = sum(c for u, c in units.items() if UNIT_TO_FAMILY.get(u, ('',0))[0] == 'count')
        cat = categorize(to_id(name))
        if count >= max(weight, volume):
            base = 'pcs'
        elif weight >= volume:
            base = 'g'
        else:
            base = 'ml' if cat in ('fat', 'sauce', 'dairy') else 'g'
        ingredient_base[name] = base
        ingredient_category[name] = cat

    # ---- Build final ingredient list ----
    final_names: list[str] = []
    seen_ids: set[str] = set()
    for name in REQUIRED_INGREDIENTS:
        iid = to_id(name)
        if iid in seen_ids:
            continue
        final_names.append(name)
        seen_ids.add(iid)
        if name not in ingredient_base:
            cat = categorize(iid)
            ingredient_base[name] = (
                'ml' if cat in ('fat', 'sauce', 'dairy')
                else 'pcs' if cat == 'fruit'
                else 'g'
            )
            ingredient_category[name] = cat

    for name, _ in ingredient_freq.most_common(args.max_ingredients):
        iid = to_id(name)
        if iid in seen_ids:
            continue
        final_names.append(name)
        seen_ids.add(iid)

    keep_ids = seen_ids
    print(f"Final ingredients: {len(final_names)}")

    # ---- Write ingredients.csv ----
    out = DATA / 'ingredients.csv'
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['ingredient_id', 'canonical_name', 'aliases', 'base_unit', 'category'])
        for name in final_names:
            w.writerow([to_id(name), name, name,
                        ingredient_base[name], ingredient_category[name]])
    print(f"Wrote {out}: {len(final_names)} ingredients")

    # ---- Write recipes.jsonl ----
    # Приоритизация: mains/sides/soups/salads сначала, потом все остальные
    def _cat(rec):
        return str(rec['row'].get('RecipeCategory', '')).strip().lower()

    main_recs = [r for r in candidates if _cat(r) in PREFER_CATEGORIES]
    other_recs = [r for r in candidates if _cat(r) not in PREFER_CATEGORIES]
    ordered = main_recs + other_recs

    written = 0
    out = DATA / 'recipes.jsonl'
    with open(out, 'w', encoding='utf-8') as f:
        for rec in ordered:
            if written >= args.max_recipes:
                break
            converted = []
            ok = True
            for ing in rec['parsed']:
                iid = ing['id']
                if iid not in keep_ids:
                    ok = False
                    break
                base = ingredient_base[ing['name']]
                qty = convert_to_base(ing['qty'], ing['unit'], base, ing['name'])
                if qty is None or qty <= 0:
                    ok = False
                    break
                converted.append({
                    'ingredient_id': iid,
                    'quantity': round(qty, 2),
                    'unit': base,
                })
            if not ok or len(converted) < 3:
                continue
            # Dedupe
            by_id: dict[str, dict] = {}
            for c in converted:
                if c['ingredient_id'] in by_id:
                    by_id[c['ingredient_id']]['quantity'] = round(
                        by_id[c['ingredient_id']]['quantity'] + c['quantity'], 2)
                else:
                    by_id[c['ingredient_id']] = dict(c)
            ings = list(by_id.values())
            if len(ings) < 3:
                continue

            try:
                servings = max(1, min(20, int(float(rec['row'].get('RecipeServings')))))
            except (ValueError, TypeError):
                servings = 2

            tags = ['vegetarian']
            protein_keys = {'egg', 'tofu', 'lentil', 'chickpea', 'bean',
                            'cheese', 'milk', 'yogurt', 'almond', 'walnut', 'peanut'}
            if any(any(k in i['ingredient_id'] for k in protein_keys) for i in ings):
                tags.append('high_protein')

            written += 1
            record = {
                'recipe_id': f'r{written:03d}',
                'title': str(rec['row'].get('Name', '')).strip()[:80],
                'servings': servings,
                'cook_minutes': int(rec['minutes']),
                'tags': tags,
                'ingredients': ings,
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    print(f"Wrote {out}: {written} recipes")

    # ---- Write prices.csv ----
    out = DATA / 'prices.csv'
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['ingredient_id', 'unit', 'price_per_unit', 'currency'])
        for name in final_names:
            cat = ingredient_category[name]
            base = ingredient_base[name]
            price = CATEGORY_PRICES.get(cat, 0.005)
            if 'salt' in name:
                price = 0.0005
            elif 'water' in name:
                price = 0.0001
            elif 'oil' in name and base == 'ml':
                price = 0.008
            w.writerow([to_id(name), base, round(price, 5), 'CU'])
    print(f"Wrote {out}: {len(final_names)} prices")

    print(f"\n{'='*50}")
    print(f"Summary: {len(final_names)} ingredients, {written} recipes")
    if written < args.min_recipes:
        print(f"WARNING: {written} < min {args.min_recipes}. "
              f"Try --max-ingredients 300 or --max-recipes 150")
        sys.exit(1)
    print("OK")


if __name__ == '__main__':
    main()
