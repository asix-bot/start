"""
Ищет, в каком поле/регистре 1С 7.7 реально лежит цена продажи и/или
себестоимость - сравнивая ВСЕ числовые поля карточки товара (items_table)
и ВСЕХ регистров RG* этой базы с заданным известным значением (взятым из
независимой выгрузки, например inventory.db).

Похоже на find_article_field.py, но идёт на шаг дальше: ищет не только в
items_table, а во всех RG-регистрах базы (где может быть, например, регистр
партий/последней поставки - там и хранится себестоимость по последней
поставке, а не в карточке товара).

Чтобы не путать совпадения разных товаров, поиск по регистрам ведётся
ТОЛЬКО среди строк, где встречается ID нужного товара (найденного по
артикулу) - то есть сначала находим ID товара в items_table, потом ищем
строки регистров, где этот ID встречается в любом поле, и смотрим, есть ли
в той же строке число, близкое к искомой цене/себестоимости.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python find_price_cost_field.py <артикул_с_суффиксом> <цена> [себестоимость]

Пример:
    python find_price_cost_field.py 100ш 2220 1350
    python find_price_cost_field.py 7132з 6190 4739.17
"""

import json
import sys
from pathlib import Path

from dbfread import DBF
from diagnostic_log import run_with_log
from sqlcmd_client import run_query, run_query_raw

CONFIG_PATH = Path(__file__).parent / "config.json"
TOLERANCE = 0.05


def split_suffix(article, suffixes):
    for suffix in sorted(suffixes, key=len, reverse=True):
        if suffix and article.endswith(suffix):
            return article[: -len(suffix)], suffix
    return article, None


def close_enough(value_str, target):
    if target is None:
        return False
    try:
        value = float(str(value_str).strip().replace(",", "."))
    except (TypeError, ValueError):
        return False
    return abs(value - target) <= TOLERANCE


def read_dbf_table(base_path, table_name, encoding):
    table_path = base_path / table_name
    if not table_path.exists():
        candidates = list(base_path.glob("{0}.*".format(table_name.split(".")[0])))
        if not candidates:
            raise FileNotFoundError("Таблица {0} не найдена в {1}".format(table_name, base_path))
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def find_item_id_dbf(base_path, items_table, encoding, article_field, fallback_field, id_field, base_article):
    table = read_dbf_table(base_path, items_table, encoding)
    for row in table:
        value = str(row.get(article_field, "")).strip()
        if not value and fallback_field:
            value = str(row.get(fallback_field, "")).strip()
        if value == base_article:
            return row[id_field], dict(row)
    return None, None


def list_sql_columns(server, database, user, password, table_name):
    output = run_query_raw(
        server, database, user, password,
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{0}'".format(table_name),
    )
    names = []
    for line in output.splitlines():
        line = line.strip()
        if line and line not in ("COLUMN_NAME",) and not line.startswith("-"):
            names.append(line)
    return names


def find_item_id_sql(server, database, user, password, items_table, article_field, fallback_field, id_field, base_article):
    cols = [id_field, article_field]
    if fallback_field:
        cols.append(fallback_field)
    query = "SELECT {0} FROM {1}".format(", ".join(cols), items_table)
    rows = run_query(server, database, user, password, query)
    for row in rows:
        if len(row) < 2:
            continue
        article = row[1].strip()
        if not article and fallback_field and len(row) > 2:
            article = row[2].strip()
        if article == base_article:
            return row[0].strip()
    return None


def find_item_full_row_sql(server, database, user, password, items_table, id_field, item_id):
    columns = list_sql_columns(server, database, user, password, items_table)
    query = "SELECT * FROM {0} WHERE LTRIM(RTRIM(CAST({1} AS NVARCHAR(50)))) = '{2}'".format(
        items_table, id_field, item_id
    )
    rows = run_query(server, database, user, password, query)
    if not rows:
        return None, []
    return rows[0], columns


def list_dbf_rg_tables(base_path):
    return sorted(set(p.stem.upper() for p in base_path.glob("RG*.DBF") if p.stem.upper().startswith("RG")))


def list_sql_rg_tables(server, database, user, password):
    output = run_query_raw(
        server, database, user, password,
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'RG%'",
    )
    names = []
    for line in output.splitlines():
        line = line.strip()
        if line and line not in ("TABLE_NAME", "") and not line.startswith("-"):
            names.append(line)
    return names


def scan_dbf_table_for_item(base_path, table_name, encoding, item_id, price, cost):
    table = read_dbf_table(base_path, table_name, encoding)
    matches = []
    for row in table:
        row_values = [str(v).strip() for v in row.values()]
        if item_id not in row_values:
            continue
        for field_name, value in row.items():
            if close_enough(value, price) or close_enough(value, cost):
                matches.append((field_name, value, dict(row)))
    return matches


def scan_sql_table_for_item(server, database, user, password, table_name, item_id, price, cost):
    query = "SELECT * FROM {0}".format(table_name)
    rows = run_query(server, database, user, password, query)
    matches = []
    for row in rows:
        if item_id not in [str(v).strip() for v in row]:
            continue
        for value in row:
            if close_enough(value, price) or close_enough(value, cost):
                matches.append((table_name, row))
    return matches


def run(article, price, cost):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    bases = config["bases"]
    suffixes = [b.get("suffix", "") for b in bases]
    default_encoding = config.get("encoding", "cp866")
    sql_auth = config.get("sql_auth", {})

    base_article, suffix = split_suffix(article, suffixes)
    if suffix is None:
        sys.exit("Не удалось определить базу по суффиксу артикула '{0}'".format(article))

    base_cfg = None
    for b in bases:
        if b.get("suffix", "") == suffix:
            base_cfg = b
            break
    print("База: {0}, искомый базовый артикул: '{1}', цена={2}, себестоимость={3}".format(
        base_cfg["name"], base_article, price, cost
    ))

    id_field = base_cfg["items_id_field"]
    article_field = base_cfg["items_article_field"]
    fallback_field = base_cfg.get("items_article_fallback_field")

    if base_cfg.get("type", "dbf") == "sql":
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        user = sql_auth["user"]
        password = sql_auth["password"]
        item_id = find_item_id_sql(server, database, user, password, base_cfg["items_table"], article_field, fallback_field, id_field, base_article)
        if not item_id:
            sys.exit("Товар с артикулом '{0}' не найден в items_table".format(base_article))
        print("ID товара: '{0}'".format(item_id))

        catalog_row, catalog_columns = find_item_full_row_sql(server, database, user, password, base_cfg["items_table"], id_field, item_id)
        if catalog_row:
            print("Строка карточки товара ({0}): {1}".format(base_cfg["items_table"], catalog_row))
            for idx, value in enumerate(catalog_row):
                if close_enough(value, price) or close_enough(value, cost):
                    col_name = catalog_columns[idx] if idx < len(catalog_columns) else "?"
                    print("  СОВПАДЕНИЕ В КАРТОЧКЕ: колонка #{0} ('{1}') = '{2}'".format(idx, col_name, value))

        rg_tables = list_sql_rg_tables(server, database, user, password)
        print("Найдено RG-таблиц: {0}".format(len(rg_tables)))
        any_match = False
        for table_name in rg_tables:
            try:
                matches = scan_sql_table_for_item(server, database, user, password, table_name, item_id, price, cost)
            except Exception as exc:
                print("  {0}: ошибка чтения - {1}".format(table_name, exc))
                continue
            if matches:
                any_match = True
                print("\n--- {0}: найдены строки с товаром И числом близким к цене/себестоимости ---".format(table_name))
                for _, row in matches:
                    print("  {0}".format(row))
        if not any_match:
            print("\nНи в одной RG-таблице не найдено строки с этим товаром и подходящим числом.")
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", default_encoding)
        item_id, item_row = find_item_id_dbf(base_path, base_cfg["items_table"], encoding, article_field, fallback_field, id_field, base_article)
        if not item_id:
            sys.exit("Товар с артикулом '{0}' не найден в items_table".format(base_article))
        print("ID товара: '{0}'".format(item_id))
        print("Строка карточки товара: {0}".format(item_row))

        rg_tables = list_dbf_rg_tables(base_path)
        print("Найдено RG-таблиц: {0}".format(len(rg_tables)))
        any_match = False
        for table_name in rg_tables:
            try:
                matches = scan_dbf_table_for_item(base_path, table_name + ".DBF", encoding, item_id, price, cost)
            except Exception as exc:
                print("  {0}: ошибка чтения - {1}".format(table_name, exc))
                continue
            if matches:
                any_match = True
                print("\n--- {0}: найдены поля с числом близким к цене/себестоимости ---".format(table_name))
                seen_rows = set()
                for field_name, value, row in matches:
                    row_key = tuple(sorted((k, str(v)) for k, v in row.items()))
                    marker = "  поле '{0}'='{1}' | строка: {2}".format(field_name, value, row)
                    if row_key not in seen_rows:
                        seen_rows.add(row_key)
                        print(marker)
        if not any_match:
            print("\nНи в одной RG-таблице не найдено строки с этим товаром и подходящим числом.")


def main():
    if len(sys.argv) < 3:
        sys.exit("Использование: python find_price_cost_field.py <артикул> <цена> [себестоимость]")

    article = sys.argv[1]
    price = float(sys.argv[2])
    cost = float(sys.argv[3]) if len(sys.argv) > 3 else None

    log_filename = "find_price_cost_field_log.txt"
    commit_message = "Поиск поля цены/себестоимости для артикула {0}".format(article)
    run_with_log(log_filename, commit_message, lambda: run(article, price, cost))


if __name__ == "__main__":
    main()
