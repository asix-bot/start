"""
Пакетная диагностика расхождений остатка (раздел 2 ТЗ stock_sync_anomaly_task.md):
для списка "артикул:ожидаемый_остаток" раскладывает остаток последнего
периода по ОТДЕЛЬНЫМ партиям (без агрегации) и проверяет гипотезу
"одна партия не учитывается на стороне партнёра" - то есть пробует
вычесть из суммы КАЖДУЮ отдельную партию по одной и смотрит, совпадёт
ли результат с ожидаемым значением (с допуском TOLERANCE).

Найдено по образцу: для 5481ки сумма всех партий SP2654=0 на последнем
периоде = 257, но партия на 200 шт (один документ) явно лишняя - без неё
получается 57, что совпадает с независимой базой партнёра.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python diagnose_stock_anomaly.py <артикул1>:<ожидаемый_остаток1> [<артикул2>:<ожидаемый_остаток2> ...]

Пример:
    python diagnose_stock_anomaly.py 5481ки:57 8814ки:62 6616ки:59
"""

import json
import sys
from pathlib import Path

from dbfread import DBF
from diagnostic_log import run_with_log
from sqlcmd_client import run_query

CONFIG_PATH = Path(__file__).parent / "config.json"
TOLERANCE = 0.05


def split_suffix(article, suffixes):
    for suffix in sorted(suffixes, key=len, reverse=True):
        if suffix and article.endswith(suffix):
            return article[: -len(suffix)], suffix
    return article, None


def read_dbf_table(base_path, table_name, encoding):
    table_path = base_path / table_name
    if not table_path.exists():
        candidates = list(base_path.glob("{0}.*".format(table_name.split(".")[0])))
        if not candidates:
            raise FileNotFoundError("Таблица {0} не найдена в {1}".format(table_name, base_path))
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def close_enough(value, target):
    return abs(value - target) <= TOLERANCE


def analyze_batches(batch_rows, expected, qty_key):
    """batch_rows - список dict со всеми полями строки + ключ qty_key с
    количеством. Печатает разбивку и проверяет гипотезу "минус одна партия"."""
    total = sum(r[qty_key] for r in batch_rows)
    print("Партий на последнем периоде (SP2654=0): {0}".format(len(batch_rows)))
    for r in batch_rows:
        print("  {0}".format(r))
    print("Сумма всех партий: {0}".format(total))
    print("Ожидаемый остаток (из независимой базы): {0}".format(expected))

    if close_enough(total, expected):
        print("СОВПАДАЕТ без изменений - расхождение объясняется не партиями.")
        return

    diff = total - expected
    print("Разница: {0}".format(diff))

    found = False
    for r in batch_rows:
        if close_enough(r[qty_key], diff):
            print("ГИПОТЕЗА ПОДТВЕРЖДЕНА: партия с количеством {0} объясняет всю разницу - "
                  "без неё сумма = {1}, совпадает с ожидаемым {2}.".format(r[qty_key], total - r[qty_key], expected))
            print("  Партия-кандидат на исключение: {0}".format(r))
            found = True
    if not found:
        # Пробуем сумму ЛЮБЫХ ДВУХ партий, если одна не подошла.
        for i, r1 in enumerate(batch_rows):
            for r2 in batch_rows[i + 1:]:
                if close_enough(r1[qty_key] + r2[qty_key], diff):
                    print("ГИПОТЕЗА (2 партии): {0} + {1} = {2} объясняет разницу.".format(
                        r1[qty_key], r2[qty_key], diff
                    ))
                    print("  Партии-кандидаты: {0} И {1}".format(r1, r2))
                    found = True
    if not found:
        print("Не нашёл одну/две партии, объясняющие разницу напрямую - нужен ручной разбор.")


def run_one(config, article_str, expected):
    bases = config["bases"]
    suffixes = [b.get("suffix", "") for b in bases]
    default_encoding = config.get("encoding", "cp866")
    sql_auth = config.get("sql_auth", {})

    base_article, suffix = split_suffix(article_str, suffixes)
    if suffix is None:
        print("{0}: не удалось определить базу по суффиксу".format(article_str))
        return

    base_cfg = None
    for b in bases:
        if b.get("suffix", "") == suffix:
            base_cfg = b
            break

    print("\n{0}\n=== {1} (база {2}, ожидаемый остаток {3}) ===".format("=" * 70, article_str, base_cfg["name"], expected))

    item_field = base_cfg["items_article_field"]
    fallback_field = base_cfg.get("items_article_fallback_field")
    id_field = base_cfg["items_id_field"]
    stock_item_field = base_cfg["stock_item_field"]
    qty_field = base_cfg["stock_qty_field"]
    period_field = base_cfg.get("stock_period_field", "PERIOD")
    extra_filter_field = base_cfg.get("stock_extra_filter_field")
    extra_filter_value = str(base_cfg.get("stock_extra_filter_value", "")).strip()

    if base_cfg.get("type", "dbf") == "sql":
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        user = sql_auth["user"]
        password = sql_auth["password"]

        cols_query = (
            "SELECT s.{0}, s.{1}, s.{2}, s.{3} FROM {4} s "
            "INNER JOIN {5} i ON i.{6} = s.{7} "
            "WHERE LTRIM(RTRIM(i.{8})) = '{9}'"
        ).format(
            period_field, extra_filter_field or stock_item_field, stock_item_field, qty_field,
            base_cfg["stock_table"], base_cfg["items_table"], id_field, stock_item_field,
            item_field, base_article,
        )
        rows = run_query(server, database, user, password, cols_query)
        if not rows:
            print("Товар с артикулом '{0}' не найден или нет строк остатка.".format(base_article))
            return
        parsed = []
        for r in rows:
            if len(r) < 4:
                continue
            try:
                parsed.append({
                    "period": r[0].strip(),
                    "filter": r[1].strip(),
                    "item": r[2].strip(),
                    "qty": float(r[3].strip().replace(",", ".")),
                })
            except (ValueError, IndexError):
                continue
        if not parsed:
            print("Не удалось разобрать строки остатка.")
            return
        latest_period = max(p["period"] for p in parsed)
        batch_rows = [p for p in parsed if p["period"] == latest_period and (not extra_filter_field or p["filter"] == extra_filter_value)]
        analyze_batches(batch_rows, expected, "qty")
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", default_encoding)

        items = read_dbf_table(base_path, base_cfg["items_table"], encoding)
        item_ids = set()
        for row in items:
            value = str(row.get(item_field, "")).strip()
            if not value and fallback_field:
                value = str(row.get(fallback_field, "")).strip()
            if value == base_article:
                item_ids.add(row[id_field])
        if not item_ids:
            print("Товар с артикулом '{0}' не найден.".format(base_article))
            return

        stock = read_dbf_table(base_path, base_cfg["stock_table"], encoding)
        all_rows = []
        for row in stock:
            if row[stock_item_field] in item_ids:
                all_rows.append(dict(row))
        if not all_rows:
            print("Нет строк остатка для найденных товаров.")
            return
        latest_period = max(r[period_field] for r in all_rows)
        batch_rows = [
            r for r in all_rows
            if r[period_field] == latest_period
            and (not extra_filter_field or str(r.get(extra_filter_field, "")).strip() == extra_filter_value)
        ]
        for r in batch_rows:
            r["qty"] = float(r[qty_field] or 0)
        analyze_batches(batch_rows, expected, "qty")


def run(pairs):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    for pair in pairs:
        if ":" not in pair:
            print("{0}: пропущено - формат должен быть артикул:ожидаемый_остаток".format(pair))
            continue
        article_str, expected_str = pair.rsplit(":", 1)
        try:
            expected = float(expected_str)
        except ValueError:
            print("{0}: не число '{1}'".format(pair, expected_str))
            continue
        try:
            run_one(config, article_str, expected)
        except Exception as exc:
            print("{0}: ОШИБКА - {1}".format(article_str, exc))


def main():
    if len(sys.argv) < 2:
        sys.exit("Использование: python diagnose_stock_anomaly.py артикул1:ожидаемый1 [артикул2:ожидаемый2 ...]")

    pairs = sys.argv[1:]
    log_filename = "diagnose_stock_anomaly_log.txt"
    commit_message = "Диагностика расхождений остатка ({0} артикулов)".format(len(pairs))
    run_with_log(log_filename, commit_message, lambda: run(pairs))


if __name__ == "__main__":
    main()
