"""
Подставляет в config.json найденное сопоставление полей для товаров и
остатка (артикул+остаток) во ВСЕ базы - не трогая type/path/sql_server/
sql_database/suffix/verified.

Найдено по анализу report.txt и diagnose_stock.py (структура одинаковая
у всех 4 баз):
  - Товары: SC4889 (ID, артикул, DESCR=название)
  - Остаток: RG1130 - периодический регистр 1С 7.7, берётся сумма по
    самому позднему PERIOD для каждого товара (см. read_dbf_latest_period_map
    и read_sql_latest_period_map в main.py)
  - На каждый период есть ДВЕ строки с одинаковым количеством, отличающиеся
    только полем SP2654 (параллельный учёт, например БУ/НУ) - чтобы не
    задвоить остаток, оставляем только SP2654='0'.

Артикул - НЕ CODE (это внутренний код конкретного размера/варианта, не
совпадающий с человеческим артикулом). Реальный "человеческий" артикул
лежит в SP4890 - он ОДИН на товар вне зависимости от размера (найдено
find_article_field.py: 15 разных CODE одной модели имеют одинаковое
SP4890). main.py сам добавляет размер (вытащенный из DESCR регэкспом
"р.NN") через тире, например "100ш-37". Если SP4890 пустое (товар без
размерных вариантов) - используется CODE как запасной вариант
(items_article_fallback_field).

Себестоимость/цена продажи найдены через find_price_cost_field.py (перебор
по известному значению из независимой базы, проверено на товарах "100ш" и
"7132з"):
  - Цена продажи: DT3580 (табличная часть расходных документов/счетов) -
    SP3586=товар, SP3591=цена за единицу.
  - Себестоимость: DT434 (табличная часть приходных накладных) -
    SP448=товар, SP451=себестоимость за единицу из этой поставки.
  - И там, и там IDDOC - номер документа. main.py берёт строку с САМЫМ
    ПОЗДНИМ документом для каждого товара (дата документа подтягивается из
    stock_table, где она уже есть) - то есть себестоимость именно "по
    последней поставке", как и просили, а не средняя по всем поставкам.

Поля DT3580/DT434 проверены на базах Шишина (DBF) и Захарина (SQL) - для
Киселева/Кукушкиной предполагается та же структура (общая для всех 4 баз
конфигурация 1С), но это не перепроверено отдельно. Если коды полей там
отличаются, main.py просто не найдёт совпадений и оставит avg_cost/
sale_price пустыми для той базы (как и раньше) - экспорт артикул+остаток
не блокируется.

ВАЖНО про цену продажи: DT3580 - это история КОНКРЕТНЫХ прошлых продаж, а
не текущая цена - для товаров с редкими продажами она может быть сильно
устаревшей. Текущая цена в этой конфигурации 1С 7.7 вообще НЕ хранится
готовым числом - она считается на лету как "себестоимость * (1+наценка%/100)
* (1-скидка%/100)". Сама наценка/скидка лежит в подчинённом справочнике
"Цены номенклатуры" (найдено перебором размеров таблиц - искали таблицу
размером ~"товаров x типов цен"):
  - Таблица: SC3772 - PARENTEXT=товар, DESCR=название типа цены
    ("Розничная", "Закупочная", "Скидка N%" и т.п.), SP3864=наценка%,
    SP6937=скидка%. Проверено на товаре 4241ки (база Киселев): наценка
    80% от себестоимости 1075 даёт 1935 ≈ показанные в самой 1С 1930
    (расхождение ~0.3%, видимо из-за момента фиксации себестоимости).
  - main.py читает строку с DESCR='Розничная' (настраивается через
    price_markup_type_name) и ПЕРЕСЧИТЫВАЕТ sale_price из avg_cost - это
    значение приоритетнее DT3580 (свежее и точнее), DT3580 остаётся как
    запасной вариант для товаров без записи в SC3772.
  - Поля проверены только на базе Киселев - для остальных баз предполагается
    та же структура, не перепроверено.

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
    "items_article_field": "SP4890",
    "items_article_fallback_field": "CODE",
    "items_id_field": "ID",
    "items_name_field": "DESCR",
    "stock_item_field": "SP1131",
    "stock_qty_field": "SP1133",
    "stock_period_field": "PERIOD",
    "stock_extra_filter_field": "SP2654",
    "stock_extra_filter_value": "0",
    "avg_cost_item_field": "SP448",
    "avg_cost_value_field": "SP451",
    "avg_cost_doc_field": "IDDOC",
    "sale_price_item_field": "SP3586",
    "sale_price_value_field": "SP3591",
    "sale_price_doc_field": "IDDOC",
    "price_markup_parent_field": "PARENTEXT",
    "price_markup_descr_field": "DESCR",
    "price_markup_type_name": "Розничная",
    "price_markup_percent_field": "SP3864",
    "price_discount_percent_field": "SP6937",
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
        base_cfg["avg_cost_table"] = "DT434.DBF" if is_dbf else "DT434"
        base_cfg["sale_price_table"] = "DT3580.DBF" if is_dbf else "DT3580"
        base_cfg["price_markup_table"] = "SC3772.DBF" if is_dbf else "SC3772"
        for key, value in FIELD_MAPPING.items():
            base_cfg[key] = value

        updated.append(base_cfg.get("name", "?"))

    open(str(CONFIG_PATH), "w", encoding="utf-8").write(json.dumps(config, ensure_ascii=False, indent=2))
    print("Сопоставление товаров/остатка/цены/себестоимости применено для баз: " + ", ".join(updated))


if __name__ == "__main__":
    main()
