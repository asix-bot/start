"""
Сбрасывает флаг "verified" у ОДНОЙ базы (по индексу 1-4) в config.json,
чтобы setup.bat при следующем запуске не пропускал её, а спросил данные
и проверил заново.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.

Использование:
    python reset_base.py <индекс 1-4>
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python reset_base.py <индекс 1-4>")

    try:
        index = int(sys.argv[1])
    except ValueError:
        sys.exit("Индекс базы должен быть числом 1-4")

    if not CONFIG_PATH.exists():
        sys.exit("Не найден {0}.".format(CONFIG_PATH))

    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
    bases = config["bases"]
    if len(bases) < index:
        sys.exit("В config.json только {0} баз(ы), а запрошен индекс {1}.".format(len(bases), index))

    base_cfg = bases[index - 1]
    base_cfg["verified"] = False

    open(str(CONFIG_PATH), "w", encoding="utf-8").write(json.dumps(config, ensure_ascii=False, indent=2))
    print("Флаг verified сброшен для базы {0} ({1}). При следующем запуске setup.bat".format(
        index, base_cfg["name"]
    ))
    print("она снова будет спрошена и проверена.")


if __name__ == "__main__":
    main()
