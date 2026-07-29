"""
Дампит сырые данные из 1SCONST.DBF для базы Шишиной:
- Уникальные ID в 1SCONST (чтобы найти правильный const_id_field)
- Строки SC3772 с DESCR="Розничная" (проверяем что SC3772 читается верно)
- Несколько примеров JOIN SC3772 -> 1SCONST

Запускать на Windows рядом с config.json:
    python diagnose_1sconst_raw.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "dbfread"))

from main import read_dbf_table

CONFIG_PATH = Path(__file__).parent / "config.json"


def main():
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    shish = next(b for b in config["bases"] if b["name"] == "Шишина")
    base = Path(shish["path"])
    enc = shish.get("encoding", "cp1251")

    sc3772_table = shish.get("price_markup_table", "SC3772.DBF")
    const_table = shish.get("price_const_table", "1SCONST.DBF")
    descr_field = shish.get("price_markup_descr_field", "DESCR")
    parent_field = shish.get("price_markup_parent_field", "PARENTEXT")
    type_name = shish.get("price_markup_type_name", "Розничная")
    price_const_id = shish.get("price_const_id", "2WV")

    print("База: {0}".format(base))
    print("SC3772: {0}".format(sc3772_table))
    print("1SCONST: {0}".format(const_table))
    print("price_const_id из конфига: '{0}'".format(price_const_id))
    print()

    # --- Шаг 1: SC3772 ---
    print("=== SC3772: все уникальные DESCR (типы цен) ===")
    descr_counts = {}
    sc3772_rozn = {}
    try:
        for row in read_dbf_table(base, sc3772_table, enc):
            d = str(row.get(descr_field, "")).strip()
            descr_counts[d] = descr_counts.get(d, 0) + 1
            if d == type_name:
                sc_id = str(row.get("ID", "")).strip()
                item_id = str(row.get(parent_field, "")).strip()
                if sc_id and item_id:
                    sc3772_rozn[sc_id] = item_id
    except Exception as e:
        print("ОШИБКА при чтении SC3772: {0}".format(e))
        return

    for d, cnt in sorted(descr_counts.items(), key=lambda x: -x[1]):
        marker = " <-- ЭТО МЫ ИЩЕМ" if d == type_name else ""
        print("  '{0}': {1} записей{2}".format(d, cnt, marker))
    print("Итого '{0}' в SC3772: {1} записей".format(type_name, len(sc3772_rozn)))
    print()

    if not sc3772_rozn:
        print("ПРОБЛЕМА: SC3772 не содержит записей с DESCR='{0}'!".format(type_name))
        print("Возможные причины:")
        print("  1. Поле DESCR называется иначе (не '{0}')".format(descr_field))
        print("  2. Тип цены называется иначе (не '{0}')".format(type_name))
        return

    # --- Шаг 2: 1SCONST ---
    print("=== 1SCONST: уникальные значения поля ID ===")
    id_counts = {}
    id_values = {}
    try:
        for row in read_dbf_table(base, const_table, enc):
            cid = str(row.get("ID", "")).strip()
            id_counts[cid] = id_counts.get(cid, 0) + 1
            if cid not in id_values:
                id_values[cid] = str(row.get("VALUE", "")).strip()
    except Exception as e:
        print("ОШИБКА при чтении 1SCONST: {0}".format(e))
        return

    print("Всего уникальных ID в 1SCONST: {0}".format(len(id_counts)))
    print("Топ-15 по кол-ву записей:")
    for cid, cnt in sorted(id_counts.items(), key=lambda x: -x[1])[:15]:
        sample = id_values.get(cid, "")
        marker = " <-- price_const_id из конфига" if cid == price_const_id else ""
        print("  '{0}': {1} записей, пример VALUE='{2}'{3}".format(cid, cnt, sample[:30], marker))
    print()

    if price_const_id not in id_counts:
        print("ПРОБЛЕМА: ID='{0}' НЕ НАЙДЕН в 1SCONST!".format(price_const_id))
        print("Нужно уточнить правильный const_id_field.")
    else:
        print("ID='{0}' найден: {1} записей.".format(price_const_id, id_counts[price_const_id]))

    # --- Шаг 3: JOIN SC3772 -> 1SCONST ---
    print()
    print("=== JOIN: 1SCONST по SC3772 'Розничная' с ID='{0}' ===".format(price_const_id))
    found = {}
    try:
        for row in read_dbf_table(base, const_table, enc):
            objid = str(row.get("OBJID", "")).strip()
            if objid not in sc3772_rozn:
                continue
            if str(row.get("ID", "")).strip() != price_const_id:
                continue
            val = str(row.get("VALUE", "")).strip()
            try:
                price = float(val)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            found[sc3772_rozn[objid]] = price
    except Exception as e:
        print("ОШИБКА: {0}".format(e))
        return

    print("Товаров с ценой из 1SCONST: {0}".format(len(found)))
    if found:
        print("Несколько примеров:")
        for item_id, price in list(found.items())[:10]:
            print("  item_id={0} -> цена={1:.2f}".format(item_id, price))
    else:
        print()
        print("ПРОБЛЕМА: JOIN дал 0 результатов.")
        print("Проверяем возможные причины...")
        # Поищем хоть одну строку 1SCONST где OBJID совпадает с SC3772
        sample_sc_ids = list(sc3772_rozn.keys())[:5]
        print("Ищем в 1SCONST OBJID из SC3772 (первые 5): {0}".format(sample_sc_ids))
        match_count = 0
        all_ids_for_matched = set()
        try:
            for row in read_dbf_table(base, const_table, enc):
                objid = str(row.get("OBJID", "")).strip()
                if objid in sc3772_rozn:
                    match_count += 1
                    all_ids_for_matched.add(str(row.get("ID", "")).strip())
        except Exception as e:
            print("Ошибка: {0}".format(e))
        print("Строк 1SCONST с OBJID из SC3772 'Розничная': {0}".format(match_count))
        if all_ids_for_matched:
            print("ID в этих строках: {0}".format(sorted(all_ids_for_matched)))
            print()
            print("Правильный const_id_field скорее всего один из: {0}".format(
                [x for x in all_ids_for_matched if x != price_const_id]))
        else:
            print("Совпадений нет — OBJID в 1SCONST не совпадает с ID в SC3772.")
            print("Проверим формат OBJID: первые 5 строк 1SCONST:")
            try:
                cnt2 = 0
                for row in read_dbf_table(base, const_table, enc):
                    if cnt2 >= 5:
                        break
                    print("  OBJID='{0}' ID='{1}' VALUE='{2}'".format(
                        str(row.get("OBJID","")).strip(),
                        str(row.get("ID","")).strip(),
                        str(row.get("VALUE","")).strip()[:20]))
                    cnt2 += 1
            except Exception as e:
                print("Ошибка: {0}".format(e))


if __name__ == "__main__":
    main()
