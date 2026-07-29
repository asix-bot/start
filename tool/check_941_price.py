"""
Дампит все 1SCONST записи для артикула 941 (и других проблемных).
Запускать на Windows: python check_941_price.py
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "dbfread"))
from main import read_dbf_table

CONFIG_PATH = Path(__file__).parent / "config.json"
config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
shish = next(b for b in config["bases"] if b["name"] == "Шишина")
base = Path(shish["path"])
enc = shish.get("encoding", "cp1251")

# Артикулы без суффикса -> item_id
ARTS = ["941", "840", "27", "104", "873", "20", "22", "23", "41", "302", "76"]
XLS  = {"941":6300,"840":5350,"27":3490,"104":3740,"873":5500,
        "20":3450,"22":2590,"23":2590,"41":3490,"302":3740,"76":2760}

art_to_id = {}
for r in read_dbf_table(base, shish.get("items_table","SC4889.DBF"), enc):
    art = str(r.get(shish.get("items_article_field","SP4890"), "")).strip()
    iid = str(r.get("ID","")).strip()
    if art in ARTS and iid:
        art_to_id[art] = iid

print("Артикул -> item_id:")
for a in ARTS:
    print("  {0} -> {1}".format(a, art_to_id.get(a,"НЕТ")))

# SC3772 "Розничная" -> sc_id для каждого item_id
type_name = shish.get("price_markup_type_name","Розничная")
sc3772_table = shish.get("price_markup_table","SC3772.DBF")
item_to_sc = {}
for r in read_dbf_table(base, sc3772_table, enc):
    if str(r.get("DESCR","")).strip() == type_name:
        item_id = str(r.get("PARENTEXT","")).strip()
        sc_id   = str(r.get("ID","")).strip()
        if item_id in art_to_id.values():
            item_to_sc[item_id] = sc_id

print("\nSC3772 'Розничная' -> SC ID:")
for art in ARTS:
    iid = art_to_id.get(art)
    sc_id = item_to_sc.get(iid,"НЕТ") if iid else "НЕТ"
    print("  {0} (item={1}) -> sc_id={2}".format(art, iid or "?", sc_id))

# 1SCONST записи для каждого SC ID
const_table = shish.get("price_const_table","1SCONST.DBF")
const_id    = shish.get("price_const_id","2WV")
sc_ids = set(item_to_sc.values())

print("\n1SCONST записи (ID={0}):".format(const_id))
records = {}
for r in read_dbf_table(base, const_table, enc):
    objid = str(r.get("OBJID","")).strip()
    cid   = str(r.get("ID","")).strip()
    if objid in sc_ids and cid == const_id:
        val  = str(r.get("VALUE","")).strip()
        date = r.get("DATE")
        records.setdefault(objid, []).append((date, val))

sc_to_art = {v: k for k, v in
             {a: item_to_sc.get(art_to_id.get(a,""),"") for a in ARTS}.items()
             if v}
for sc_id in sorted(sc_ids):
    art = sc_to_art.get(sc_id, sc_id)
    recs = sorted(records.get(sc_id, []), key=lambda x: str(x[0]))
    xls_p = XLS.get(art, "?")
    print("  Арт={0} sc_id={1} XLS={2}".format(art, sc_id, xls_p))
    if not recs:
        print("    (нет записей)")
    for date, val in recs:
        try:
            price = float(val.replace(",","."))
            mark = " <-- БЕРЁМ" if recs and (date, val) == sorted(recs, key=lambda x: str(x[0]))[-1] else ""
        except:
            mark = ""
        print("    DATE={0}  VALUE={1:>12}{2}".format(date, val, mark))

print("\nГотово.")
