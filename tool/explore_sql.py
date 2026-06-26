"""
Разведчик структуры SQL-версии баз 1С 7.7 (через sqlcmd.exe).

Подключается к указанному серверу/базе SQL Server, выводит список таблиц
и их колонок с примерами строк - аналогично explore_dbf.py, но для SQL.

Используется не напрямую, а через explore.py (он читает config.json и
сам решает, какие базы DBF, а какие SQL).

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.
"""

from sqlcmd_client import run_query_raw

# Те же подсказки по именам таблиц, что и в explore_dbf.py - в SQL-версии
# 1С 7.7 обычно сохраняет те же имена таблиц, что и в DBF-версии.
INTERESTING_HINTS = ("SC", "RG", "RA", "1SC", "DH", "DT")

SAMPLE_ROWS = 5
SAMPLE_ROWS_INTERESTING = 60
SCAN_LIMIT = 20000


def looks_interesting(table_name):
    name = table_name.upper()
    for hint in INTERESTING_HINTS:
        if name.startswith(hint):
            return True
    return False


def list_tables(server, database, user, password):
    query = "SELECT name FROM sys.tables ORDER BY name"
    output = run_query_raw(server, database, user, password, query)
    if "ОШИБКА" in output or "Msg " in output:
        # Возможно, очень старый SQL Server без sys.tables (до 2005) - пробуем sysobjects.
        query = "SELECT name FROM sysobjects WHERE xtype='U' ORDER BY name"
        output = run_query_raw(server, database, user, password, query)
    return output


def explore_base_sql(base_cfg, sql_auth, out_lines):
    server = base_cfg["sql_server"]
    database = base_cfg["sql_database"]
    user = sql_auth["user"]
    password = sql_auth["password"]

    separator = "=" * 80
    out_lines.append("\n{0}\nБАЗА (SQL): {1} - сервер {2}, база {3}\n{0}".format(
        separator, base_cfg["name"], server, database
    ))

    tables_output = list_tables(server, database, user, password)
    if "ОШИБКА" in tables_output:
        out_lines.append("  Не удалось получить список таблиц:\n" + tables_output)
        return

    table_names = []
    for line in tables_output.splitlines():
        name = line.strip()
        if name and name.lower() not in ("name", "----", ""):
            # sqlcmd печатает строку из дефисов под заголовком "name" - её и сам
            # заголовок пропускаем.
            if not name.startswith("-") and name.lower() != "name":
                table_names.append(name)

    if not table_names:
        out_lines.append("  Не найдено ни одной пользовательской таблицы. Сырой вывод:\n" + tables_output)
        return

    out_lines.append("  Найдено таблиц: {0}".format(len(table_names)))

    table_names.sort(key=lambda n: (not looks_interesting(n), n))

    for table_name in table_names:
        interesting = looks_interesting(table_name)
        marker = " <-- возможно интересна" if interesting else ""
        out_lines.append("\n  [{0}]{1}".format(table_name, marker))

        columns_query = (
            "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH "
            "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{0}' ORDER BY ORDINAL_POSITION"
        ).format(table_name)
        columns_output = run_query_raw(server, database, user, password, columns_query)
        out_lines.append("    Колонки:\n" + indent(columns_output, "      "))

        sample_count = SAMPLE_ROWS_INTERESTING if interesting else SAMPLE_ROWS
        if interesting:
            # Случайные строки по всей таблице (а не просто первые N) - так
            # попадают разные документы/периоды. SCAN_LIMIT ограничивает
            # внутренний TOP, чтобы ORDER BY NEWID() не сортировал всю
            # огромную таблицу целиком (это может быть медленно).
            sample_query = (
                "SELECT TOP {0} * FROM (SELECT TOP {1} * FROM [{2}]) t ORDER BY NEWID()"
            ).format(sample_count, SCAN_LIMIT, table_name)
        else:
            sample_query = "SELECT TOP {0} * FROM [{1}]".format(sample_count, table_name)
        sample_output = run_query_raw(server, database, user, password, sample_query)
        out_lines.append("    Примеры строк:\n" + indent(sample_output, "      "))


def indent(text, prefix):
    lines = text.splitlines()
    return "\n".join(prefix + line for line in lines)
