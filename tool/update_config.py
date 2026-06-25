"""
Утилита для setup.bat: подставляет в config.json пути и суффиксы баз,
введённые пользователем в консоли, без необходимости открывать JSON руками.

Имена/типы полей (items_table, stock_table и т.д.) этим скриптом не трогаются —
их всё равно нужно заполнить по report.txt после explore_dbf.py.

Использование:
    python update_config.py <path1> <suffix1> <path2> <suffix2> <path3> <suffix3> <path4> <suffix4>
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
EXAMPLE_PATH = Path(__file__).parent / "config.example.json"


def main():
    if len(sys.argv) != 9:
        sys.exit("Нужно ровно 8 аргументов: path1 suffix1 path2 suffix2 path3 suffix3 path4 suffix4")

    pairs = [(sys.argv[i], sys.argv[i + 1]) for i in range(1, 9, 2)]

    source_path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH
    config = json.loads(source_path.read_text(encoding="utf-8"))

    bases = config["bases"]
    if len(bases) != len(pairs):
        sys.exit("В config.json сейчас {0} баз, а передано {1} пар путь/суффикс.".format(len(bases), len(pairs)))

    for base_cfg, pair in zip(bases, pairs):
        base_cfg["path"] = pair[0]
        base_cfg["suffix"] = pair[1]

    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print("config.json обновлён: {0}".format(CONFIG_PATH))


if __name__ == "__main__":
    main()
