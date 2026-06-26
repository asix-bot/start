"""
Утилита для setup.bat: подставляет в config.json тип/путь-или-сервер и
суффикс для каждой базы, плюс общий логин/пароль SQL Server для SQL-баз -
введённые пользователем в консоли, без необходимости открывать JSON руками.

Имена/типы полей (items_table, stock_table и т.д.) этим скриптом не трогаются -
их всё равно нужно заполнить по report.txt после explore.py.

На каждую из 4 баз передаётся 4 аргумента: TYPE LOC1 LOC2 SUFFIX, где:
  - TYPE: "D" (DBF) или "S" (SQL)
  - для DBF: LOC1 = путь к папке с базой, LOC2 = "NONE" (не используется)
  - для SQL: LOC1 = имя сервера, LOC2 = имя базы данных
В конце - ещё 2 аргумента: общий SQL_USER SQL_PASSWORD (для всех SQL-баз).

Итого 4*4 + 2 = 18 аргументов.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python update_config.py T1 LOC1_1 LOC1_2 SUF1 T2 LOC2_1 LOC2_2 SUF2 ... SQLUSER SQLPASS
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
EXAMPLE_PATH = Path(__file__).parent / "config.example.json"

EXPECTED_ARGS = 4 * 4 + 2


def main():
    if len(sys.argv) != EXPECTED_ARGS + 1:
        sys.exit(
            "Нужно ровно {0} аргументов: "
            "(тип путьИЛИсервер базаИЛиNONE суффикс) x4 + sql_user sql_password".format(EXPECTED_ARGS)
        )

    args = sys.argv[1:]
    base_args = args[:16]
    sql_user = args[16]
    sql_password = args[17]

    quads = [tuple(base_args[i:i + 4]) for i in range(0, 16, 4)]

    source_path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH
    config = json.loads(source_path.read_text(encoding="utf-8"))

    bases = config["bases"]
    if len(bases) != len(quads):
        sys.exit("В config.json сейчас {0} баз, а передано {1} наборов данных.".format(len(bases), len(quads)))

    for base_cfg, quad in zip(bases, quads):
        base_type_raw, loc1, loc2, suffix = quad
        if base_type_raw.strip().upper() == "S":
            base_cfg["type"] = "sql"
            base_cfg["sql_server"] = loc1
            base_cfg["sql_database"] = loc2
            base_cfg.pop("path", None)
        else:
            base_cfg["type"] = "dbf"
            base_cfg["path"] = loc1
            base_cfg.pop("sql_server", None)
            base_cfg.pop("sql_database", None)
        base_cfg["suffix"] = suffix

    config["sql_auth"] = {"user": sql_user, "password": sql_password}

    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print("config.json обновлён: {0}".format(CONFIG_PATH))


if __name__ == "__main__":
    main()
