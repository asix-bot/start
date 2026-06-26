"""
Проверяет (без подключения к базе), помечена ли база уже как проверенная
в config.json - то есть успешно прошла check_base.py в одном из прошлых
запусков setup.bat. Используется, чтобы при повторном запуске setup.bat
пропускать уже настроенные базы и спрашивать данные только новых/неудачных.

Exit code 0 - база уже проверена (verified: true), можно пропустить ввод.
Exit code 1 - база не настроена или не проверена, нужно спросить данные.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python is_base_verified.py <индекс 1-4>
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python is_base_verified.py <индекс 1-4>")

    try:
        index = int(sys.argv[1])
    except ValueError:
        sys.exit("Индекс базы должен быть числом 1-4")

    if not CONFIG_PATH.exists():
        sys.exit(1)

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    bases = config.get("bases", [])
    if len(bases) < index:
        sys.exit(1)

    base_cfg = bases[index - 1]
    if base_cfg.get("verified") is True:
        print("База {0} уже настроена и проверена ранее.".format(base_cfg.get("name", index)))
        sys.exit(0)

    sys.exit(1)


if __name__ == "__main__":
    main()
