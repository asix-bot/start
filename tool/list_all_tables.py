"""
Выгружает ПОЛНЫЙ список таблиц базы (без фильтра по префиксу) - на случай,
если регистр цен называется не так, как мы предполагали (RG/RA/DT/DH/SC/_1S),
и find_price_cost_field.py его просто не сканирует вообще.

Для SQL - через INFORMATION_SCHEMA.TABLES. Для DBF - через перечисление всех
*.DBF файлов в папке базы (с количеством записей - помогает увидеть, что мы
могли упустить, особенно таблицы с подходящим размером под "товар x типы цен").

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python list_all_tables.py <индекс_базы 1-4>
"""

import json
import sys
from pathlib import Path

from dbfread import DBF
from diagnostic_log import run_with_log
from sqlcmd_client import run_query_raw

CONFIG_PATH = Path(__file__).parent / "config.json"


def run(index):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    print("База: {0} ({1})".format(base_cfg["name"], base_cfg.get("type", "dbf")))

    if base_cfg.get("type", "dbf") == "sql":
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        sql_auth = config.get("sql_auth", {})
        user = sql_auth["user"]
        password = sql_auth["password"]

        print("\n--- Полный список таблиц (без фильтра) ---")
        print(run_query_raw(
            server, database, user, password,
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME",
        ))
    else:
        base_path = Path(base_cfg["path"])
        dbf_files = sorted(base_path.glob("*.DBF")) + sorted(base_path.glob("*.dbf"))
        print("\n--- Полный список .DBF файлов ({0} шт.) ---".format(len(dbf_files)))
        for dbf_path in dbf_files:
            try:
                encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))
                table = DBF(str(dbf_path), encoding=encoding, ignore_missing_memofile=True)
                print("{0}: {1} записей".format(dbf_path.name, len(table)))
            except Exception as exc:
                print("{0}: ошибка открытия - {1}".format(dbf_path.name, exc))


def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python list_all_tables.py <индекс_базы 1-4>")

    index = int(sys.argv[1])

    log_filename = "list_all_tables_log.txt"
    commit_message = "Полный список таблиц базы {0} (без фильтра)".format(index)
    run_with_log(log_filename, commit_message, lambda: run(index))


if __name__ == "__main__":
    main()
