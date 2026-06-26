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
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dbfread import DBF

from github_publish import push_files
from sqlcmd_client import run_query

CONFIG_PATH = Path(__file__).parent / "config.json"

# Размер товара зашит как текст внутри названия. Два варианта (по схеме
# МойСклад - см. ТЗ_аномалия_остатков.md, раздел 4):
#
#  1) Характеристика "Размер" (в DESCR это "р.NN") - значение копируется
#     В ТОЧНОСТИ как есть, дефисы/слэши не трогаются: "р.33-36" -> "33-36".
#  2) Любая другая характеристика - в DESCR это последний текст в скобках
#     в конце названия (например "(182 см)", "(04 R)") - к содержимому
#     скобок (без них самих) применяется посимвольная замена:
#       пробел -> "_", дефис "-" -> "_", "(" -> "_", ")" -> удаляется,
#       "№" -> "_", "," -> "_", "/" остаётся как есть, остальное не
#     трогаем; повторяющиеся пробелы НЕ схлопываются. Результат обрезается
#     до 20 символов (МойСклад режет код варианта именно так).
#
# Это эмпирическая реконструкция алгоритма МойСклад, не гарантирует 100%
# совпадение во всех случаях (сам МойСклад отдельно отметил расхождения,
# которые не смог объяснить - например дефис ведёт себя по-разному в двух
# ветках) - но покрывает большинство наблюдаемых вариантов.
# "р." - основной вариант, но в реальных DESCR встречаются опечатки и
# вариации ввода: латинская "p." вместо кириллической "р.", без точки
# ("р42"), с пробелом вместо точки ("р 42"), запятая вместо точки
# ("р,40", также как разделитель внутри размера "27,7"), задвоенная точка
# ("р..42/43"). Разделитель перед цифрами допускаем 0-2 раза (. или ,),
# с необязательным пробелом - дальше сами цифры с разделителями как есть.
SIZE_PATTERN = re.compile(
    r"\b[рp][.,]{0,2}\s*([0-9]+(?:[./,\-][0-9]+)*)",
    re.UNICODE | re.IGNORECASE,
)
# Допускаем один уровень вложенных скобок (бывает "((04 R))" в DESCR) -
# внутренние скобки остаются ЛИТЕРАЛЬНО в захваченном тексте и потом сами
# слагифицируются ("(" -> "_", ")" -> удаляется), это и даёт "_04_R".
TRAILING_PAREN_PATTERN = re.compile(r"\(((?:[^()]|\([^()]*\))*)\)\s*$", re.UNICODE)

_SLUG_REPLACEMENTS = {
    " ": "_",
    "-": "_",
    "(": "_",
    ")": "",
    "№": "_",
    ",": "_",
}


def _slugify_characteristic(text):
    return "".join(_SLUG_REPLACEMENTS.get(ch, ch) for ch in text)[:20]


def extract_size(name):
    name = name or ""
    match = SIZE_PATTERN.search(name)
    if match:
        return match.group(1)
    match = TRAILING_PAREN_PATTERN.search(name)
    if match:
        slug = _slugify_characteristic(match.group(1))
        return slug if slug else None
    return None


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


def read_dbf_latest_period_map(
    base_path, table_name, item_field, period_field, value_field, encoding,
    extra_filter_field=None, extra_filter_value=None,
):
    """Для каждого товара берёт сумму value_field по строкам с максимальным
    period_field - так получается остаток за самый свежий период из
    периодического регистра 1С 7.7 (RGxxxx.DBF).

    В этом регистре на каждый период есть ДВЕ строки с одинаковым
    количеством, отличающиеся только дополнительным измерением (например
    параллельный учёт БУ/НУ) - extra_filter_field/extra_filter_value
    позволяет оставить только одну из них и не задвоить остаток.
    Дополнительно убираем полные дубликаты строк на случай, если они
    всё же встречаются физически дважды."""
    latest_period = {}
    for row in read_dbf_table(base_path, table_name, encoding):
        item = row[item_field]
        period = row[period_field]
        if item not in latest_period or period > latest_period[item]:
            latest_period[item] = period

    result = {}
    seen_rows = set()
    for row in read_dbf_table(base_path, table_name, encoding):
        item = row[item_field]
        if row[period_field] != latest_period.get(item):
            continue
        if extra_filter_field and str(row.get(extra_filter_field, "")).strip() != str(extra_filter_value).strip():
            continue
        row_key = tuple(sorted((k, str(v)) for k, v in row.items()))
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        result[item] = result.get(item, 0) + (row[value_field] or 0)
    return result


def export_base_dbf(base_cfg, encoding):
    base_path = Path(base_cfg["path"])

    items = read_dbf_table(base_path, base_cfg["items_table"], encoding)

    id_field = base_cfg["items_id_field"]
    article_field = base_cfg["items_article_field"]
    fallback_field = base_cfg.get("items_article_fallback_field")
    name_field = base_cfg.get("items_name_field")

    item_by_id = {}
    for row in items:
        article_value = str(row.get(article_field, "")).strip()
        fallback_value = str(row.get(fallback_field, "")).strip() if fallback_field else ""
        if not article_value:
            article_value = fallback_value
        item_by_id[row[id_field]] = {
            "article": article_value,
            "name": row.get(name_field, "") if name_field else "",
            "disambiguator": fallback_value,
        }

    stock_by_id = read_dbf_latest_period_map(
        base_path,
        base_cfg["stock_table"],
        base_cfg["stock_item_field"],
        base_cfg.get("stock_period_field", "PERIOD"),
        base_cfg["stock_qty_field"],
        encoding,
        base_cfg.get("stock_extra_filter_field"),
        base_cfg.get("stock_extra_filter_value"),
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


def read_sql_latest_period_map(
    server, database, user, password, table, item_field, period_field, value_field,
    extra_filter_field=None, extra_filter_value=None,
):
    """SQL-аналог read_dbf_latest_period_map - сумма value_field по строкам
    с максимальным period_field для каждого товара. На каждый период в этом
    регистре есть ДВЕ строки с одинаковым количеством, отличающиеся только
    дополнительным измерением (например параллельный учёт БУ/НУ) -
    extra_filter_field/extra_filter_value оставляет только одну из них.
    SELECT DISTINCT дополнительно убирает полные дубликаты строк, если они
    всё же встречаются физически дважды."""
    base_query = "SELECT DISTINCT * FROM {0}".format(table)
    if extra_filter_field:
        base_query += " WHERE LTRIM(RTRIM({0})) = '{1}'".format(extra_filter_field, extra_filter_value)

    query = (
        "SELECT t1.{0}, SUM(t1.{1}) FROM ({2}) t1 "
        "WHERE t1.{3} = (SELECT MAX(t2.{3}) FROM {4} t2 WHERE t2.{0} = t1.{0}) "
        "GROUP BY t1.{0}"
    ).format(item_field, value_field, base_query, period_field, table)
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
    fallback_field = base_cfg.get("items_article_fallback_field")
    name_field = base_cfg.get("items_name_field")

    select_cols = [id_field, article_field]
    if fallback_field:
        select_cols.append(fallback_field)
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
        next_idx = 2
        fallback_value = ""
        if fallback_field:
            if len(row) > next_idx:
                fallback_value = row[next_idx].strip()
            if not article:
                article = fallback_value
            next_idx += 1
        name = row[next_idx].strip() if name_field and len(row) > next_idx else ""
        item_by_id[item_id] = {"article": article, "name": name, "disambiguator": fallback_value}

    stock_by_id = read_sql_latest_period_map(
        server, database, user, password,
        base_cfg["stock_table"], base_cfg["stock_item_field"],
        base_cfg.get("stock_period_field", "PERIOD"), base_cfg["stock_qty_field"],
        base_cfg.get("stock_extra_filter_field"),
        base_cfg.get("stock_extra_filter_value"),
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

def export_base(base_cfg, default_encoding, sql_auth, exclude_zero_stock=False):
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
        stock_value = stock_by_id.get(item_id, 0)
        try:
            stock_value = float(stock_value)
        except (TypeError, ValueError):
            stock_value = 0
        if stock_value < 0:
            # Отрицательный остаток - явная ошибка учёта, приводим к 0.
            stock_value = 0
        if exclude_zero_stock and stock_value <= 0:
            # По умолчанию (exclude_zero_stock=False) строка с нулевым
            # остатком всё равно попадает в CSV как stock=0 - так
            # потребитель файла может отличить "товар существует, но
            # распродан" от "артикул вообще не существует в системе"
            # (полное отсутствие строки). Включи exclude_zero_stock=true
            # в config.json, только если эта разница тебе не важна и
            # нужен компактный файл без нулевых остатков.
            continue
        size = extract_size(item_info.get("name", ""))
        if size:
            article_out = "{0}{1}-{2}".format(raw_article, suffix, size)
        else:
            article_out = "{0}{1}".format(raw_article, suffix)
        out_rows.append(
            {
                "article": article_out,
                "name": str(item_info.get("name", "")).strip(),
                "stock": stock_value,
                "avg_cost": avg_cost_by_id.get(item_id, ""),
                "sale_price": sale_price_by_id.get(item_id, ""),
                "base": base_cfg["name"],
                "_item_id": item_id,
                "_disambiguator": str(item_info.get("disambiguator", "")).strip(),
            }
        )

    # Если в названии нет распознаваемого размера (или он одинаковый у
    # нескольких разных товаров, например цвета одной модели), несколько
    # разных внутренних товаров 1С могут получить ОДИНАКОВЫЙ итоговый
    # артикул - они бы перезатирали друг друга у любого потребителя,
    # читающего CSV в словарь по артикулу. Различаем такие дубликаты
    # внутренним кодом товара (CODE/ID).
    article_counts = {}
    for row in out_rows:
        article_counts[row["article"]] = article_counts.get(row["article"], 0) + 1
    for row in out_rows:
        if article_counts[row["article"]] > 1:
            disambiguator = row["_disambiguator"] or str(row["_item_id"]).strip()
            row["article"] = "{0}-{1}".format(row["article"], disambiguator)
        del row["_item_id"]
        del row["_disambiguator"]
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
    exclude_zero_stock = config.get("exclude_zero_stock", False)

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
            rows = export_base(base_cfg, encoding, sql_auth, exclude_zero_stock)
        except Exception as exc:
            elapsed = time.perf_counter() - base_started_at
            print("  Ошибка при чтении базы {0}: {1}".format(base_cfg["name"], exc))
            log_lines.append("{0}: ОШИБКА за {1:.2f} сек - {2}".format(base_cfg["name"], elapsed, exc))
            continue
        elapsed = time.perf_counter() - base_started_at
        zero_stock_count = sum(1 for r in rows if float(r["stock"]) == 0)
        print("  Найдено товаров: {0} за {1:.2f} сек (из них с нулевым остатком: {2})".format(
            len(rows), elapsed, zero_stock_count
        ))
        log_lines.append("{0}: {1} товаров за {2:.2f} сек (с нулевым остатком: {3})".format(
            base_cfg["name"], len(rows), elapsed, zero_stock_count
        ))
        all_rows.extend(rows)

    total_elapsed = (datetime.now() - run_started_at).total_seconds()
    total_zero = sum(1 for r in all_rows if float(r["stock"]) == 0)
    log_lines.append("Итого товаров: {0} (из них с нулевым остатком: {1})".format(len(all_rows), total_zero))
    log_lines.append(
        "Режим: {0}".format(
            "нулевые остатки ИСКЛЮЧЕНЫ из CSV (exclude_zero_stock=true)" if exclude_zero_stock
            else "нулевые остатки включены в CSV строкой stock=0"
        )
    )
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
