"""
Проверяет работу нового метода чтения цен из 1SCONST для SQL-базы.
Выводит: сколько товаров получили цену, несколько примеров с артикулом и ценой.

Совместимо с Python 3.4.

Использование:
    python check_price_from_const.py <индекс_базы 1-4>

Пример:
    python check_price_from_const.py 2
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

    # Запрос: JOIN SC3772 + 1SCONST, фильтр по типу и const_id
    query = (
        "SELECT sc.{parent}, const.VALUE, const.DATE "
        "FROM {sc3772} sc "
        "JOIN {const} const ON LTRIM(RTRIM(const.OBJID)) = LTRIM(RTRIM(sc.ID)) "
        "WHERE LTRIM(RTRIM(sc.{descr})) = N'{type}' "
        "AND LTRIM(RTRIM(const.ID)) = '{cid}' "
        "AND ISNUMERIC(LTRIM(RTRIM(const.VALUE))) = 1 "
        "AND CAST(LTRIM(RTRIM(const.VALUE)) AS FLOAT) > 0"
    ).format(
        parent=parent_field, sc3772=sc3772_table, const=const_table,
        descr=descr_field, type=type_name, cid=const_id,
    )

    print("Выполняю запрос...")
    rows = run_query(server, database, user, password, query)
    print("Строк в результате: {0}".format(len(rows)))

    # Берём последнюю дату для каждого товара
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

    # Подтягиваем артикулы для первых 20
    items_table = base_cfg.get("items_table", "SC4889")
    article_field = base_cfg.get("items_article_field", "SP4890")
    item_ids = list(result.keys())[:20]
    id_list = ", ".join("'" + i + "'" for i in item_ids)
    art_rows = run_query(server, database, user, password,
        "SELECT ID, {0} FROM {1} WHERE LTRIM(RTRIM(ID)) IN ({2})".format(
            article_field, items_table, id_list))
    art_map = {}
    for r in art_rows:
        if len(r) >= 2:
            art_map[r[0].strip()] = r[1].strip()

    print("\nПримеры (первые 20):")
    for item_id in item_ids:
        art = art_map.get(item_id, "?")
        price = result[item_id]
        date = result_date.get(item_id, "?")
        print("  {0:10} арт={1:15} цена={2:.2f} ({3})".format(item_id, art, price, date))


def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python check_price_from_const.py <индекс_базы 1-4>")
    index = int(sys.argv[1])
    log_filename = "check_price_from_const_log.txt"
    commit_message = "Проверка цен из 1SCONST (база {0})".format(index)
    run_with_log(log_filename, commit_message, lambda: run(index))


if __name__ == "__main__":
    main()
