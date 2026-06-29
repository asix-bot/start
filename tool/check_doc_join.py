"""
Точечная диагностика: проверяет, есть ли в stock_table (RG1130) строки с
заданным IDDOC - чтобы понять, можно ли по этому полю связать DT3580/DT434
(цена/себестоимость) с датой документа из stock_table.

Нужно, потому что main.py пытается взять дату документа из stock_table по
IDDOC, но если там лежат ДРУГИЕ номера документов (например внутренний
"приходный ордер" склада, а не сам "Счёт"/накладная) - совпадений не будет
и цена/себестоимость останутся пустыми, даже если сама таблица DT3580/DT434
найдена правильно.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python check_doc_join.py <индекс_базы 1-4> <IDDOC1> [IDDOC2 ...]

Пример:
    python check_doc_join.py 3 2LWI 34AE
"""

import json
import sys
from pathlib import Path

from dbfread import DBF
from diagnostic_log import run_with_log
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


def run(index, iddocs):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    print("База: {0} ({1}), stock_table={2}, avg_cost_table={3}, sale_price_table={4}".format(
        base_cfg["name"], base_cfg.get("type", "dbf"),
        base_cfg.get("stock_table"), base_cfg.get("avg_cost_table"), base_cfg.get("sale_price_table"),
    ))

    if base_cfg.get("type", "dbf") == "sql":
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        sql_auth = config.get("sql_auth", {})
        user = sql_auth["user"]
        password = sql_auth["password"]

        for iddoc in iddocs:
            print("\n--- stock_table ({0}): строки с IDDOC='{1}' ---".format(base_cfg["stock_table"], iddoc))
            query = "SELECT * FROM {0} WHERE LTRIM(RTRIM(IDDOC)) = '{1}'".format(base_cfg["stock_table"], iddoc)
            print(run_query_raw(server, database, user, password, query))

            for table_key in ("avg_cost_table", "sale_price_table"):
                table = base_cfg.get(table_key)
                if not table:
                    continue
                print("--- {0} ({1}): строки с IDDOC='{2}' ---".format(table_key, table, iddoc))
                query2 = "SELECT * FROM {0} WHERE LTRIM(RTRIM(IDDOC)) = '{1}'".format(table, iddoc)
                print(run_query_raw(server, database, user, password, query2))
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))

        for iddoc in iddocs:
            print("\n--- stock_table ({0}): строки с IDDOC='{1}' ---".format(base_cfg["stock_table"], iddoc))
            count = 0
            for row in read_dbf_table(base_path, base_cfg["stock_table"], encoding):
                if str(row.get("IDDOC", "")).strip() == iddoc.strip():
                    count += 1
                    print(dict(row))
            print("Найдено строк: {0}".format(count))

            for table_key in ("avg_cost_table", "sale_price_table"):
                table = base_cfg.get(table_key)
                if not table:
                    continue
                print("--- {0} ({1}): строки с IDDOC='{2}' ---".format(table_key, table, iddoc))
                count2 = 0
                for row in read_dbf_table(base_path, table, encoding):
                    if str(row.get("IDDOC", "")).strip() == iddoc.strip():
                        count2 += 1
                        print(dict(row))
                print("Найдено строк: {0}".format(count2))


def main():
    if len(sys.argv) < 3:
        sys.exit("Использование: python check_doc_join.py <индекс_базы 1-4> <IDDOC1> [IDDOC2 ...]")

    index = int(sys.argv[1])
    iddocs = sys.argv[2:]

    log_filename = "check_doc_join_log.txt"
    commit_message = "Диагностика связи IDDOC между stock_table и DT-таблицами (база {0})".format(index)
    run_with_log(log_filename, commit_message, lambda: run(index, iddocs))


if __name__ == "__main__":
    main()
