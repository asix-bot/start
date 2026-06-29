"""
Диагностика связи цены/себестоимости с датой документа: по артикулу находит
строки в avg_cost_table/sale_price_table (с их IDDOC) и для каждого IDDOC
проверяет, нашёлся ли он в 1SJOURN (глобальный журнал документов, см.
doc_date_table_name в main.py) - и если нашёлся, какая там дата.

Нужно, чтобы понять, почему main.py выбирает именно ТУ строку, что выбирает -
если для всех IDDOC этого товара 1SJOURN не находит совпадений, main.py
тихо переходит на запасной вариант (любая найденная строка, без гарантии
"последняя") - и тогда нужно разбираться, почему 1SJOURN не совпадает
(другое имя таблицы/поля, отсутствие файла и т.п.).

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python check_doc_join.py <индекс_базы 1-4> <артикул_без_суффикса>

Пример:
    python check_doc_join.py 1 20
    python check_doc_join.py 3 7132
"""

import json
import sys
from pathlib import Path

from dbfread import DBF
from diagnostic_log import run_with_log
from sqlcmd_client import run_query, run_query_raw

CONFIG_PATH = Path(__file__).parent / "config.json"


def doc_date_table_name(base_cfg):
    name = base_cfg.get("doc_date_table") or "1SJOURN"
    if base_cfg.get("type", "dbf") == "dbf" and not name.upper().endswith(".DBF"):
        name += ".DBF"
    return name


def read_dbf_table(base_path, table_name, encoding):
    table_path = base_path / table_name
    if not table_path.exists():
        candidates = list(base_path.glob("{0}.*".format(table_name.split(".")[0])))
        if not candidates:
            raise FileNotFoundError("Таблица {0} не найдена в {1}".format(table_name, base_path))
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def run(index, article):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    doc_date_table = doc_date_table_name(base_cfg)
    print("База: {0} ({1}), avg_cost_table={2}, sale_price_table={3}, doc_date_table={4}".format(
        base_cfg["name"], base_cfg.get("type", "dbf"),
        base_cfg.get("avg_cost_table"), base_cfg.get("sale_price_table"), doc_date_table,
    ))

    is_sql = base_cfg.get("type", "dbf") == "sql"
    if is_sql:
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        sql_auth = config.get("sql_auth", {})
        user = sql_auth["user"]
        password = sql_auth["password"]

        try:
            print("\n--- Тест доступности {0}: первые 3 строки ---".format(doc_date_table))
            print(run_query_raw(server, database, user, password, "SELECT TOP 3 IDDOC, DATE FROM {0}".format(doc_date_table)))
        except Exception as exc:
            print("ОШИБКА при чтении {0}: {1}".format(doc_date_table, exc))
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))
        try:
            print("\n--- Тест доступности {0}: первые 3 строки ---".format(doc_date_table))
            shown = 0
            for row in read_dbf_table(base_path, doc_date_table, encoding):
                print({"IDDOC": row.get("IDDOC"), "DATE": row.get("DATE")})
                shown += 1
                if shown >= 3:
                    break
        except Exception as exc:
            print("ОШИБКА при чтении {0}: {1}".format(doc_date_table, exc))

    for table_key, item_field_key in (("avg_cost_table", "avg_cost_item_field"), ("sale_price_table", "sale_price_item_field")):
        table = base_cfg.get(table_key)
        item_field = base_cfg.get(item_field_key)
        if not table or not item_field:
            continue

        print("\n=== {0} ({1}): строки для базового артикула '{2}' ===".format(table_key, table, article))

        item_field_for_lookup = base_cfg["items_article_field"]
        fallback_field = base_cfg.get("items_article_fallback_field")
        id_field = base_cfg["items_id_field"]

        if is_sql:
            cols = [id_field, item_field_for_lookup]
            if fallback_field:
                cols.append(fallback_field)
            items_query = "SELECT {0} FROM {1}".format(", ".join(cols), base_cfg["items_table"])
            rows = run_query(server, database, user, password, items_query)
            item_ids = []
            for row in rows:
                if len(row) < 2:
                    continue
                a = row[1].strip()
                if not a and fallback_field and len(row) > 2:
                    a = row[2].strip()
                if a == article:
                    item_ids.append(row[0].strip())
            print("Найдено товаров с этим артикулом: {0}".format(len(item_ids)))

            for item_id in item_ids:
                query = "SELECT * FROM {0} WHERE LTRIM(RTRIM({1})) = '{2}'".format(table, item_field, item_id)
                rows2 = run_query(server, database, user, password, query)
                for row2 in rows2:
                    print("  строка ({0}): {1}".format(item_id, row2))
                    iddoc = row2[0].strip() if row2 else ""
                    if iddoc:
                        check_query = "SELECT DATE FROM {0} WHERE LTRIM(RTRIM(IDDOC)) = '{1}'".format(doc_date_table, iddoc)
                        try:
                            result = run_query(server, database, user, password, check_query)
                            print("    IDDOC='{0}' в {1}: {2}".format(iddoc, doc_date_table, result if result else "НЕ НАЙДЕН"))
                        except Exception as exc:
                            print("    Ошибка проверки IDDOC='{0}': {1}".format(iddoc, exc))
        else:
            base_path = Path(base_cfg["path"])
            encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))
            item_ids = []
            for row in read_dbf_table(base_path, base_cfg["items_table"], encoding):
                a = str(row.get(item_field_for_lookup, "")).strip()
                if not a and fallback_field:
                    a = str(row.get(fallback_field, "")).strip()
                if a == article:
                    item_ids.append(row[id_field])
            print("Найдено товаров с этим артикулом: {0}".format(len(item_ids)))

            doc_dates = {}
            try:
                for row in read_dbf_table(base_path, doc_date_table, encoding):
                    iddoc = row.get("IDDOC")
                    if iddoc is not None:
                        doc_dates[iddoc] = row.get("DATE")
            except Exception as exc:
                print("Не удалось прочитать {0}: {1}".format(doc_date_table, exc))

            table_file = table if table.upper().endswith(".DBF") else table + ".DBF"
            item_id_set = set(item_ids)
            for row2 in read_dbf_table(base_path, table_file, encoding):
                if row2.get(item_field) in item_id_set:
                    iddoc = row2.get("IDDOC")
                    date = doc_dates.get(iddoc)
                    print("  строка: {0}".format(dict(row2)))
                    print("    IDDOC='{0}' в {1}: {2}".format(iddoc, doc_date_table, date if date else "НЕ НАЙДЕН"))


def main():
    if len(sys.argv) != 3:
        sys.exit("Использование: python check_doc_join.py <индекс_базы 1-4> <артикул_без_суффикса>")

    index = int(sys.argv[1])
    article = sys.argv[2]

    log_filename = "check_doc_join_log.txt"
    commit_message = "Диагностика связи цены/себестоимости с 1SJOURN (база {0}, артикул {1})".format(index, article)
    run_with_log(log_filename, commit_message, lambda: run(index, article))


if __name__ == "__main__":
    main()
