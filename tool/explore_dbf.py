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


def looks_interesting(filename: str) -> bool:
    name = filename.upper()
    return any(name.startswith(h) for h in INTERESTING_HINTS)


def explore_base(base_path: Path, out_lines: list[str]) -> None:
    out_lines.append(f"\n{'=' * 80}\nБАЗА: {base_path}\n{'=' * 80}")

    dbf_files = sorted(base_path.glob("*.DBF")) + sorted(base_path.glob("*.dbf"))
    if not dbf_files:
        out_lines.append("  Не найдено ни одного .DBF файла в этой папке (может, путь не верен,"
                          " или таблицы лежат в подпапке).")
        return

    out_lines.append(f"  Найдено DBF-файлов: {len(dbf_files)}")

    # Сортируем так, чтобы "интересные" таблицы (товары/остатки/цены) шли первыми.
    dbf_files.sort(key=lambda p: (not looks_interesting(p.name), p.name))

    for dbf_path in dbf_files:
        try:
            table = DBF(str(dbf_path), encoding=ENCODING, ignore_missing_memofile=True)
        except Exception as exc:
            out_lines.append(f"\n  [{dbf_path.name}] -- ошибка открытия: {exc}")
            continue

        marker = " <-- возможно интересна" if looks_interesting(dbf_path.name) else ""
        out_lines.append(f"\n  [{dbf_path.name}] записей: {len(table)}{marker}")
        fields = ", ".join(f"{f.name}({f.type}{f.length})" for f in table.fields)
        out_lines.append(f"    Поля: {fields}")

        try:
            records = iter(table)
            for i in range(SAMPLE_ROWS):
                row = next(records)
                out_lines.append(f"    Пример {i + 1}: {dict(row)}")
        except StopIteration:
            pass
        except Exception as exc:
            out_lines.append(f"    Ошибка чтения строк: {exc}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python explore_dbf.py <путь_к_базе_1> [путь_к_базе_2 ...]")
        sys.exit(1)

    out_lines: list[str] = []
    for raw_path in sys.argv[1:]:
        explore_base(Path(raw_path), out_lines)

    report = "\n".join(out_lines)
    print(report)

    report_path = Path(__file__).parent / "report.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n\nОтчёт также сохранён в {report_path}")

    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        github_cfg = config.get("github")
        if github_cfg and github_cfg.get("token") and "ВСТАВЬ_СЮДА" not in github_cfg["token"]:
            repo_report_path = Path(github_cfg["repo_path"]) / "report.txt"
            repo_report_path.parent.mkdir(parents=True, exist_ok=True)
            repo_report_path.write_text(report, encoding="utf-8")
            push_files(github_cfg, ["report.txt"], "Отчёт о структуре баз 1С (explore_dbf)")
        else:
            print("config.json найден, но github.token не заполнен — report.txt не публикуется.")
    else:
        print("config.json не найден — report.txt не публикуется в GitHub (только локально).")


if __name__ == "__main__":
    main()
