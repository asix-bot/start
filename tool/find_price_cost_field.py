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

Перебор идёт по таблицам RG*/RA*/DT*/DH*/SC* (включая ПОДЧИНЁННЫЕ справочники,
например возможный "Цены номенклатуры" - подчинён Номенклатуре и ссылается
на справочник "Типы цен").

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Можно передать НЕСКОЛЬКО артикулов за один запуск (один пуш в GitHub).

Использование:
    python find_price_cost_field.py артикул1:цена1[:себестоимость1] [артикул2:цена2 ...]

Пример:
    python find_price_cost_field.py 100ш:2220:1350 941ш:2360 22ш:3720
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


def _parse_candidates(raw):
    """Число может храниться по-разному: "2220", "2220.00", "2220,00",
    с разделителем тысяч (пробел или точка/запятая) - "2 220.00",
    "2.220,00" (европейский формат, точка=тысячи, запятая=дробная часть).
    Возвращает ВСЕ разумные интерпретации строки как числа, без удаления
    дробной части (целое число без разделителя - это тоже валидный случай,
    str(value_str) уже его покрывает без изменений)."""
    text = str(raw).strip()
    if not text:
        return []
    candidates = set()
    no_space = text.replace(" ", "").replace("\xa0", "")
    for variant in (text, no_space):
        # Простая запятая как дробный разделитель: "1350,00" -> "1350.00"
        candidates.add(variant.replace(",", "."))
        # Точка как разделитель тысяч, запятая как дробная часть:
        # "2.220,00" -> убрать точки, запятую сделать дробной.
        if "." in variant and "," in variant:
            candidates.add(variant.replace(".", "").replace(",", "."))
        # Точка как разделитель тысяч без дробной части: "2.220" -> "2220"
        candidates.add(variant.replace(".", ""))
    results = []
    for candidate in candidates:
        try:
            results.append(float(candidate))
        except (TypeError, ValueError):
            continue
    return results


# НДС (20% и старая ставка 18%/10%) и проценты скидок, найденные в
# справочнике "Типы цен" (SC3769: "Скидка 8%", "Скидка 5%", "Скидка 25%" и
# т.п.) - на случай, если итоговая цена нигде не хранится готовым числом, а
# вычисляется из БАЗОВОЙ цены на лету (база * множитель). Проверяем оба
# направления (умножить и поделить), чтобы поймать как "цена без скидки"
# в базе при известной цене СО скидкой, так и наоборот.
_RATE_MULTIPLIERS = (1.20, 1.18, 1.10, 0.92, 0.95, 0.75, 0.80, 0.85, 0.90)


def close_enough(value_str, target):
    if target is None:
        return False
    for value in _parse_candidates(value_str):
        if abs(value - target) <= TOLERANCE:
            return True
        # Возможное хранение в другом масштабе (копейки вместо рублей и т.п.).
        for scale in (100.0, 1000.0, 0.01, 0.001):
            if abs(value - target * scale) <= TOLERANCE * scale:
                return True
        # Возможное хранение БАЗОВОЙ цены/себестоимости без НДС или скидки -
        # искомое число получается из найденного умножением/делением.
        for rate in _RATE_MULTIPLIERS:
            if abs(value - target * rate) <= TOLERANCE * rate:
                return True
            if abs(value - target / rate) <= TOLERANCE / rate:
                return True
    return False


def read_dbf_table(base_path, table_name, encoding):
    table_path = base_path / table_name
    if not table_path.exists():
        candidates = list(base_path.glob("{0}.*".format(table_name.split(".")[0])))
        if not candidates:
            raise FileNotFoundError("Таблица {0} не найдена в {1}".format(table_name, base_path))
        table_path = candidates[0]
    return DBF(str(table_path), encoding=encoding, ignore_missing_memofile=True)


def find_all_item_ids_dbf(base_path, items_table, encoding, article_field, fallback_field, id_field, base_article):
    """Артикул (SP4890) общий на ВСЕ размерные варианты одной модели - значит
    под одним base_article может быть несколько разных товаров (разных
    размеров). Возвращает список (item_id, row) для каждого совпадения, а не
    только первого - иначе можно случайно проверить не тот размер."""
    table = read_dbf_table(base_path, items_table, encoding)
    results = []
    for row in table:
        value = str(row.get(article_field, "")).strip()
        if not value and fallback_field:
            value = str(row.get(fallback_field, "")).strip()
        if value == base_article:
            results.append((row[id_field], dict(row)))
    return results


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


def find_all_item_ids_sql(server, database, user, password, items_table, article_field, fallback_field, id_field, base_article):
    """Аналог find_all_item_ids_dbf - SP4890 общий на все размерные варианты,
    под одним base_article может быть несколько разных товаров."""
    cols = [id_field, article_field]
    if fallback_field:
        cols.append(fallback_field)
    query = "SELECT {0} FROM {1}".format(", ".join(cols), items_table)
    rows = run_query(server, database, user, password, query)
    results = []
    for row in rows:
        if len(row) < 2:
            continue
        article = row[1].strip()
        if not article and fallback_field and len(row) > 2:
            article = row[2].strip()
        if article == base_article:
            results.append(row[0].strip())
    return results


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
    # RG* - периодические регистры накопления (остатки на конец периода).
    # RA* - регистры движений документов (приход/расход с суммами по каждому
    # документу).
    # DT* - табличная часть документов (строки счетов/накладных - именно
    # тут чаще всего лежит цена за единицу прямо в строке документа).
    # DH* - заголовки документов (на случай, если цена хранится не в строке).
    # SC* - справочники, включая ПОДЧИНЁННЫЕ (например "Цены номенклатуры" -
    # подчинённый справочник, привязанный и к товару, и к типу цены из
    # справочника "Типы цен" - именно там может лежать текущая цена).
    # 1S* - служебные таблицы 1С (1SCONST - периодические константы с полем
    # OBJID, которое МОЖЕТ ссылаться на объект/товар - редкий, но известный
    # способ привязать произвольное значение к объекту в 1С 7.7).
    names = set()
    for prefix in ("RG", "RA", "DT", "DH", "SC", "1S"):
        names.update(p.stem.upper() for p in base_path.glob("{0}*.DBF".format(prefix)) if p.stem.upper().startswith(prefix))
    return sorted(names)


def list_sql_rg_tables(server, database, user, password):
    output = run_query_raw(
        server, database, user, password,
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'RG%' OR TABLE_NAME LIKE 'RA%' "
        "OR TABLE_NAME LIKE 'DT%' OR TABLE_NAME LIKE 'DH%' OR TABLE_NAME LIKE 'SC%' OR TABLE_NAME LIKE '1S%'",
    )
    names = []
    for line in output.splitlines():
        line = line.strip()
        if line and line not in ("TABLE_NAME", "") and not line.startswith("-"):
            names.append(line)
    return names


def _numeric_fields(row_items):
    result = []
    for field_name, value in row_items:
        try:
            result.append((field_name, float(str(value).strip().replace(",", "."))))
        except (TypeError, ValueError):
            continue
    return result


def scan_dbf_table_for_item(base_path, table_name, encoding, item_id, price, cost):
    """Ищет совпадение и напрямую (поле = цена/себестоимость), и как
    отношение "сумма / количество" - в регистрах движений документов (RA*)
    цена/себестоимость часто хранится как ИТОГОВАЯ сумма по строке, а не
    цена за единицу, поэтому делим каждое числовое поле на каждое другое
    числовое поле той же строки (похожее на количество) и сравниваем
    результат с искомым значением."""
    table = read_dbf_table(base_path, table_name, encoding)
    matches = []
    for row in table:
        row_values = [str(v).strip() for v in row.values()]
        if item_id not in row_values:
            continue
        for field_name, value in row.items():
            if close_enough(value, price) or close_enough(value, cost):
                matches.append((field_name, value, dict(row)))
        numeric = _numeric_fields(row.items())
        for sum_field, sum_value in numeric:
            for qty_field, qty_value in numeric:
                if sum_field == qty_field or qty_value in (0, 0.0):
                    continue
                unit_value = sum_value / qty_value
                if close_enough(unit_value, price) or close_enough(unit_value, cost):
                    matches.append((
                        "{0}/{1}".format(sum_field, qty_field), unit_value, dict(row)
                    ))
    return matches


SQL_SCAN_CHUNK_SIZE = 5000
MAX_SQL_SCAN_ROWS = 500000


def _scan_row_for_match(table_name, row, item_id, price, cost, matches):
    if item_id not in [str(v).strip() for v in row]:
        return
    for value in row:
        if close_enough(value, price) or close_enough(value, cost):
            matches.append((table_name, row))
            break
    numeric = _numeric_fields(list(enumerate(row)))
    for sum_idx, sum_value in numeric:
        for qty_idx, qty_value in numeric:
            if sum_idx == qty_idx or qty_value in (0, 0.0):
                continue
            unit_value = sum_value / qty_value
            if close_enough(unit_value, price) or close_enough(unit_value, cost):
                matches.append((table_name, row))


def scan_sql_table_for_item(server, database, user, password, table_name, item_id, price, cost):
    """Читает таблицу СТРАНИЦАМИ по SQL_SCAN_CHUNK_SIZE строк (OFFSET/FETCH),
    а не одним запросом "SELECT * FROM table" - на таблицах с сотнями тысяч/
    миллионами строк (многолетняя история документов) одиночный большой
    запрос переполняет память (subprocess.communicate() буферизует весь
    вывод сразу). Постраничное чтение держит в памяти только одну страницу
    за раз, поэтому может пройти ВСЮ таблицу (до MAX_SQL_SCAN_ROWS суммарно),
    а не обрывается/пропускается целиком."""
    matches = []
    offset = 0
    while offset < MAX_SQL_SCAN_ROWS:
        query = (
            "SELECT * FROM {0} ORDER BY (SELECT NULL) "
            "OFFSET {1} ROWS FETCH NEXT {2} ROWS ONLY"
        ).format(table_name, offset, SQL_SCAN_CHUNK_SIZE)
        rows = run_query(server, database, user, password, query)
        if not rows:
            break
        for row in rows:
            _scan_row_for_match(table_name, row, item_id, price, cost, matches)
        offset += SQL_SCAN_CHUNK_SIZE
        if len(rows) < SQL_SCAN_CHUNK_SIZE:
            break
    return matches


def run_one(config, article, price, cost):
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
        item_ids = find_all_item_ids_sql(server, database, user, password, base_cfg["items_table"], article_field, fallback_field, id_field, base_article)
        if not item_ids:
            sys.exit("Товар с артикулом '{0}' не найден в items_table".format(base_article))
        print("Найдено товаров с этим базовым артикулом (разные размеры/варианты): {0}".format(len(item_ids)))

        rg_tables = list_sql_rg_tables(server, database, user, password)
        print("Найдено RG-таблиц: {0}".format(len(rg_tables)))

        any_match = False
        for item_id in item_ids:
            print("\n=== Вариант ID='{0}' ===".format(item_id))
            catalog_row, catalog_columns = find_item_full_row_sql(server, database, user, password, base_cfg["items_table"], id_field, item_id)
            if catalog_row:
                print("Строка карточки товара ({0}): {1}".format(base_cfg["items_table"], catalog_row))
                for idx, value in enumerate(catalog_row):
                    if close_enough(value, price) or close_enough(value, cost):
                        col_name = catalog_columns[idx] if idx < len(catalog_columns) else "?"
                        any_match = True
                        print("  СОВПАДЕНИЕ В КАРТОЧКЕ: колонка #{0} ('{1}') = '{2}'".format(idx, col_name, value))

            for table_name in rg_tables:
                print("  сканирую {0}...".format(table_name))
                try:
                    matches = scan_sql_table_for_item(server, database, user, password, table_name, item_id, price, cost)
                except Exception as exc:
                    print("  {0}: ошибка чтения - {1}".format(table_name, exc))
                    continue
                if matches:
                    any_match = True
                    print("--- {0}: найдены строки с товаром И числом близким к цене/себестоимости ---".format(table_name))
                    for _, row in matches:
                        print("  {0}".format(row))
        if not any_match:
            print("\nНи в карточке, ни в одной RG-таблице ни для одного варианта не найдено подходящего числа.")
    else:
        base_path = Path(base_cfg["path"])
        encoding = base_cfg.get("encoding", default_encoding)
        items = find_all_item_ids_dbf(base_path, base_cfg["items_table"], encoding, article_field, fallback_field, id_field, base_article)
        if not items:
            sys.exit("Товар с артикулом '{0}' не найден в items_table".format(base_article))
        print("Найдено товаров с этим базовым артикулом (разные размеры/варианты): {0}".format(len(items)))

        rg_tables = list_dbf_rg_tables(base_path)
        print("Найдено RG-таблиц: {0}".format(len(rg_tables)))

        any_match = False
        for item_id, item_row in items:
            print("\n=== Вариант ID='{0}' ===".format(item_id))
            print("Строка карточки товара: {0}".format(item_row))
            for field_name, value in item_row.items():
                if close_enough(value, price) or close_enough(value, cost):
                    any_match = True
                    print("  СОВПАДЕНИЕ В КАРТОЧКЕ: поле '{0}' = '{1}'".format(field_name, value))

            for table_name in rg_tables:
                print("  сканирую {0}...".format(table_name))
                try:
                    matches = scan_dbf_table_for_item(base_path, table_name + ".DBF", encoding, item_id, price, cost)
                except Exception as exc:
                    print("  {0}: ошибка чтения - {1}".format(table_name, exc))
                    continue
                if matches:
                    any_match = True
                    print("--- {0}: найдены поля с числом близким к цене/себестоимости ---".format(table_name))
                    seen_rows = set()
                    for field_name, value, row in matches:
                        row_key = tuple(sorted((k, str(v)) for k, v in row.items()))
                        marker = "  поле '{0}'='{1}' | строка: {2}".format(field_name, value, row)
                        if row_key not in seen_rows:
                            seen_rows.add(row_key)
                            print(marker)
        if not any_match:
            print("\nНи в карточке, ни в одной RG-таблице ни для одного варианта не найдено подходящего числа.")


def run(specs):
    """specs - список строк "артикул:цена" или "артикул:цена:себестоимость" -
    позволяет проверить сразу несколько товаров за один запуск/один пуш в
    GitHub, а не гонять скрипт по одному."""
    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    for spec in specs:
        parts = spec.split(":")
        if len(parts) < 2:
            print("\n{0}: пропущено - формат должен быть артикул:цена[:себестоимость]".format(spec))
            continue
        article = parts[0]
        try:
            price = float(parts[1])
            cost = float(parts[2]) if len(parts) > 2 and parts[2] else None
        except ValueError:
            print("\n{0}: не число в цене/себестоимости".format(spec))
            continue
        print("\n{0}\n### {1} ###".format("#" * 70, spec))
        try:
            run_one(config, article, price, cost)
        except SystemExit as exc:
            print(exc.code)
        except Exception as exc:
            print("ОШИБКА: {0}".format(exc))


def main():
    if len(sys.argv) < 2:
        sys.exit(
            "Использование: python find_price_cost_field.py артикул:цена[:себестоимость] [артикул2:цена2 ...]"
        )

    specs = sys.argv[1:]
    log_filename = "find_price_cost_field_log.txt"
    commit_message = "Поиск поля цены/себестоимости ({0} артикулов)".format(len(specs))
    run_with_log(log_filename, commit_message, lambda: run(specs))


if __name__ == "__main__":
    main()
