"""
Выгружает количество строк (COUNT(*)) для каждой таблицы заданного префикса
в SQL-базе - чтобы найти кандидата на регистр цен по РАЗМЕРУ (товаров x
типов цен), когда точечный текстовый поиск значения не сработал.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python list_table_sizes.py <индекс_базы 1-4> <префикс>

Пример:
    python list_table_sizes.py 2 SC
"""

import json
import sys
from pathlib import Path

from diagnostic_log import run_with_log
from sqlcmd_client import run_query, run_query_raw

CONFIG_PATH = Path(__file__).parent / "config.json"


def run(index, prefix):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    if base_cfg.get("type", "dbf") != "sql":
        sys.exit("Эта диагностика только для SQL-баз.")

    server = base_cfg["sql_server"]
    database = base_cfg["sql_database"]
    sql_auth = config.get("sql_auth", {})
    user = sql_auth["user"]
    password = sql_auth["password"]

    print("База: {0}, префикс: {1}".format(base_cfg["name"], prefix))

    output = run_query_raw(
        server, database, user, password,
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '{0}%' ORDER BY TABLE_NAME".format(prefix),
    )
    tables = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line in ("TABLE_NAME",) or line.startswith("-") or "affected" in line:
            continue
        tables.append(line)

    print("Найдено таблиц: {0}".format(len(tables)))

    sizes = []
    for table_name in tables:
        try:
            rows = run_query(server, database, user, password, "SELECT COUNT(*) FROM {0}".format(table_name))
            count = int(rows[0][0].strip()) if rows and rows[0] else -1
        except Exception as exc:
            print("{0}: ошибка - {1}".format(table_name, exc))
            continue
        sizes.append((count, table_name))

    sizes.sort(reverse=True)
    print("\n--- Таблицы по убыванию размера ---")
    for count, table_name in sizes:
        print("{0}: {1} строк".format(table_name, count))


def main():
    if len(sys.argv) != 3:
        sys.exit("Использование: python list_table_sizes.py <индекс_базы 1-4> <префикс>")

    index = int(sys.argv[1])
    prefix = sys.argv[2]

    log_filename = "list_table_sizes_log.txt"
    commit_message = "Размеры таблиц с префиксом {0} (база {1})".format(prefix, index)
    run_with_log(log_filename, commit_message, lambda: run(index, prefix))


if __name__ == "__main__":
    main()
