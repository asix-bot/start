"""
Сырой дамп ВСЕХ строк указанной таблицы, где артикул товара встречается в
ЛЮБОМ поле - без проверки на совпадение цены/себестоимости. Нужно, чтобы
вручную посмотреть структуру таблицы-кандидата (например RG10737) для
конкретного товара, когда автоматический поиск по числу не сработал, но
сама таблица выглядит подходящей по размеру/смыслу.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python dump_table_for_item.py <индекс_базы 1-4> <таблица> <артикул_без_суффикса>

Пример:
    python dump_table_for_item.py 2 RG10737 4241
    python dump_table_for_item.py 2 RA10737 4241
"""

import json
import sys
from pathlib import Path

from dbfread import DBF
from diagnostic_log import run_with_log
from sqlcmd_client import run_query, run_query_raw

CONFIG_PATH = Path(__file__).parent / "config.json"


def read_dbf_table(base_path, table_name, encoding):
    table_path = base_path / table_name
    if not table_path.exists():
        candidates = list(base_path.glob("{0}.*".format(table_name.split(".")[0])))
        if not candidates:
            raise FileNotFoundError("Таблица {0} не найдена в {1}".format(table_name, base_path))
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def find_item_ids(base_cfg, config, article):
    """Возвращает список ID товаров (все размерные варианты) с этим артикулом."""
    item_field = base_cfg["items_article_field"]
    fallback_field = base_cfg.get("items_article_fallback_field")
    id_field = base_cfg["items_id_field"]

    if base_cfg.get("type", "dbf") == "sql":
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        sql_auth = config.get("sql_auth", {})
        user = sql_auth["user"]
        password = sql_auth["password"]
        cols = [id_field, item_field]
        if fallback_field:
            cols.append(fallback_field)
        rows = run_query(server, database, user, password, "SELECT {0} FROM {1}".format(", ".join(cols), base_cfg["items_table"]))
        ids = []
        for row in rows:
            if len(row) < 2:
                continue
            a = row[1].strip()
            if not a and fallback_field and len(row) > 2:
                a = row[2].strip()
            if a == article:
                ids.append(row[0].strip())
        return ids
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))
        ids = []
        for row in read_dbf_table(base_path, base_cfg["items_table"], encoding):
            a = str(row.get(item_field, "")).strip()
            if not a and fallback_field:
                a = str(row.get(fallback_field, "")).strip()
            if a == article:
                ids.append(row[id_field])
        return ids


def run(index, table_name, article):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    print("База: {0} ({1}), таблица: {2}, артикул: {3}".format(base_cfg["name"], base_cfg.get("type", "dbf"), table_name, article))

    item_ids = find_item_ids(base_cfg, config, article)
    print("Найдено товаров с этим артикулом: {0} -> {1}".format(len(item_ids), item_ids))
    if not item_ids:
        return

    if base_cfg.get("type", "dbf") == "sql":
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        sql_auth = config.get("sql_auth", {})
        user = sql_auth["user"]
        password = sql_auth["password"]

        print("\n--- Колонки {0} ---".format(table_name))
        print(run_query_raw(server, database, user, password, "SELECT TOP 1 * FROM {0}".format(table_name)))

        for item_id in item_ids:
            print("\n--- Строки {0}, где встречается ID='{1}' (в любом поле) ---".format(table_name, item_id))
            cols_output = run_query_raw(
                server, database, user, password,
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{0}'".format(table_name),
            )
            columns = []
            for line in cols_output.splitlines():
                line = line.strip()
                if line and line not in ("COLUMN_NAME",) and not line.startswith("-"):
                    columns.append(line)
            conditions = " OR ".join(
                "LTRIM(RTRIM(CAST({0} AS NVARCHAR(50)))) = '{1}'".format(c, item_id) for c in columns
            )
            query = "SELECT * FROM {0} WHERE {1}".format(table_name, conditions)
            print(run_query_raw(server, database, user, password, query))
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))
        table_file = table_name if table_name.upper().endswith(".DBF") else table_name + ".DBF"
        item_id_set = set(item_ids)
        count = 0
        for row in read_dbf_table(base_path, table_file, encoding):
            if any(str(v).strip() in [str(i).strip() for i in item_id_set] for v in row.values()):
                count += 1
                print(dict(row))
        print("Найдено строк: {0}".format(count))


def main():
    if len(sys.argv) != 4:
        sys.exit("Использование: python dump_table_for_item.py <индекс_базы 1-4> <таблица> <артикул_без_суффикса>")

    index = int(sys.argv[1])
    table_name = sys.argv[2]
    article = sys.argv[3]

    log_filename = "dump_table_for_item_log.txt"
    commit_message = "Сырой дамп {0} для артикула {1} (база {2})".format(table_name, article, index)
    run_with_log(log_filename, commit_message, lambda: run(index, table_name, article))


if __name__ == "__main__":
    main()
