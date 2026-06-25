"""
Экспорт артикул/остаток/цена из 4 баз 1С 7.7 (DBF) в один CSV и публикация в GitHub.

Настройки берутся из config.json (см. config.example.json — скопируй и заполни
своими путями, именами таблиц/полей, суффиксами и токеном GitHub).

Каждый запуск:
  1. Читает items/stock/price таблицы каждой базы из config["bases"].
  2. Соединяет их по внутреннему ID товара.
  3. К артикулу добавляет суффикс этой базы (например "00123" + "-B1" = "00123-B1").
  4. Складывает строки всех баз в один CSV (полная перезапись файла — это снэпшот
     на момент запуска, а не история).
  5. Коммитит и пушит файл в репозиторий на GitHub через git с токеном.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Запуск:
    pip install dbfread
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

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(
            "Не найден {0}.\n"
            "Скопируй config.example.json в config.json и заполни своими значениями.".format(CONFIG_PATH)
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def read_table(base_path, table_name, encoding):
    table_path = base_path / table_name
    if not table_path.exists():
        # Регистр имени файла может отличаться на разных ОС/копиях баз.
        candidates = list(base_path.glob("{0}.*".format(table_name.split(".")[0])))
        if not candidates:
            raise FileNotFoundError("Таблица {0} не найдена в {1}".format(table_name, base_path))
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def read_value_map(base_path, table_name, item_field, value_field, encoding):
    table = read_table(base_path, table_name, encoding)
    result = {}
    for row in table:
        result[row[item_field]] = row[value_field]
    return result


def export_base(base_cfg, encoding):
    base_path = Path(base_cfg["path"])
    suffix = base_cfg.get("suffix", "")

    items = read_table(base_path, base_cfg["items_table"], encoding)

    id_field = base_cfg["items_id_field"]
    article_field = base_cfg["items_article_field"]
    name_field = base_cfg.get("items_name_field")

    item_by_id = {}
    for row in items:
        item_by_id[row[id_field]] = row

    stock_by_id = read_value_map(
        base_path, base_cfg["stock_table"], base_cfg["stock_item_field"], base_cfg["stock_qty_field"], encoding
    )
    sale_price_by_id = read_value_map(
        base_path,
        base_cfg["sale_price_table"],
        base_cfg["sale_price_item_field"],
        base_cfg["sale_price_value_field"],
        encoding,
    )
    avg_cost_by_id = read_value_map(
        base_path,
        base_cfg["avg_cost_table"],
        base_cfg["avg_cost_item_field"],
        base_cfg["avg_cost_value_field"],
        encoding,
    )

    out_rows = []
    for item_id, item_row in item_by_id.items():
        raw_article = str(item_row.get(article_field, "")).strip()
        if not raw_article:
            continue
        out_rows.append(
            {
                "article": "{0}{1}".format(raw_article, suffix),
                "name": str(item_row.get(name_field, "")).strip() if name_field else "",
                "stock": stock_by_id.get(item_id, 0),
                "avg_cost": avg_cost_by_id.get(item_id, ""),
                "sale_price": sale_price_by_id.get(item_id, ""),
                "base": base_cfg["name"],
            }
        )
    return out_rows


def write_csv(rows, csv_path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["article", "name", "stock", "avg_cost", "sale_price", "base"]
        )
        writer.writeheader()
        writer.writerows(rows)


def write_log(log_lines, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def main():
    run_started_at = datetime.now()
    config = load_config()
    encoding = config.get("encoding", "cp866")

    all_rows = []
    log_lines = ["Запуск экспорта: {0:%Y-%m-%d %H:%M:%S}".format(run_started_at)]

    for base_cfg in config["bases"]:
        print("Читаю базу {0} ({1})...".format(base_cfg["name"], base_cfg["path"]))
        base_started_at = time.perf_counter()
        try:
            rows = export_base(base_cfg, encoding)
        except Exception as exc:
            elapsed = time.perf_counter() - base_started_at
            print("  Ошибка при чтении базы {0}: {1}".format(base_cfg["name"], exc))
            log_lines.append("{0}: ОШИБКА за {1:.2f} сек — {2}".format(base_cfg["name"], elapsed, exc))
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
