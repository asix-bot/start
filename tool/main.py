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

Запуск:
    pip install dbfread
    python main.py
"""

import csv
import json
import sys
from pathlib import Path

from dbfread import DBF

from github_publish import push_files

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"Не найден {CONFIG_PATH}.\n"
            "Скопируй config.example.json в config.json и заполни своими значениями."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def read_table(base_path: Path, table_name: str, encoding: str) -> DBF:
    table_path = base_path / table_name
    if not table_path.exists():
        # Регистр имени файла может отличаться на разных ОС/копиях баз.
        candidates = list(base_path.glob(f"{table_name.split('.')[0]}.*"))
        if not candidates:
            raise FileNotFoundError(f"Таблица {table_name} не найдена в {base_path}")
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def export_base(base_cfg: dict, encoding: str) -> list[dict]:
    base_path = Path(base_cfg["path"])
    suffix = base_cfg.get("suffix", "")

    items = read_table(base_path, base_cfg["items_table"], encoding)
    stock = read_table(base_path, base_cfg["stock_table"], encoding)
    price = read_table(base_path, base_cfg["price_table"], encoding)

    id_field = base_cfg["items_id_field"]
    article_field = base_cfg["items_article_field"]
    name_field = base_cfg.get("items_name_field")

    item_by_id = {row[id_field]: row for row in items}

    stock_item_field = base_cfg["stock_item_field"]
    stock_qty_field = base_cfg["stock_qty_field"]
    stock_by_id: dict = {}
    for row in stock:
        stock_by_id[row[stock_item_field]] = row[stock_qty_field]

    price_item_field = base_cfg["price_item_field"]
    price_value_field = base_cfg["price_value_field"]
    price_by_id: dict = {}
    for row in price:
        price_by_id[row[price_item_field]] = row[price_value_field]

    out_rows = []
    for item_id, item_row in item_by_id.items():
        raw_article = str(item_row.get(article_field, "")).strip()
        if not raw_article:
            continue
        out_rows.append(
            {
                "article": f"{raw_article}{suffix}",
                "name": str(item_row.get(name_field, "")).strip() if name_field else "",
                "stock": stock_by_id.get(item_id, 0),
                "price": price_by_id.get(item_id, ""),
                "base": base_cfg["name"],
            }
        )
    return out_rows


def write_csv(rows: list[dict], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["article", "name", "stock", "price", "base"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    config = load_config()
    encoding = config.get("encoding", "cp866")

    all_rows: list[dict] = []
    for base_cfg in config["bases"]:
        print(f"Читаю базу {base_cfg['name']} ({base_cfg['path']})...")
        try:
            rows = export_base(base_cfg, encoding)
        except Exception as exc:
            print(f"  Ошибка при чтении базы {base_cfg['name']}: {exc}")
            continue
        print(f"  Найдено товаров: {len(rows)}")
        all_rows.extend(rows)

    github_cfg = config["github"]
    csv_path = Path(github_cfg["repo_path"]) / github_cfg["csv_path_in_repo"]
    write_csv(all_rows, csv_path)
    print(f"CSV записан: {csv_path} ({len(all_rows)} строк)")

    push_files(github_cfg, [github_cfg["csv_path_in_repo"]], "Обновление остатков и цен из 1С")


if __name__ == "__main__":
    main()
