"""
Экспорт артикул/остаток/цена из баз 1С 7.7 (DBF и/или SQL Server) в один CSV
и публикация в GitHub.

Настройки берутся из config.json (см. config.example.json - скопируй и заполни
своими путями/серверами, именами таблиц/полей, суффиксами и токеном GitHub).

Каждая база в config["bases"] имеет поле "type":
  - "dbf" - данные читаются из DBF-файлов (поле "path" - папка с базой);
  - "sql" - данные читаются из SQL Server через sqlcmd.exe (поля
    "sql_server"/"sql_database", логин/пароль - в config["sql_auth"]).

Остаток считается из периодического регистра 1С 7.7 (например RG1130.DBF) -
для каждого товара берётся СУММА значений за САМЫЙ ПОЗДНИЙ период (в 1С 7.7
такие регистры хранят уже накопленный остаток на конец периода, а не сырые
движения, поэтому суммировать все строки за всю историю не нужно - только
строки с максимальным PERIOD для этого товара).

avg_cost_table/sale_price_table - НЕОБЯЗАТЕЛЬНЫ. Если не заданы или при
чтении возникла ошибка - в CSV просто будут пустые значения для этой базы,
остальной экспорт (артикул+остаток) не блокируется. Это сделано специально,
чтобы можно было запустить экспорт остатков, не дожидаясь, пока найдётся
точная таблица себестоимости/цены.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Запуск:
    python main.py
"""

import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dbfread import DBF

from github_publish import push_files
from sqlcmd_client import run_query

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(
            "Не найден {0}.\n"
            "Скопируй config.example.json в config.json и заполни своими значениями.".format(CONFIG_PATH)
        )
    return json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())


# ---------------------------------------------------------------------------
# DBF
# ---------------------------------------------------------------------------

def read_dbf_table(base_path, table_name, encoding):
    table_path = base_path / table_name
    if not table_path.exists():
        # Регистр имени файла может отличаться на разных ОС/копиях баз.
        candidates = list(base_path.glob("{0}.*".format(table_name.split(".")[0])))
        if not candidates:
            raise FileNotFoundError("Таблица {0} не найдена в {1}".format(table_name, base_path))
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def read_dbf_value_map(base_path, table_name, item_field, value_field, encoding):
    table = read_dbf_table(base_path, table_name, encoding)
    result = {}
    for row in table:
        result[row[item_field]] = row[value_field]
    return result


def read_dbf_latest_period_map(base_path, table_name, item_field, period_field, value_field, encoding):
    """Для каждого товара берёт сумму value_field по строкам с максимальным
    period_field - так получается актуальный остаток из периодического
    регистра 1С 7.7 (RGxxxx.DBF), а не сумма движений за всю историю."""
    latest_period = {}
    for row in read_dbf_table(base_path, table_name, encoding):
        item = row[item_field]
        period = row[period_field]
        if item not in latest_period or period > latest_period[item]:
            latest_period[item] = period

    result = {}
    for row in read_dbf_table(base_path, table_name, encoding):
        item = row[item_field]
        if row[period_field] == latest_period.get(item):
            result[item] = result.get(item, 0) + (row[value_field] or 0)
    return result


def export_base_dbf(base_cfg, encoding):
    base_path = Path(base_cfg["path"])

    items = read_dbf_table(base_path, base_cfg["items_table"], encoding)

    id_field = base_cfg["items_id_field"]
    article_field = base_cfg["items_article_field"]
    name_field = base_cfg.get("items_name_field")

    item_by_id = {}
    for row in items:
        item_by_id[row[id_field]] = {
            "article": row.get(article_field, ""),
            "name": row.get(name_field, "") if name_field else "",
        }

    stock_by_id = read_dbf_latest_period_map(
        base_path,
        base_cfg["stock_table"],
        base_cfg["stock_item_field"],
        base_cfg.get("stock_period_field", "PERIOD"),
        base_cfg["stock_qty_field"],
        encoding,
    )

    sale_price_by_id = {}
    if base_cfg.get("sale_price_table"):
        try:
            sale_price_by_id = read_dbf_value_map(
                base_path,
                base_cfg["sale_price_table"],
                base_cfg["sale_price_item_field"],
                base_cfg["sale_price_value_field"],
                encoding,
            )
        except Exception:
            sale_price_by_id = {}

    avg_cost_by_id = {}
    if base_cfg.get("avg_cost_table"):
        try:
            avg_cost_by_id = read_dbf_value_map(
                base_path,
                base_cfg["avg_cost_table"],
                base_cfg["avg_cost_item_field"],
                base_cfg["avg_cost_value_field"],
                encoding,
            )
        except Exception:
            avg_cost_by_id = {}

    return item_by_id, stock_by_id, avg_cost_by_id, sale_price_by_id


# ---------------------------------------------------------------------------
# SQL Server (через sqlcmd.exe)
# ---------------------------------------------------------------------------

def read_sql_value_map(server, database, user, password, table, item_field, value_field):
    query = "SELECT {0}, {1} FROM {2}".format(item_field, value_field, table)
    rows = run_query(server, database, user, password, query)
    result = {}
    for row in rows:
        if len(row) < 2:
            continue
        result[row[0].strip()] = row[1].strip()
    return result


def read_sql_latest_period_map(server, database, user, password, table, item_field, period_field, value_field):
    """SQL-аналог read_dbf_latest_period_map - сумма value_field по строкам
    с максимальным period_field для каждого товара."""
    query = (
        "SELECT t1.{0}, SUM(t1.{1}) FROM {2} t1 "
        "WHERE t1.{3} = (SELECT MAX(t2.{3}) FROM {2} t2 WHERE t2.{0} = t1.{0}) "
        "GROUP BY t1.{0}"
    ).format(item_field, value_field, table, period_field)
    rows = run_query(server, database, user, password, query)
    result = {}
    for row in rows:
        if len(row) < 2:
            continue
        result[row[0].strip()] = row[1].strip()
    return result


def export_base_sql(base_cfg, sql_auth):
    server = base_cfg["sql_server"]
    database = base_cfg["sql_database"]
    user = sql_auth["user"]
    password = sql_auth["password"]

    id_field = base_cfg["items_id_field"]
    article_field = base_cfg["items_article_field"]
    name_field = base_cfg.get("items_name_field")

    select_cols = [id_field, article_field]
    if name_field:
        select_cols.append(name_field)
    query = "SELECT {0} FROM {1}".format(", ".join(select_cols), base_cfg["items_table"])
    rows = run_query(server, database, user, password, query)

    item_by_id = {}
    for row in rows:
        if len(row) < 2:
            continue
        item_id = row[0].strip()
        article = row[1].strip()
        name = row[2].strip() if name_field and len(row) > 2 else ""
        item_by_id[item_id] = {"article": article, "name": name}

    stock_by_id = read_sql_latest_period_map(
        server, database, user, password,
        base_cfg["stock_table"], base_cfg["stock_item_field"],
        base_cfg.get("stock_period_field", "PERIOD"), base_cfg["stock_qty_field"],
    )

    sale_price_by_id = {}
    if base_cfg.get("sale_price_table"):
        try:
            sale_price_by_id = read_sql_value_map(
                server, database, user, password,
                base_cfg["sale_price_table"], base_cfg["sale_price_item_field"], base_cfg["sale_price_value_field"],
            )
        except Exception:
            sale_price_by_id = {}

    avg_cost_by_id = {}
    if base_cfg.get("avg_cost_table"):
        try:
            avg_cost_by_id = read_sql_value_map(
                server, database, user, password,
                base_cfg["avg_cost_table"], base_cfg["avg_cost_item_field"], base_cfg["avg_cost_value_field"],
            )
        except Exception:
            avg_cost_by_id = {}

    return item_by_id, stock_by_id, avg_cost_by_id, sale_price_by_id


# ---------------------------------------------------------------------------
# Общая склейка результатов (не зависит от типа базы)
# ---------------------------------------------------------------------------

def export_base(base_cfg, default_encoding, sql_auth):
    base_type = base_cfg.get("type", "dbf")
    suffix = base_cfg.get("suffix", "")

    if base_type == "sql":
        item_by_id, stock_by_id, avg_cost_by_id, sale_price_by_id = export_base_sql(base_cfg, sql_auth)
    else:
        encoding = base_cfg.get("encoding", default_encoding)
        item_by_id, stock_by_id, avg_cost_by_id, sale_price_by_id = export_base_dbf(base_cfg, encoding)

    out_rows = []
    for item_id, item_info in item_by_id.items():
        raw_article = str(item_info.get("article", "")).strip()
        if not raw_article:
            continue
        out_rows.append(
            {
                "article": "{0}{1}".format(raw_article, suffix),
                "name": str(item_info.get("name", "")).strip(),
                "stock": stock_by_id.get(item_id, 0),
                "avg_cost": avg_cost_by_id.get(item_id, ""),
                "sale_price": sale_price_by_id.get(item_id, ""),
                "base": base_cfg["name"],
            }
        )
    return out_rows


def write_csv(rows, csv_path):
    try:
        csv_path.parent.mkdir(parents=True)
    except FileExistsError:
        pass
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["article", "name", "stock", "avg_cost", "sale_price", "base"]
        )
        writer.writeheader()
        writer.writerows(rows)


def write_log(log_lines, log_path):
    try:
        log_path.parent.mkdir(parents=True)
    except FileExistsError:
        pass
    open(str(log_path), "w", encoding="utf-8").write("\n".join(log_lines) + "\n")


def main():
    run_started_at = datetime.now()
    config = load_config()
    encoding = config.get("encoding", "cp866")
    sql_auth = config.get("sql_auth", {})

    all_rows = []
    log_lines = ["Запуск экспорта: {0:%Y-%m-%d %H:%M:%S}".format(run_started_at)]

    for base_cfg in config["bases"]:
        base_type = base_cfg.get("type", "dbf")
        location = base_cfg["path"] if base_type == "dbf" else "{0}/{1}".format(
            base_cfg.get("sql_server", "?"), base_cfg.get("sql_database", "?")
        )
        print("Читаю базу {0} [{1}] ({2})...".format(base_cfg["name"], base_type, location))
        base_started_at = time.perf_counter()
        try:
            rows = export_base(base_cfg, encoding, sql_auth)
        except Exception as exc:
            elapsed = time.perf_counter() - base_started_at
            print("  Ошибка при чтении базы {0}: {1}".format(base_cfg["name"], exc))
            log_lines.append("{0}: ОШИБКА за {1:.2f} сек - {2}".format(base_cfg["name"], elapsed, exc))
            continue
        elapsed = time.perf_counter() - base_started_at
        print("  Найдено товаров: {0} за {1:.2f} сек".format(len(rows), elapsed))
        log_lines.append("{0}: {1} товаров за {2:.2f} сек".format(base_cfg["name"], len(rows), elapsed))
        all_rows.extend(rows)

    total_elapsed = (datetime.now() - run_started_at).total_seconds()
    log_lines.append("Итого товаров: {0}".format(len(all_rows)))
    log_lines.append("Общее время выполнения: {0:.2f} сек".format(total_elapsed))

    github_cfg = config["github"]
    csv_path = Path(github_cfg["repo_path"]) / github_cfg["csv_path_in_repo"]
    write_csv(all_rows, csv_path)
    print("CSV записан: {0} ({1} строк)".format(csv_path, len(all_rows)))

    log_path = Path(github_cfg["repo_path"]) / github_cfg.get("log_path_in_repo", "export_log.txt")
    write_log(log_lines, log_path)
    print("Лог записан: {0}".format(log_path))

    push_files(
        github_cfg,
        [github_cfg["csv_path_in_repo"], github_cfg.get("log_path_in_repo", "export_log.txt")],
        "Обновление остатков и цен из 1С",
    )


if __name__ == "__main__":
    main()
