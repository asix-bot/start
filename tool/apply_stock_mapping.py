"""
Подставляет в config.json найденное сопоставление полей для товаров и
остатка (артикул+остаток) во ВСЕ базы - не трогая type/path/sql_server/
sql_database/suffix/verified.

Найдено по анализу report.txt и diagnose_stock.py (структура одинаковая
у всех 4 баз):
  - Товары: SC4889 (ID, CODE=артикул, DESCR=название)
  - Остаток: RG1130 - периодический регистр 1С 7.7, берётся сумма по
    самому позднему PERIOD для каждого товара (см. read_dbf_latest_period_map
    и read_sql_latest_period_map в main.py)
  - На каждый период есть ДВЕ строки с одинаковым количеством, отличающиеся
    только полем SP2654 (параллельный учёт, например БУ/НУ) - чтобы не
    задвоить остаток, оставляем только SP2654='0'.

Себестоимость/цена продажи (avg_cost_table/sale_price_table) очищаются -
они пока не найдены, main.py относится к ним как к опциональным и не
блокирует экспорт артикул+остаток из-за их отсутствия.

Имя таблицы пишется с расширением .DBF для DBF-баз и без расширения для
SQL-баз (соответствует тому, как main.py их использует).

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python apply_stock_mapping.py
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

FIELD_MAPPING = {
    "items_article_field": "CODE",
    "items_id_field": "ID",
    "items_name_field": "DESCR",
    "stock_item_field": "SP1131",
    "stock_qty_field": "SP1133",
    "stock_period_field": "PERIOD",
    "stock_extra_filter_field": "SP2654",
    "stock_extra_filter_value": "0",
}


def main():
    if not CONFIG_PATH.exists():
        sys.exit("Не найден {0}.".format(CONFIG_PATH))

    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())

    updated = []
    for base_cfg in config["bases"]:
        is_dbf = base_cfg.get("type", "dbf") == "dbf"
        base_cfg["items_table"] = "SC4889.DBF" if is_dbf else "SC4889"
        base_cfg["stock_table"] = "RG1130.DBF" if is_dbf else "RG1130"
        for key, value in FIELD_MAPPING.items():
            base_cfg[key] = value

        base_cfg.pop("avg_cost_table", None)
        base_cfg.pop("avg_cost_item_field", None)
        base_cfg.pop("avg_cost_value_field", None)
        base_cfg.pop("sale_price_table", None)
        base_cfg.pop("sale_price_item_field", None)
        base_cfg.pop("sale_price_value_field", None)

        updated.append(base_cfg.get("name", "?"))

    open(str(CONFIG_PATH), "w", encoding="utf-8").write(json.dumps(config, ensure_ascii=False, indent=2))
    print("Сопоставление товаров/остатка применено для баз: " + ", ".join(updated))
    print("avg_cost_table/sale_price_table очищены (пока не настроены).")


if __name__ == "__main__":
    main()
