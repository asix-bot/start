"""
Диагностика: сравнивает цены из DT3580 vs 1SCONST для базы Шишиной.
Запускать на Windows рядом с config.json.

Использование:
    python diagnose_shishina_prices.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "dbfread"))

from main import (
    read_dbf_doc_date_map, read_dbf_latest_doc_value_map,
    read_dbf_price_from_const,
)
from dbfread import DBF

CONFIG_PATH = Path(__file__).parent / "config.json"

def main():
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    shish = next(b for b in config["bases"] if b["name"] == "Шишина")
    base = Path(shish["path"])
    enc = shish.get("encoding", "cp1251")

    print("База: {0}".format(base))

    # Читаем SC4889 -> article -> item_id
    sc4889 = DBF(str(base / shish["items_table"]), encoding=enc, ignore_missing_memofile=True)
    art_to_id = {}
    for r in sc4889:
        art = str(r.get(shish.get("items_article_field","SP4890"), "")).strip()
        iid = str(r.get("ID","")).strip()
        if art and iid:
            art_to_id[art] = iid

    print("Товаров в SC4889: {0}".format(len(art_to_id)))

    # DT3580 — цены из документов
    try:
        doc_date_map = read_dbf_doc_date_map(base, "1SJOURN.DBF", enc)
        dt3580 = read_dbf_latest_doc_value_map(
            base, shish["sale_price_table"],
            shish["sale_price_item_field"], shish["sale_price_value_field"],
            shish.get("sale_price_doc_field","IDDOC"), doc_date_map, enc)
        print("DT3580: получено {0} цен".format(len(dt3580)))
    except Exception as e:
        dt3580 = {}
        print("DT3580 ОШИБКА: {0}".format(e))

    # 1SCONST — прямые розничные цены
    try:
        const_prices = read_dbf_price_from_const(
            base,
            shish["price_markup_table"],
            shish.get("price_const_table","1SCONST.DBF"),
            enc,
            shish.get("price_markup_parent_field","PARENTEXT"),
            shish.get("price_markup_descr_field","DESCR"),
            shish.get("price_markup_type_name","Розничная"),
            shish.get("price_const_id","2WV"),
        )
        print("1SCONST: получено {0} цен".format(len(const_prices)))
    except Exception as e:
        const_prices = {}
        print("1SCONST ОШИБКА: {0}".format(e))

    # Итоговая цена (как в export_base_dbf)
    final = dict(dt3580)
    final.update(const_prices)

    # Расхождения: DT3580 != 1SCONST (у кого источники расходятся)
    print("\n=== РАСХОЖДЕНИЯ DT3580 vs 1SCONST (с остатком > 0) ===")
    # Читаем остатки чтобы показывать только реальные товары
    from main import read_dbf_latest_period_map
    stock_map = read_dbf_latest_period_map(
        base, shish["stock_table"], shish["stock_item_field"],
        shish.get("stock_period_field","PERIOD"), shish["stock_qty_field"], enc,
        shish.get("stock_extra_filter_field"), shish.get("stock_extra_filter_value"))

    id_to_art = {v: k for k, v in art_to_id.items()}
    diffs = []
    for iid in set(list(dt3580.keys()) + list(const_prices.keys())):
        if float(stock_map.get(iid, 0) or 0) <= 0:
            continue
        d = dt3580.get(iid)
        c = const_prices.get(iid)
        if d is not None and c is not None and abs(float(d) - float(c)) > 1:
            diffs.append((id_to_art.get(iid,'?'), iid, d, c))

    if diffs:
        print("{:<12} {:<8} {:>12} {:>12}".format("Артикул","item_id","DT3580","1SCONST"))
        print("-" * 46)
        for art, iid, d, c in sorted(diffs, key=lambda x: x[0]):
            print("{:<12} {:<8} {:>12.2f} {:>12.2f}".format(art, iid, float(d), float(c)))
        print("\nВсего расхождений: {0}".format(len(diffs)))
    else:
        print("Расхождений нет или нет данных в DT3580.")

    print("\n=== ИТОГОВЫЕ ЦЕНЫ (что попадёт в CSV, топ-20 с остатком) ===")
    with_stock = [(id_to_art.get(iid,'?'), float(stock_map.get(iid,0) or 0), final.get(iid))
                  for iid in stock_map if float(stock_map.get(iid,0) or 0) > 0]
    with_stock.sort(key=lambda x: -x[1])
    print("{:<14} {:>8} {:>12}".format("Артикул","Остаток","Цена CSV"))
    print("-" * 36)
    for art, qty, price in with_stock[:20]:
        print("{:<14} {:>8.1f} {:>12}".format(art, qty, "{:.2f}".format(price) if price else "—"))

if __name__ == "__main__":
    main()
