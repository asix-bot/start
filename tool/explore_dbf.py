"""
Разведчик структуры баз 1С 7.7.

Проходит по указанным папкам с базами (каталоги, где лежат .DBF файлы)
и для каждого DBF-файла печатает: имя файла, список полей (имя+тип+длина)
и несколько примеров строк. Результат пишет и в консоль, и в текстовый
отчёт report.txt — его удобно скопировать и показать для разбора полей.

Использование:
    pip install dbfread
    python explore_dbf.py "C:\\Base1" "C:\\Base2" "C:\\Base3" "C:\\Base4"

Можно передать только те базы, которые хочешь изучить сейчас (необязательно все 4).
Кодировка DOS-кириллицы (cp866) стандартна для 1С 7.7; если текст в отчёте
выглядит как "кракозябры", поменяй ENCODING ниже на 'cp1251'.

Если рядом существует config.json (см. config.example.json) с заполненным
блоком "github", то report.txt после генерации также закоммитится и
запушится в репозиторий (полезно, чтобы разобрать структуру баз удалённо,
не копируя report.txt руками).

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.
"""

import json
import sys
from pathlib import Path

from dbfread import DBF

from github_publish import push_files

CONFIG_PATH = Path(__file__).parent / "config.json"

ENCODING = "cp866"
SAMPLE_ROWS = 5

# Таблицы 1С 7.7, в которых обычно есть смысл искать артикул/остаток/цену.
# Это не жёсткое правило (конфигурация нестандартная), но помогает быстрее
# найти нужное среди десятков DBF-файлов.
INTERESTING_HINTS = ("SC", "RG", "1SC", "DH", "DT")


def looks_interesting(filename):
    name = filename.upper()
    return any(name.startswith(h) for h in INTERESTING_HINTS)


def explore_base(base_path, out_lines):
    separator = "=" * 80
    out_lines.append("\n{0}\nБАЗА: {1}\n{0}".format(separator, base_path))

    dbf_files = sorted(base_path.glob("*.DBF")) + sorted(base_path.glob("*.dbf"))
    if not dbf_files:
        out_lines.append("  Не найдено ни одного .DBF файла в этой папке (может, путь не верен,"
                          " или таблицы лежат в подпапке).")
        return

    out_lines.append("  Найдено DBF-файлов: {0}".format(len(dbf_files)))

    # Сортируем так, чтобы "интересные" таблицы (товары/остатки/цены) шли первыми.
    dbf_files.sort(key=lambda p: (not looks_interesting(p.name), p.name))

    for dbf_path in dbf_files:
        try:
            table = DBF(str(dbf_path), encoding=ENCODING, ignore_missing_memofile=True)
        except Exception as exc:
            out_lines.append("\n  [{0}] -- ошибка открытия: {1}".format(dbf_path.name, exc))
            continue

        marker = " <-- возможно интересна" if looks_interesting(dbf_path.name) else ""
        out_lines.append("\n  [{0}] записей: {1}{2}".format(dbf_path.name, len(table), marker))
        field_descriptions = []
        for f in table.fields:
            field_descriptions.append("{0}({1}{2})".format(f.name, f.type, f.length))
        out_lines.append("    Поля: {0}".format(", ".join(field_descriptions)))

        try:
            records = iter(table)
            for i in range(SAMPLE_ROWS):
                row = next(records)
                out_lines.append("    Пример {0}: {1}".format(i + 1, dict(row)))
        except StopIteration:
            pass
        except Exception as exc:
            out_lines.append("    Ошибка чтения строк: {0}".format(exc))


def main():
    if len(sys.argv) < 2:
        print("Использование: python explore_dbf.py <путь_к_базе_1> [путь_к_базе_2 ...]")
        sys.exit(1)

    out_lines = []
    for raw_path in sys.argv[1:]:
        explore_base(Path(raw_path), out_lines)

    report = "\n".join(out_lines)
    print(report)

    report_path = Path(__file__).parent / "report.txt"
    open(str(report_path), "w", encoding="utf-8").write(report)
    print("\n\nОтчёт также сохранён в {0}".format(report_path))

    if CONFIG_PATH.exists():
        config = json.loads(open(str(CONFIG_PATH), encoding="utf-8").read())
        github_cfg = config.get("github")
        if github_cfg and github_cfg.get("token") and "ВСТАВЬ_СЮДА" not in github_cfg["token"]:
            repo_report_path = Path(github_cfg["repo_path"]) / "report.txt"
            try:
                repo_report_path.parent.mkdir(parents=True)
            except FileExistsError:
                pass
            open(str(repo_report_path), "w", encoding="utf-8").write(report)
            push_files(github_cfg, ["report.txt"], "Отчёт о структуре баз 1С (explore_dbf)")
        else:
            print("config.json найден, но github.token не заполнен — report.txt не публикуется.")
    else:
        print("config.json не найден — report.txt не публикуется в GitHub (только локально).")


if __name__ == "__main__":
    main()
