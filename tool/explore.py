"""
Разведчик структуры всех баз 1С 7.7, перечисленных в config.json - и DBF,
и SQL Server (через sqlcmd.exe), в зависимости от поля "type" каждой базы.

В отличие от explore_dbf.py (принимает пути через argv), этот скрипт сам
читает config.json - пути/сервера к этому моменту уже туда записаны
(setup.bat делает это перед вызовом explore.py).

Результат - report.txt (общий для DBF и SQL частей), который также
коммитится и пушится в репозиторий, если в config.json настроен github.token.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python explore.py
"""

import json
import sys
from pathlib import Path

from explore_dbf import explore_base as explore_base_dbf
from explore_sql import explore_base_sql
from github_publish import push_files

CONFIG_PATH = Path(__file__).parent / "config.json"


def main():
    if not CONFIG_PATH.exists():
        sys.exit("Не найден {0}. Сначала запусти setup.bat хотя бы до шага 4.".format(CONFIG_PATH))

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    sql_auth = config.get("sql_auth", {})

    out_lines = []
    for base_cfg in config["bases"]:
        base_type = base_cfg.get("type", "dbf")
        print("Изучаю базу {0} [{1}]...".format(base_cfg["name"], base_type))
        try:
            if base_type == "sql":
                explore_base_sql(base_cfg, sql_auth, out_lines)
            else:
                explore_base_dbf(Path(base_cfg["path"]), out_lines)
        except Exception as exc:
            out_lines.append("\nБАЗА {0}: ОШИБКА при разведке - {1}".format(base_cfg["name"], exc))
            print("  Ошибка: {0}".format(exc))

    report = "\n".join(out_lines)
    print(report)

    report_path = Path(__file__).parent / "report.txt"
    report_path.write_text(report, encoding="utf-8")
    print("\n\nОтчёт также сохранён в {0}".format(report_path))

    github_cfg = config.get("github")
    if github_cfg and github_cfg.get("token") and "ВСТАВЬ_СЮДА" not in github_cfg["token"]:
        repo_report_path = Path(github_cfg["repo_path"]) / "report.txt"
        repo_report_path.parent.mkdir(parents=True, exist_ok=True)
        repo_report_path.write_text(report, encoding="utf-8")
        push_files(github_cfg, ["report.txt"], "Отчёт о структуре баз 1С (explore)")
    else:
        print("github.token не заполнен - report.txt не публикуется в GitHub.")


if __name__ == "__main__":
    main()
