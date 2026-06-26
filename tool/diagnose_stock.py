"""
Диагностика: выводит ВСЕ строки регистра остатка (stock_table) для ОДНОГО
товара (по артикулу, без суффикса) - без какой-либо агрегации/дедупликации.
Нужно, чтобы вручную увидеть, действительно ли строки дублируются точь-в-точь,
или это разные строки с одинаковым количеством (тогда дедуп по строке не
поможет, и проблема в другом измерении регистра).

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python diagnose_stock.py <индекс_базы 1-4> <артикул_без_суффикса>

Пример:
    python diagnose_stock.py 3 38520
"""

import json
import sys
from pathlib import Path

from dbfread import DBF
from sqlcmd_client import run_query_raw

CONFIG_PATH = Path(__file__).parent / "config.json"


def read_dbf_table(base_path, table_name, encoding):
    table_path = base_path / table_name
    if not table_path.exists():
        candidates = list(base_path.glob("{0}.*".format(table_name.split(".")[0])))
        if not candidates:
            raise FileNotFoundError("Таблица {0} не найдена в {1}".format(table_name, base_path))
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def main():
    if len(sys.argv) != 3:
        sys.exit("Использование: python diagnose_stock.py <индекс_базы 1-4> <артикул_без_суффикса>")

    index = int(sys.argv[1])
    article = sys.argv[2]

    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    print("База: {0} ({1})".format(base_cfg["name"], base_cfg.get("type", "dbf")))

    if base_cfg.get("type", "dbf") == "sql":
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        sql_auth = config.get("sql_auth", {})
        user = sql_auth["user"]
        password = sql_auth["password"]

        find_id_query = "SELECT {0} FROM {1} WHERE {2}='{3}'".format(
            base_cfg["items_id_field"], base_cfg["items_table"], base_cfg["items_article_field"], article
        )
        print("--- ищем ID товара ---")
        id_output = run_query_raw(server, database, user, password, find_id_query)
        print(id_output)

        item_id_lines = [
            line.strip() for line in id_output.splitlines()
            if line.strip() and line.strip().lower() != base_cfg["items_id_field"].lower()
            and not line.strip().startswith("-") and "rows affected" not in line.lower()
        ]
        if not item_id_lines:
            sys.exit("Товар с артикулом {0} не найден.".format(article))
        item_id = item_id_lines[0]
        print("Найден ID: '{0}'".format(item_id))

        print("\n--- все строки stock_table для этого ID, без агрегации ---")
        all_rows_query = "SELECT * FROM {0} WHERE {1}='{2}' ORDER BY {3}".format(
            base_cfg["stock_table"], base_cfg["stock_item_field"], item_id,
            base_cfg.get("stock_period_field", "PERIOD"),
        )
        print(run_query_raw(server, database, user, password, all_rows_query))
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))

        items = read_dbf_table(base_path, base_cfg["items_table"], encoding)
        item_id = None
        for row in items:
            if str(row.get(base_cfg["items_article_field"], "")).strip() == article:
                item_id = row[base_cfg["items_id_field"]]
                break
        if item_id is None:
            sys.exit("Товар с артикулом {0} не найден.".format(article))
        print("Найден ID: '{0}'".format(item_id))

        print("\n--- все строки stock_table для этого ID, без агрегации ---")
        stock = read_dbf_table(base_path, base_cfg["stock_table"], encoding)
        item_field = base_cfg["stock_item_field"]
        count = 0
        for row in stock:
            if row[item_field] == item_id:
                count += 1
                print(count, dict(row))
        print("\nВсего найдено строк:", count)


if __name__ == "__main__":
    main()
