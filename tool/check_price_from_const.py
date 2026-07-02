"""
Проверяет работу нового метода чтения цен из 1SCONST для SQL-базы.
Выводит: сколько товаров получили цену, несколько примеров с артикулом и ценой.
Также дампит все уникальные const ID из 1SCONST для объектов SC3772 —
чтобы найти правильный ID поля "Цена" если 2WV не подходит.

Совместимо с Python 3.4.

Использование:
    python check_price_from_const.py <индекс_базы 1-4>
"""

import json
import sys
from pathlib import Path

from diagnostic_log import run_with_log
from sqlcmd_client import run_query

CONFIG_PATH = Path(__file__).parent / "config.json"


def run(index):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    print("База: {0} (тип: {1})".format(base_cfg["name"], base_cfg.get("type", "dbf")))

    if base_cfg.get("type", "dbf") != "sql":
        print("Эта проверка только для SQL-баз.")
        return

    server = base_cfg["sql_server"]
    database = base_cfg["sql_database"]
    sql_auth = config.get("sql_auth", {})
    user = sql_auth["user"]
    password = sql_auth["password"]

    sc3772_table = base_cfg.get("price_markup_table", "SC3772")
    const_table = base_cfg.get("price_const_table", "1SCONST")
    parent_field = base_cfg.get("price_markup_parent_field", "PARENTEXT")
    descr_field = base_cfg.get("price_markup_descr_field", "DESCR")
    type_name = base_cfg.get("price_markup_type_name", "Розничная")
    const_id = base_cfg.get("price_const_id", "2WV")

    print("SC3772={0}, 1SCONST={1}, const_id={2}, type_name={3}".format(
        sc3772_table, const_table, const_id, type_name))

    def bracket(t):
        return "[{0}]".format(t) if t and t[0].isdigit() else t

    sc3772_b = bracket(sc3772_table)
    const_b = bracket(const_table)

    # Шаг 1: найти все уникальные const ID в 1SCONST для объектов SC3772
    print("\n--- Шаг 1: уникальные const ID в 1SCONST для SC3772 объектов ---")
    id_query = (
        "SELECT LTRIM(RTRIM(c.ID)) as CID, COUNT(*) as CNT, "
        "MIN(LTRIM(RTRIM(c.VALUE))) as SAMPLE_VAL "
        "FROM {sc3772} sc "
        "JOIN {const} c ON LTRIM(RTRIM(c.OBJID)) = LTRIM(RTRIM(sc.ID)) "
        "WHERE LTRIM(RTRIM(sc.{descr})) = N'{type}' "
        "GROUP BY LTRIM(RTRIM(c.ID)) "
        "ORDER BY CNT DESC"
    ).format(sc3772=sc3772_b, const=const_b, descr=descr_field, type=type_name)

    id_rows = run_query(server, database, user, password, id_query)
    print("Найдено уникальных const ID: {0}".format(len(id_rows)))
    for r in id_rows:
        print("  ID={0}  count={1}  sample_value={2}".format(
            r[0] if len(r) > 0 else "?",
            r[1] if len(r) > 1 else "?",
            r[2] if len(r) > 2 else "?",
        ))

    # Шаг 2: const ID с числовыми ненулевыми значениями
    print("\n--- Шаг 2: const ID с числовыми значениями > 0 ---")
    num_query = (
        "SELECT LTRIM(RTRIM(c.ID)) as CID, "
        "MAX(CAST(LTRIM(RTRIM(c.VALUE)) AS FLOAT)) as MAX_VAL, "
        "COUNT(*) as CNT "
        "FROM {sc3772} sc "
        "JOIN {const} c ON LTRIM(RTRIM(c.OBJID)) = LTRIM(RTRIM(sc.ID)) "
        "WHERE LTRIM(RTRIM(sc.{descr})) = N'{type}' "
        "AND ISNUMERIC(LTRIM(RTRIM(c.VALUE))) = 1 "
        "AND CAST(LTRIM(RTRIM(c.VALUE)) AS FLOAT) > 0 "
        "GROUP BY LTRIM(RTRIM(c.ID)) "
        "ORDER BY CNT DESC"
    ).format(sc3772=sc3772_b, const=const_b, descr=descr_field, type=type_name)

    try:
        num_rows = run_query(server, database, user, password, num_query)
        print("const ID с ненулевыми числовыми значениями:")
        for r in num_rows:
            print("  ID={0}  max_value={1}  count={2}".format(
                r[0] if len(r) > 0 else "?",
                r[1] if len(r) > 1 else "?",
                r[2] if len(r) > 2 else "?",
            ))
    except Exception as e:
        print("Ошибка шага 2:", e)

    # Шаг 3: основной запрос с текущим const_id
    print("\n--- Шаг 3: основной запрос (const_id={0}) ---".format(const_id))
    query = (
        "SELECT sc.{parent}, c.VALUE, c.DATE "
        "FROM {sc3772} sc "
        "JOIN {const} c ON LTRIM(RTRIM(c.OBJID)) = LTRIM(RTRIM(sc.ID)) "
        "WHERE LTRIM(RTRIM(sc.{descr})) = N'{type}' "
        "AND LTRIM(RTRIM(c.ID)) = '{cid}' "
        "AND ISNUMERIC(LTRIM(RTRIM(c.VALUE))) = 1 "
        "AND CAST(LTRIM(RTRIM(c.VALUE)) AS FLOAT) > 0"
    ).format(
        parent=parent_field, sc3772=sc3772_b, const=const_b,
        descr=descr_field, type=type_name, cid=const_id,
    )
    rows = run_query(server, database, user, password, query)
    print("Строк в результате: {0}".format(len(rows)))

    result = {}
    result_date = {}
    for row in rows:
        if len(row) < 2:
            continue
        item_id = row[0].strip()
        val = row[1].strip().replace(",", ".")
        date_str = row[2].strip() if len(row) > 2 else ""
        try:
            price = float(val)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        prev_date = result_date.get(item_id)
        if prev_date is None or date_str > prev_date:
            result[item_id] = price
            result_date[item_id] = date_str

    print("Уникальных товаров с ценой: {0}".format(len(result)))

    if result:
        items_table = base_cfg.get("items_table", "SC4889")
        article_field = base_cfg.get("items_article_field", "SP4890")
        item_ids = list(result.keys())[:10]
        id_list = ", ".join("'" + i + "'" for i in item_ids)
        art_rows = run_query(server, database, user, password,
            "SELECT ID, {0} FROM {1} WHERE LTRIM(RTRIM(ID)) IN ({2})".format(
                article_field, items_table, id_list))
        art_map = {r[0].strip(): r[1].strip() for r in art_rows if len(r) >= 2}
        print("\nПримеры:")
        for item_id in item_ids:
            print("  {0:10} арт={1:15} цена={2:.2f} ({3})".format(
                item_id, art_map.get(item_id, "?"), result[item_id], result_date.get(item_id, "?")))


def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python check_price_from_const.py <индекс_базы 1-4>")
    index = int(sys.argv[1])
    log_filename = "check_price_from_const_log.txt"
    commit_message = "Проверка цен из 1SCONST (база {0})".format(index)
    run_with_log(log_filename, commit_message, lambda: run(index))


if __name__ == "__main__":
    main()
