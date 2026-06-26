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

FAILURE_MARKERS = (
    "Не найдено ни одного .DBF файла",
    "Не удалось получить список таблиц",
    "Не найдено ни одной пользовательской таблицы",
)


def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python check_base.py <индекс 1-4>")

    try:
        index = int(sys.argv[1])
    except ValueError:
        sys.exit("Индекс базы должен быть числом 1-4")

    if not CONFIG_PATH.exists():
        sys.exit("Не найден {0}.".format(CONFIG_PATH))

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
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
        try:
            explore_base_sql(base_cfg, sql_auth, out_lines)
        except Exception as exc:
            print("Ошибка подключения к SQL Server: {0}".format(exc))
            sys.exit(1)
    else:
        base_path_raw = base_cfg.get("path", "")
        if not base_path_raw:
            print("Не задан путь для базы {0}.".format(base_cfg["name"]))
            sys.exit(1)
        base_path = Path(base_path_raw)
        if not base_path.exists():
            print("Путь не найден: {0}".format(base_path))
            sys.exit(1)
        try:
            explore_base_dbf(base_path, out_lines)
        except Exception as exc:
            print("Ошибка чтения DBF: {0}".format(exc))
            sys.exit(1)

    report_text = "\n".join(out_lines)
    for marker in FAILURE_MARKERS:
        if marker in report_text:
            print("Проверка базы {0} не прошла:".format(base_cfg["name"]))
            print(report_text)
            sys.exit(1)

    print("База {0} проверена успешно.".format(base_cfg["name"]))
    print(report_text)

    base_cfg["verified"] = True
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    if LOCAL_REPORT_PATH.exists():
        existing = LOCAL_REPORT_PATH.read_text(encoding="utf-8")
    else:
        existing = ""
    updated_report = existing + ("\n" if existing else "") + report_text
    LOCAL_REPORT_PATH.write_text(updated_report, encoding="utf-8")

    github_cfg = config.get("github")
    if github_cfg and github_cfg.get("token") and "ВСТАВЬ_СЮДА" not in github_cfg["token"]:
        repo_report_path = Path(github_cfg["repo_path"]) / "report.txt"
        repo_report_path.parent.mkdir(parents=True, exist_ok=True)
        repo_report_path.write_text(updated_report, encoding="utf-8")
        push_files(github_cfg, ["report.txt"], "Отчёт о структуре базы {0}".format(base_cfg["name"]))
    else:
        print("github.token не заполнен - report.txt сохранён только локально.")

    sys.exit(0)


if __name__ == "__main__":
    main()
