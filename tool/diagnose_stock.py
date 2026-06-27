"""
Диагностика: выводит ВСЕ строки регистра остатка (stock_table) для ОДНОГО
товара (по артикулу, без суффикса) - без какой-либо агрегации/дедупликации.
Нужно, чтобы вручную увидеть, действительно ли строки дублируются точь-в-точь,
или это разные строки с одинаковым количеством (тогда дедуп по строке не
поможет, и проблема в другом измерении регистра).

Весь вывод сохраняется локально в diagnose_stock_log.txt и пушится в
GitHub (если в config.json настроен токен) - результат можно скачать из
репозитория, не делая скриншоты терминала.

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


def run(index, article):
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    base_cfg = config["bases"][index - 1]
    print("База: {0} ({1})".format(base_cfg["name"], base_cfg.get("type", "dbf")))

    if base_cfg.get("type", "dbf") == "sql":
        server = base_cfg["sql_server"]
        database = base_cfg["sql_database"]
        sql_auth = config.get("sql_auth", {})
        user = sql_auth["user"]
        password = sql_auth["password"]

        # Важно: ID товара в 1С хранится с ведущими пробелами (например
        # '      D11'), поэтому НЕЛЬЗЯ доставать его текстом через sqlcmd
        # и подставлять обратно в следующий запрос - .strip() при разборе
        # текстового вывода теряет эти пробелы, и второй запрос находит 0
        # строк. Поэтому делаем всё ОДНИМ запросом через JOIN, не вынимая
        # ID товара в Python вообще.
        all_rows_query = (
            "SELECT s.* FROM {0} s "
            "INNER JOIN {1} i ON i.{2} = s.{3} "
            "WHERE LTRIM(RTRIM(i.{4})) = '{5}' "
            "ORDER BY s.{6}"
        ).format(
            base_cfg["stock_table"],
            base_cfg["items_table"],
            base_cfg["items_id_field"],
            base_cfg["stock_item_field"],
            base_cfg["items_article_field"],
            article,
            base_cfg.get("stock_period_field", "PERIOD"),
        )
        print("--- все строки stock_table для этого товара, без агрегации ---")
        print(run_query_raw(server, database, user, password, all_rows_query))
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", config.get("encoding", "cp866"))

        items = read_dbf_table(base_path, base_cfg["items_table"], encoding)
        item_ids = []
        for row in items:
            if str(row.get(base_cfg["items_article_field"], "")).strip() == article:
                item_ids.append(row[base_cfg["items_id_field"]])
        if not item_ids:
            sys.exit("Товар с артикулом {0} не найден.".format(article))
        # Артикул (SP4890) общий на ВСЕ размерные варианты одной модели -
        # под одним article может быть несколько разных товаров (ID),
        # поэтому берём ВСЕ совпадения, а не только первый.
        print("Найдены ID товаров ({0} шт.): {1}".format(len(item_ids), item_ids))

        print("\n--- все строки stock_table для этих ID, без агрегации ---")
        stock = read_dbf_table(base_path, base_cfg["stock_table"], encoding)
        item_field = base_cfg["stock_item_field"]
        item_id_set = set(item_ids)
        count = 0
        for row in stock:
            if row[item_field] in item_id_set:
                count += 1
                print(count, dict(row))
        print("\nВсего найдено строк:", count)


def main():
    if len(sys.argv) != 3:
        sys.exit("Использование: python diagnose_stock.py <индекс_базы 1-4> <артикул_без_суффикса>")

    index = int(sys.argv[1])
    article = sys.argv[2]

    log_filename = "diagnose_stock_log.txt"
    commit_message = "Диагностика остатка: база {0}, артикул {1}".format(index, article)
    run_with_log(log_filename, commit_message, lambda: run(index, article))


if __name__ == "__main__":
    main()
