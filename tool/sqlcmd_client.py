"""
Тонкая обёртка над sqlcmd.exe для чтения данных из SQL-версии баз 1С 7.7.

Используется вместо pyodbc/pymssql, чтобы не зависеть от бинарных
расширений Python (на старом Python 3.4 готовых wheel-пакетов может не
быть). sqlcmd.exe должен быть установлен и доступен в PATH.

Совместимо с Python 3.4: без f-строк, без subprocess.run (появился в 3.5).
"""

import subprocess
import sys

# Кодировка консольного вывода sqlcmd на русской Windows обычно совпадает
# с активной OEM-кодовой страницей консоли (см. chcp 866 во всех bat-файлах
# проекта).
OUTPUT_ENCODING = "cp866"


def run_query(server, database, user, password, query):
    """Выполняет query через sqlcmd, возвращает список строк (каждая - список ячеек).

    К запросу автоматически добавляется "SET NOCOUNT ON;", чтобы sqlcmd не
    печатал служебную строку "(N rows affected)" вместе с данными.
    Колонки разделяются символом "|" (-s), без заголовков (-h -1).
    """
    full_query = "SET NOCOUNT ON; " + query
    cmd = [
        "sqlcmd",
        "-S", server,
        "-d", database,
        "-U", user,
        "-P", password,
        "-h", "-1",
        "-W",
        "-s", "|",
        "-Q", full_query,
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_bytes, stderr_bytes = process.communicate()
    if process.returncode != 0:
        stderr_text = stderr_bytes.decode(OUTPUT_ENCODING, errors="replace")
        stdout_text = stdout_bytes.decode(OUTPUT_ENCODING, errors="replace")
        raise RuntimeError(
            "sqlcmd завершился с ошибкой (сервер={0}, база={1}):\n{2}\n{3}".format(
                server, database, stdout_text, stderr_text
            )
        )

    text = stdout_bytes.decode(OUTPUT_ENCODING, errors="replace")
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        rows.append(line.split("|"))
    return rows


def run_query_raw(server, database, user, password, query):
    """Выполняет query через sqlcmd и возвращает сырой текстовый вывод как есть
    (с заголовками и форматированием sqlcmd) - удобно для отчётов/разведки,
    где нужна читаемость, а не точный парсинг."""
    cmd = [
        "sqlcmd",
        "-S", server,
        "-d", database,
        "-U", user,
        "-P", password,
        "-W",
        "-Q", query,
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_bytes, stderr_bytes = process.communicate()
    stdout_text = stdout_bytes.decode(OUTPUT_ENCODING, errors="replace")
    stderr_text = stderr_bytes.decode(OUTPUT_ENCODING, errors="replace")
    if process.returncode != 0:
        return "ОШИБКА sqlcmd:\n{0}\n{1}".format(stdout_text, stderr_text)
    return stdout_text
