"""
Ищет, в каком ПОЛЕ карточки товара (items_table, например SC4889) реально
лежит артикул - проверяя ВСЕ поля каждой строки на точное совпадение с
заданным числом, а не предполагая, что это CODE.

Нужно, когда выясняется, что сопоставление по CODE не совпадает с реальными
артикулами из независимого источника (например, из локальной базы, куда
артикулы импортировались прямо из 1С).

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python find_article_field.py <индекс_базы 1-4> <число_артикула> [число2 ...]

Пример:
    python find_article_field.py 1 100
    python find_article_field.py 2 8807 1143
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


def search_dbf(base_cfg, config, targets):
    base_path = Path(base_cfg["path"])
    encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))
    table = read_dbf_table(base_path, base_cfg["items_table"], encoding)

    target_set = set(targets)
    target_padded = set(t.zfill(8) for t in targets)

    found_any = False
    checked = 0
    for row in table:
        checked += 1
        for field_name, value in row.items():
            value_str = str(value).strip()
            if value_str in target_set or value_str in target_padded:
                found_any = True
                print("СОВПАДЕНИЕ: поле='{0}' значение='{1}' | вся строка: {2}".format(
                    field_name, value_str, dict(row)
                ))
    print("Проверено строк: {0}".format(checked))
    if not found_any:
        print("Ни одно из значений {0} не найдено ни в одном поле ни одной строки.".format(targets))


def search_sql(base_cfg, config, targets):
    server = base_cfg["sql_server"]
    database = base_cfg["sql_database"]
    sql_auth = config.get("sql_auth", {})
    user = sql_auth["user"]
    password = sql_auth["password"]
    table = base_cfg["items_table"]

    columns_query = (
        "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{0}'"
    ).format(table)
    columns_output = run_query_raw(server, database, user, password, columns_query)
    skip_types = ("text", "ntext", "image", "xml")
    column_names = []
    for line in columns_output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in ("COLUMN_NAME", "-----------") and not parts[0].startswith("-"):
            if parts[1].lower() not in skip_types:
                column_names.append(parts[0])

    print("Колонки items_table (без text/ntext/image/xml): {0}".format(", ".join(column_names)))

    text_columns = [c for c in column_names if c.upper() not in ("ROW_ID",)]
    for target in targets:
        target_padded = target.zfill(8)
        conditions = []
        for col in text_columns:
            conditions.append("LTRIM(RTRIM(CAST({0} AS NVARCHAR(4000)))) IN ('{1}', '{2}')".format(
                col, target, target_padded
            ))
        query = "SELECT * FROM {0} WHERE {1}".format(table, " OR ".join(conditions))
        print("\n--- ищем '{0}' (и '{1}') во всех полях ---".format(target, target_padded))
        print(run_query_raw(server, database, user, password, query))


def main():
    if len(sys.argv) < 3:
        sys.exit("Использование: python find_article_field.py <индекс_базы 1-4> <число1> [число2 ...]")

    index = int(sys.argv[1])
    targets = sys.argv[2:]

    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    print("База: {0} ({1})".format(base_cfg["name"], base_cfg.get("type", "dbf")))

    if base_cfg.get("type", "dbf") == "sql":
        search_sql(base_cfg, config, targets)
    else:
        search_dbf(base_cfg, config, targets)


if __name__ == "__main__":
    main()
