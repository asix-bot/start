"""
Проверяет список артикулов (с суффиксом, например "9714ки"): существуют ли
они в источнике (items_table нужной базы) вообще, и если да - какой у них
сырой остаток (до отбрасывания нулевых/отрицательных).

Помогает различить причину отсутствия артикула в stock_prices.csv:
  - "не найден в источнике" - артикул физически нет в SC4889 этой базы
    (другой склад/канал, не входящий в покрытие экспорта, либо опечатка).
  - "найден, остаток X" - артикул есть, просто его остаток <= 0 (и до
    фикса 26.06 такие строки полностью пропадали из CSV).

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python diagnose_missing_articles.py арт1 арт2 арт3 ...

Пример:
    python diagnose_missing_articles.py 9714ки 7397ки 5687з 1635з
"""

import json
import sys
from pathlib import Path

from diagnostic_log import run_with_log
from main import (
    CONFIG_PATH,
    export_base_dbf,
    export_base_sql,
)


def split_suffix(article, suffixes):
    # Сначала проверяем более длинные суффиксы (например "ки" раньше "и"),
    # чтобы не ошибиться с более коротким случайным совпадением.
    for suffix in sorted(suffixes, key=len, reverse=True):
        if suffix and article.endswith(suffix):
            return article[: -len(suffix)], suffix
    return article, None


def run(articles_to_check):
    if not CONFIG_PATH.exists():
        sys.exit("Не найден {0}.".format(CONFIG_PATH))

    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    bases = config["bases"]
    suffixes = [b.get("suffix", "") for b in bases]
    default_encoding = config.get("encoding", "cp866")
    sql_auth = config.get("sql_auth", {})

    bases_by_suffix = {}
    for base_cfg in bases:
        bases_by_suffix[base_cfg.get("suffix", "")] = base_cfg

    # Один раз читаем item_by_id и stock_by_id (без фильтрации по нулю) для
    # каждой базы, которая встречается среди проверяемых артикулов.
    cache = {}

    for article in articles_to_check:
        raw_article, suffix = split_suffix(article, suffixes)
        if suffix is None or suffix not in bases_by_suffix:
            print("{0}: не удалось определить базу по суффиксу".format(article))
            continue

        base_cfg = bases_by_suffix[suffix]
        base_name = base_cfg["name"]

        if base_name not in cache:
            print("Читаю базу {0}...".format(base_name))
            try:
                if base_cfg.get("type", "dbf") == "sql":
                    item_by_id, stock_by_id, _, _ = export_base_sql(base_cfg, sql_auth)
                else:
                    encoding = base_cfg.get("encoding", default_encoding)
                    item_by_id, stock_by_id, _, _ = export_base_dbf(base_cfg, encoding)
                cache[base_name] = (item_by_id, stock_by_id)
            except Exception as exc:
                print("  Ошибка чтения базы {0}: {1}".format(base_name, exc))
                cache[base_name] = ({}, {})

        item_by_id, stock_by_id = cache[base_name]

        found_id = None
        found_name = None
        for item_id, info in item_by_id.items():
            if str(info.get("article", "")).strip() == raw_article:
                found_id = item_id
                found_name = info.get("name", "")
                break

        if found_id is None:
            print("{0} (база {1}, артикул-источник '{2}'): НЕ НАЙДЕН в items_table".format(
                article, base_name, raw_article
            ))
        else:
            raw_stock = stock_by_id.get(found_id, "<нет строк в stock_table>")
            print("{0} (база {1}): найден, ID='{2}', название='{3}', сырой остаток={4}".format(
                article, base_name, found_id, found_name, raw_stock
            ))


def main():
    if len(sys.argv) < 2:
        sys.exit("Использование: python diagnose_missing_articles.py арт1 [арт2 ...]")

    articles_to_check = sys.argv[1:]
    log_filename = "diagnose_missing_articles_log.txt"
    commit_message = "Диагностика отсутствующих артикулов ({0} шт.)".format(len(articles_to_check))
    run_with_log(log_filename, commit_message, lambda: run(articles_to_check))


if __name__ == "__main__":
    main()
