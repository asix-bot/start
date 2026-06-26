"""
Проверяет ОДНУ базу (по индексу 1-4) из config.json: пытается прочитать её
структуру (DBF-файлы или таблицы SQL Server через sqlcmd), и если успешно -
дописывает результат в накопительный report.txt, пушит его в GitHub и
помечает базу как "verified": true в config.json.

Используется в новом потоке setup.bat: для каждой базы по очереди -
ввели данные, проверили именно эту базу, и только при успехе переходят
к следующей. Если проверка не прошла (exit code 1), setup.bat должен
повторно запросить данные для той же базы.

Флаг "verified" в config.json позволяет при повторном запуске setup.bat
пропускать уже настроенные и проверенные базы (см. is_base_verified.py).

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python check_base.py <индекс 1-4>
"""

import json
import sys
from pathlib import Path

from explore_dbf import explore_base as explore_base_dbf
from explore_sql import explore_base_sql
from github_publish import push_files

CONFIG_PATH = Path(__file__).parent / "config.json"
LOCAL_REPORT_PATH = Path(__file__).parent / "report.txt"
ERROR_LOG_PATH = Path(__file__).parent / "last_check_error.txt"

FAILURE_MARKERS = (
    "Не найдено ни одного .DBF файла",
    "Не удалось получить список таблиц",
    "Не найдено ни одной пользовательской таблицы",
)

MAX_CONSOLE_LINES = 25


def fail(message_text):
    """Печатает короткую версию ошибки в консоль (полный текст - в файл), завершает с кодом 1."""
    open(str(ERROR_LOG_PATH), "w", encoding="utf-8").write(message_text)

    lines = message_text.splitlines()
    if len(lines) > MAX_CONSOLE_LINES:
        shown = lines[:MAX_CONSOLE_LINES]
        print("\n".join(shown))
        print("... обрезано, всего строк: {0}".format(len(lines)))
        print("Полный текст ошибки сохранён в {0}".format(ERROR_LOG_PATH))
    else:
        print(message_text)

    sys.exit(1)


def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python check_base.py <индекс 1-4>")

    try:
        index = int(sys.argv[1])
    except ValueError:
        sys.exit("Индекс базы должен быть числом 1-4")

    if not CONFIG_PATH.exists():
        sys.exit("Не найден {0}.".format(CONFIG_PATH))

    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8").read())
    bases = config["bases"]
    if len(bases) < index:
        sys.exit("В config.json только {0} баз(ы), а запрошен индекс {1}.".format(len(bases), index))

    base_cfg = bases[index - 1]
    base_type = base_cfg.get("type", "dbf")
    sql_auth = config.get("sql_auth", {})

    out_lines = []

    if base_type == "sql":
        server = base_cfg.get("sql_server", "")
        database = base_cfg.get("sql_database", "")
        if not server or not database:
            print("Не заданы sql_server/sql_database для базы {0}.".format(base_cfg["name"]))
            sys.exit(1)
        if not sql_auth.get("user") or not sql_auth.get("password"):
            print("ОШИБКА: в config.json не заполнен sql_auth (логин/пароль SQL Server).")
            sys.exit(1)
        try:
            explore_base_sql(base_cfg, sql_auth, out_lines)
        except Exception as exc:
            exc_text = str(exc)
            if "Login failed" in exc_text or "18456" in exc_text:
                fail(
                    "ОШИБКА ЛОГИНА/ПАРОЛЯ SQL Server для базы {0} (пользователь '{1}'):\n{2}".format(
                        base_cfg["name"], sql_auth.get("user"), exc_text
                    )
                )
            else:
                fail("Ошибка подключения к SQL Server для базы {0}: {1}".format(base_cfg["name"], exc_text))
    else:
        base_path_raw = base_cfg.get("path", "")
        if not base_path_raw:
            fail("Не задан путь для базы {0}.".format(base_cfg["name"]))
        base_path = Path(base_path_raw)
        if not base_path.exists():
            fail("Путь не найден для базы {0}: {1}".format(base_cfg["name"], base_path))
        try:
            explore_base_dbf(base_path, out_lines)
        except Exception as exc:
            fail("Ошибка чтения DBF для базы {0}: {1}".format(base_cfg["name"], exc))

    report_text = "\n".join(out_lines)

    if "Login failed" in report_text or "18456" in report_text:
        fail(
            "ОШИБКА ЛОГИНА/ПАРОЛЯ SQL Server для базы {0} (пользователь '{1}'):\n{2}".format(
                base_cfg["name"], sql_auth.get("user"), report_text
            )
        )

    for marker in FAILURE_MARKERS:
        if marker in report_text:
            fail("Проверка базы {0} не прошла:\n{1}".format(base_cfg["name"], report_text))

    print("База {0} проверена успешно.".format(base_cfg["name"]))
    report_lines = report_text.splitlines()
    if len(report_lines) > MAX_CONSOLE_LINES:
        print("\n".join(report_lines[:MAX_CONSOLE_LINES]))
        print("... обрезано, всего строк: {0}. Полный отчёт - в report.txt.".format(len(report_lines)))
    else:
        print(report_text)

    base_cfg["verified"] = True
    open(str(CONFIG_PATH), "w", encoding="utf-8").write(json.dumps(config, ensure_ascii=False, indent=2))

    if LOCAL_REPORT_PATH.exists():
        existing = open(str(LOCAL_REPORT_PATH), encoding="utf-8").read()
    else:
        existing = ""
    updated_report = existing + ("\n" if existing else "") + report_text
    open(str(LOCAL_REPORT_PATH), "w", encoding="utf-8").write(updated_report)

    github_cfg = config.get("github")
    if github_cfg and github_cfg.get("token") and "ВСТАВЬ_СЮДА" not in github_cfg["token"]:
        repo_report_path = Path(github_cfg["repo_path"]) / "report.txt"
        try:
            repo_report_path.parent.mkdir(parents=True)
        except FileExistsError:
            pass
        open(str(repo_report_path), "w", encoding="utf-8").write(updated_report)
        push_files(github_cfg, ["report.txt"], "Отчёт о структуре базы {0}".format(base_cfg["name"]))
    else:
        print("github.token не заполнен - report.txt сохранён только локально.")

    sys.exit(0)


if __name__ == "__main__":
    main()
