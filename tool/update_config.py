"""
Утилита для setup.bat: обновляет в config.json тип и расположение ОДНОЙ
базы (по индексу 1-4). Используется в потоке setup.bat, который
проверяет базы по одной, циклом, а не все 4 сразу - так ошибка в данных
одной базы не требует переввода остальных.

Логин/пароль SQL Server (config["sql_auth"]) этим скриптом не трогаются -
они зашиты прямо в config.json/config.example.json и не запрашиваются
в setup.bat.

Имена баз и суффиксы уже зашиты в config.json/config.example.json и не
передаются сюда - менять их через этот скрипт не нужно.

Имена/типы полей (items_table, stock_table и т.д.) этим скриптом не трогаются -
их всё равно нужно заполнить по report.txt после check_base.py для всех баз.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python update_config.py <индекс 1-4> <D|S> <путь_или_сервер> <база_или_NONE>
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
EXAMPLE_PATH = Path(__file__).parent / "config.example.json"


def main():
    if len(sys.argv) != 5:
        sys.exit("Нужно ровно 4 аргумента: индекс(1-4) D-или-S путь-или-сервер база-или-NONE")

    index_raw, base_type_raw, loc1, loc2 = sys.argv[1:]

    try:
        index = int(index_raw)
    except ValueError:
        sys.exit("Индекс базы должен быть числом 1-4, получено: {0}".format(index_raw))
    if index < 1 or index > 4:
        sys.exit("Индекс базы должен быть от 1 до 4, получено: {0}".format(index))

    source_path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH
    config = json.loads(source_path.read_text(encoding="utf-8"))

    bases = config["bases"]
    if len(bases) < index:
        sys.exit("В config.json только {0} баз(ы), а запрошен индекс {1}.".format(len(bases), index))

    base_cfg = bases[index - 1]

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

    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print("config.json обновлён для базы {0} ({1}): {2}".format(index, base_cfg["name"], CONFIG_PATH))


if __name__ == "__main__":
    main()
