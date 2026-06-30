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

Чтение цены/себестоимости (DT3580/DT434) проходит по ВСЕЙ истории документов
и ощутимо нагружает сервер 1С - поэтому пересчитывается не каждый запуск, а
РАЗ В СУТКИ и только в окне price_recalc_window_start..price_recalc_window_end
(по умолчанию 19:00-23:59 - время, когда магазин не работает, см.
config.json). В остальное время суток значения берутся из локального
price_cache.json (не пушится в git - живёт рядом со скриптом, не в
repo_path). Остаток при этом всё равно читается и пушится каждый час как
раньше - окно касается только цены/себестоимости.

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

# Расчёт цены/себестоимости читает ВСЮ историю документов (DT3580/DT434,
# годы накопленных строк) - это ощутимая нагрузка на сервер 1С. Магазин не
# работает вечером, поэтому пересчёт разрешён только РАЗ В СУТКИ и только
# внутри окна price_recalc_window_start..price_recalc_window_end (по
# умолчанию 19:00-23:59, настраивается в config.json) - первый часовой
# запуск, попавший в это окно, считает свежие значения, остальные запуски
# (в том числе все остальные часы суток) берут значения из локального
# кэша (price_cache.json, не пушится в git - живёт рядом со скриптом).
PRICE_CACHE_PATH = Path(__file__).parent / "price_cache.json"
DEFAULT_PRICE_RECALC_WINDOW_START = "19:00"
DEFAULT_PRICE_RECALC_WINDOW_END = "23:59"


def load_price_cache():
    if not PRICE_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(open(str(PRICE_CACHE_PATH), encoding="utf-8").read())
    except (ValueError, OSError):
        return {}


def save_price_cache(cache):
    open(str(PRICE_CACHE_PATH), "w", encoding="utf-8").write(json.dumps(cache, ensure_ascii=False, indent=2))


def _parse_hhmm(text):
    hours, minutes = text.split(":")
    return int(hours), int(minutes)


def should_recompute_prices_now(cache, base_name, window_start, window_end, now=None):
    """True только если ТЕКУЩЕЕ время внутри окна [window_start, window_end]
    (формат "HH:MM") И для этой базы пересчёт ещё не делался СЕГОДНЯ внутри
    этого окна - то есть ровно один раз в сутки, в вечернее время простоя
    магазина, а не на каждый часовой запуск."""
    now = now or datetime.now()
    start_h, start_m = _parse_hhmm(window_start)
    end_h, end_m = _parse_hhmm(window_end)
    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    if not (start_minutes <= current_minutes <= end_minutes):
        return False

    entry = cache.get(base_name)
    if not entry or "computed_at" not in entry:
        return True
    try:
        computed_at = datetime.strptime(entry["computed_at"], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return True
    computed_minutes = computed_at.hour * 60 + computed_at.minute
    already_done_today = computed_at.date() == now.date() and computed_minutes >= start_minutes
    return not already_done_today

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
    """Явный размер из характеристики "Размер" (текст "р.NN" в DESCR).
    Это надёжный сигнал - применяем его к артикулу всегда, даже если товар
    единственный в своей модели (например partner_sources)."""
    name = name or ""
    match = SIZE_PATTERN.search(name)
    if match:
        return match.group(1)
    return None


def extract_free_text_tag(name):
    """Последний текст в скобках в конце названия (цвет/материал/габариты/
    номер модели - НЕ обязательно размер). В отличие от extract_size() это
    ненадёжный сигнал: товар с единственным вариантом тоже может иметь
    скобки в названии (например "(металл)", "(синий)") без какого-либо
    реального размерного варианта. Поэтому не приклеиваем это к артикулу
    всегда - используем только как один из способов различить КОЛЛИЗИЮ
    артикулов (см. export_base), когда explicit-размера нет."""
    name = name or ""
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


# 1SJOURN - служебный ГЛОБАЛЬНЫЙ журнал документов 1С 7.7: содержит IDDOC и
# DATE для ВСЕХ типов документов (счетов, накладных и т.д.), в отличие от
# регистра движений RAxxxx, который покрывает только те документы, что
# реально подвинули остаток (расходные счета туда не всегда попадают - из-за
# этого даты для DT3580/цены продажи раньше не находились). Имя таблицы
# одно и то же для всех баз (генерируется самой 1С), поэтому не привязано к
# stock_table и не требует отдельной настройки в config.json.
DEFAULT_DOC_DATE_TABLE = "1SJOURN"


def doc_date_table_name(base_cfg, override=None):
    name = override or base_cfg.get("doc_date_table") or DEFAULT_DOC_DATE_TABLE
    if base_cfg.get("type", "dbf") == "dbf" and not name.upper().endswith(".DBF"):
        name += ".DBF"
    return name


def read_dbf_doc_date_map(base_path, table_name, encoding, doc_field="IDDOC", date_field="DATE"):
    """IDDOC -> DATE из глобального журнала документов 1SJOURN. Нужно, чтобы
    найти САМЫЙ ПОЗДНИЙ документ для товара в других таблицах (цена/
    себестоимость), которые сами по себе дату не хранят надёжно."""
    result = {}
    for row in read_dbf_table(base_path, table_name, encoding):
        doc = row.get(doc_field)
        date = row.get(date_field)
        if doc is not None and date is not None:
            result[doc] = date
    return result


def read_dbf_latest_doc_value_map(base_path, table_name, item_field, value_field, doc_field, doc_date_map, encoding):
    """Для каждого товара берёт value_field из строки с САМЫМ ПОЗДНИМ
    документом (по doc_date_map) - например цену/себестоимость из последней
    накладной. Если для документа дата не нашлась (например тип документа не
    отражается в регистре движений, как иногда бывает с расходными счетами) -
    строка всё равно используется как запасной вариант (чтобы поле не
    осталось пустым), но с низшим приоритетом - датированная строка всегда
    замещает недатированную."""
    best_date = {}
    result = {}
    for row in read_dbf_table(base_path, table_name, encoding):
        item = row[item_field]
        date = doc_date_map.get(row.get(doc_field))
        has_date = date is not None
        if item not in best_date:
            best_date[item] = (has_date, date)
            result[item] = row[value_field]
            continue
        prev_has_date, prev_date = best_date[item]
        if has_date and (not prev_has_date or date > prev_date):
            best_date[item] = (has_date, date)
            result[item] = row[value_field]
        elif not has_date and not prev_has_date:
            # Нет даты ни у текущей, ни у предыдущей строки - берём
            # последнюю встреченную как лучший доступный вариант.
            result[item] = row[value_field]
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


# Цена продажи в этой конфигурации 1С 7.7 НЕ хранится готовым числом - она
# считается на лету как "себестоимость * (1 + наценка%/100) * (1 - скидка%/100)".
# Сам процент наценки/скидки лежит в подчинённом справочнике "Цены номенклатуры"
# (найдено через перебор по размеру таблицы - PARENTEXT=товар, DESCR=название
# типа цены вроде "Розничная", и два процентных поля). Это надёжнее, чем
# DT3580 (история конкретных прошлых продаж - может быть очень устаревшей).
def read_dbf_price_markup_map(base_path, table_name, encoding, parent_field, descr_field, type_name, markup_field, discount_field):
    result = {}
    for row in read_dbf_table(base_path, table_name, encoding):
        if str(row.get(descr_field, "")).strip() != type_name:
            continue
        item = row.get(parent_field)
        try:
            markup = float(row.get(markup_field) or 0)
            discount = float(row.get(discount_field) or 0)
        except (TypeError, ValueError):
            continue
        result[item] = (markup, discount)
    return result


def apply_price_markup(avg_cost_by_id, markup_by_id):
    result = {}
    for item, (markup, discount) in markup_by_id.items():
        cost = avg_cost_by_id.get(item)
        if cost is None:
            continue
        try:
            cost = float(cost)
        except (TypeError, ValueError):
            continue
        result[item] = cost * (1 + markup / 100.0) * (1 - discount / 100.0)
    return result


def export_base_dbf(base_cfg, encoding, compute_prices=True):
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

    doc_date_map = {}
    if compute_prices and (base_cfg.get("sale_price_table") or base_cfg.get("avg_cost_table")):
        try:
            doc_date_map = read_dbf_doc_date_map(base_path, doc_date_table_name(base_cfg), encoding)
        except Exception:
            doc_date_map = {}

    sale_price_by_id = {}
    if compute_prices and base_cfg.get("sale_price_table"):
        try:
            sale_price_by_id = read_dbf_latest_doc_value_map(
                base_path,
                base_cfg["sale_price_table"],
                base_cfg["sale_price_item_field"],
                base_cfg["sale_price_value_field"],
                base_cfg.get("sale_price_doc_field", "IDDOC"),
                doc_date_map,
                encoding,
            )
        except Exception:
            sale_price_by_id = {}

    avg_cost_by_id = {}
    if compute_prices and base_cfg.get("avg_cost_table"):
        try:
            avg_cost_by_id = read_dbf_latest_doc_value_map(
                base_path,
                base_cfg["avg_cost_table"],
                base_cfg["avg_cost_item_field"],
                base_cfg["avg_cost_value_field"],
                base_cfg.get("avg_cost_doc_field", "IDDOC"),
                doc_date_map,
                encoding,
            )
        except Exception:
            avg_cost_by_id = {}

    if compute_prices and base_cfg.get("price_markup_table"):
        try:
            markup_by_id = read_dbf_price_markup_map(
                base_path,
                base_cfg["price_markup_table"],
                encoding,
                base_cfg.get("price_markup_parent_field", "PARENTEXT"),
                base_cfg.get("price_markup_descr_field", "DESCR"),
                base_cfg.get("price_markup_type_name", "Розничная"),
                base_cfg.get("price_markup_percent_field"),
                base_cfg.get("price_discount_percent_field"),
            )
            computed = apply_price_markup(avg_cost_by_id, markup_by_id)
            sale_price_by_id.update(computed)
        except Exception:
            pass

    return item_by_id, stock_by_id, avg_cost_by_id, sale_price_by_id


# ---------------------------------------------------------------------------
# SQL Server (через sqlcmd.exe)
# ---------------------------------------------------------------------------

def read_sql_doc_date_map(server, database, user, password, table, doc_field="IDDOC", date_field="DATE"):
    """SQL-аналог read_dbf_doc_date_map - IDDOC -> DATE из глобального журнала документов 1SJOURN."""
    query = "SELECT DISTINCT {0}, {1} FROM {2}".format(doc_field, date_field, table)
    rows = run_query(server, database, user, password, query)
    result = {}
    for row in rows:
        if len(row) < 2:
            continue
        doc = row[0].strip()
        date = row[1].strip()
        if doc and date:
            result[doc] = date
    return result


def read_sql_latest_doc_value_map(server, database, user, password, table, item_field, value_field, doc_field, doc_date_map):
    """SQL-аналог read_dbf_latest_doc_value_map - для каждого товара берёт
    value_field из строки с САМЫМ ПОЗДНИМ документом (по дате из регистра
    движений). Сравнение дат идёт как строк ('YYYY-MM-DD...') - формат
    sqlcmd для datetime сортируется лексикографически так же, как по
    времени. Если для документа дата не нашлась (некоторые типы документов,
    например расходные счета, могут не отражаться в регистре движений) -
    строка используется как запасной вариант с низшим приоритетом, а не
    пропускается - иначе поле осталось бы пустым для всех товаров."""
    query = "SELECT {0}, {1}, {2} FROM {3}".format(item_field, value_field, doc_field, table)
    rows = run_query(server, database, user, password, query)
    best_date = {}
    result = {}
    for row in rows:
        if len(row) < 3:
            continue
        item = row[0].strip()
        value = row[1].strip()
        doc = row[2].strip()
        date = doc_date_map.get(doc)
        has_date = bool(date)
        if item not in best_date:
            best_date[item] = (has_date, date)
            result[item] = value
            continue
        prev_has_date, prev_date = best_date[item]
        if has_date and (not prev_has_date or date > prev_date):
            best_date[item] = (has_date, date)
            result[item] = value
        elif not has_date and not prev_has_date:
            result[item] = value
    return result


def read_sql_price_markup_map(server, database, user, password, table, parent_field, descr_field, type_name, markup_field, discount_field):
    """SQL-аналог read_dbf_price_markup_map - фильтр по DESCR делается СЕРВЕРНОЙ
    стороной (WHERE), а не вытягиванием всей таблицы (она может быть в районе
    100к+ строк - один тип цены на товар после фильтра кратно меньше)."""
    query = "SELECT {0}, {1}, {2} FROM {3} WHERE LTRIM(RTRIM({4})) = '{5}'".format(
        parent_field, markup_field, discount_field, table, descr_field, type_name
    )
    rows = run_query(server, database, user, password, query)
    result = {}
    for row in rows:
        if len(row) < 3:
            continue
        item = row[0].strip()
        try:
            markup = float(row[1].strip().replace(",", "."))
            discount = float(row[2].strip().replace(",", "."))
        except (ValueError, IndexError):
            continue
        result[item] = (markup, discount)
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


def export_base_sql(base_cfg, sql_auth, compute_prices=True):
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

    doc_date_map = {}
    if compute_prices and (base_cfg.get("sale_price_table") or base_cfg.get("avg_cost_table")):
        try:
            doc_date_map = read_sql_doc_date_map(server, database, user, password, doc_date_table_name(base_cfg))
        except Exception:
            doc_date_map = {}

    sale_price_by_id = {}
    if compute_prices and base_cfg.get("sale_price_table"):
        try:
            sale_price_by_id = read_sql_latest_doc_value_map(
                server, database, user, password,
                base_cfg["sale_price_table"], base_cfg["sale_price_item_field"], base_cfg["sale_price_value_field"],
                base_cfg.get("sale_price_doc_field", "IDDOC"), doc_date_map,
            )
        except Exception:
            sale_price_by_id = {}

    avg_cost_by_id = {}
    if compute_prices and base_cfg.get("avg_cost_table"):
        try:
            avg_cost_by_id = read_sql_latest_doc_value_map(
                server, database, user, password,
                base_cfg["avg_cost_table"], base_cfg["avg_cost_item_field"], base_cfg["avg_cost_value_field"],
                base_cfg.get("avg_cost_doc_field", "IDDOC"), doc_date_map,
            )
        except Exception:
            avg_cost_by_id = {}

    if compute_prices and base_cfg.get("price_markup_table"):
        try:
            markup_by_id = read_sql_price_markup_map(
                server, database, user, password,
                base_cfg["price_markup_table"],
                base_cfg.get("price_markup_parent_field", "PARENTEXT"),
                base_cfg.get("price_markup_descr_field", "DESCR"),
                base_cfg.get("price_markup_type_name", "Розничная"),
                base_cfg.get("price_markup_percent_field"),
                base_cfg.get("price_discount_percent_field"),
            )
            computed = apply_price_markup(avg_cost_by_id, markup_by_id)
            sale_price_by_id.update(computed)
        except Exception:
            pass

    return item_by_id, stock_by_id, avg_cost_by_id, sale_price_by_id


# ---------------------------------------------------------------------------
# Общая склейка результатов (не зависит от типа базы)
# ---------------------------------------------------------------------------

def export_base(
    base_cfg, default_encoding, sql_auth, exclude_zero_stock=False,
    price_cache=None,
    price_recalc_window_start=DEFAULT_PRICE_RECALC_WINDOW_START,
    price_recalc_window_end=DEFAULT_PRICE_RECALC_WINDOW_END,
):
    base_type = base_cfg.get("type", "dbf")
    suffix = base_cfg.get("suffix", "")
    base_name = base_cfg["name"]
    if price_cache is None:
        price_cache = {}

    compute_prices = should_recompute_prices_now(
        price_cache, base_name, price_recalc_window_start, price_recalc_window_end
    )

    if base_type == "sql":
        item_by_id, stock_by_id, avg_cost_by_id, sale_price_by_id = export_base_sql(
            base_cfg, sql_auth, compute_prices=compute_prices
        )
    else:
        encoding = base_cfg.get("encoding", default_encoding)
        item_by_id, stock_by_id, avg_cost_by_id, sale_price_by_id = export_base_dbf(
            base_cfg, encoding, compute_prices=compute_prices
        )

    if compute_prices:
        price_cache[base_name] = {
            "computed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "avg_cost_by_id": avg_cost_by_id,
            "sale_price_by_id": sale_price_by_id,
        }
    else:
        cached_entry = price_cache.get(base_name, {})
        avg_cost_by_id = cached_entry.get("avg_cost_by_id", {})
        sale_price_by_id = cached_entry.get("sale_price_by_id", {})

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
            # Скобки в названии (если есть) НЕ приклеиваем сюда - они часто
            # не размер (цвет/материал/модель), см. extract_free_text_tag().
            # Их используем только ниже, если этот артикул реально
            # коллизирует с другим товаром.
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
    # читающего CSV в словарь по артикулу. Различаем такие дубликаты:
    # сначала пробуем текст в скобках (цвет/материал/модель - см.
    # extract_free_text_tag), если он сам уникален внутри коллизирующей
    # группы; иначе - внутренним кодом товара (CODE/ID). Скобки НЕ
    # приклеиваются, если коллизии нет - товар с единственным вариантом
    # получает чистый базовый артикул, даже если в названии есть скобки.
    article_counts = {}
    for row in out_rows:
        article_counts[row["article"]] = article_counts.get(row["article"], 0) + 1

    collision_groups = {}
    for row in out_rows:
        if article_counts[row["article"]] > 1:
            collision_groups.setdefault(row["article"], []).append(row)

    for rows in collision_groups.values():
        tag_counts = {}
        tags = {}
        for row in rows:
            tag = extract_free_text_tag(row["name"])
            tags[id(row)] = tag
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for row in rows:
            tag = tags[id(row)]
            if tag and tag_counts[tag] == 1:
                row["article"] = "{0}-{1}".format(row["article"], tag)
            else:
                disambiguator = row["_disambiguator"] or str(row["_item_id"]).strip()
                row["article"] = "{0}-{1}".format(row["article"], disambiguator)

    for row in out_rows:
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
    price_recalc_window_start = config.get("price_recalc_window_start", DEFAULT_PRICE_RECALC_WINDOW_START)
    price_recalc_window_end = config.get("price_recalc_window_end", DEFAULT_PRICE_RECALC_WINDOW_END)

    force_price_recalc = "--force-price-recalc" in sys.argv
    if force_price_recalc:
        # Для ручной проверки прямо сейчас, не дожидаясь вечернего окна -
        # игнорируем и кэш, и окно времени, пересчитываем цену/себестоимость
        # для всех баз в этом запуске независимо от текущего часа.
        print("--force-price-recalc: окно времени и кэш цены/себестоимости игнорируются на этот запуск.")
        price_cache = {}
        price_recalc_window_start = "00:00"
        price_recalc_window_end = "23:59"
    else:
        price_cache = load_price_cache()

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
            rows = export_base(
                base_cfg, encoding, sql_auth, exclude_zero_stock,
                price_cache=price_cache,
                price_recalc_window_start=price_recalc_window_start,
                price_recalc_window_end=price_recalc_window_end,
            )
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

    save_price_cache(price_cache)

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
