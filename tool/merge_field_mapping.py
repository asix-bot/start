"""
Скачивает из репозитория GitHub файл bases_mapping.json (его туда кладёт
тот, кто сопоставляет таблицы/поля по report.txt — например, отдельная
сессия Клода) и подмешивает поля сопоставления в локальный config.json.

bases_mapping.json — список объектов вида:
[
  {
    "name": "Base1",
    "items_table": "...", "items_article_field": "...", "items_id_field": "...",
    "items_name_field": "...", "stock_table": "...", "stock_item_field": "...",
    "stock_qty_field": "...", "price_table": "...", "price_item_field": "...",
    "price_value_field": "..."
  },
  ...
]

В нём НЕ должно быть github.token — секция github и поля path/suffix
в локальном config.json не трогаются, берутся только перечисленные выше
поля сопоставления (если какого-то поля нет в записи — оставляем как было).

Использование:
    python merge_field_mapping.py
"""

import json
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
MAPPING_FIELDS = (
    "items_table",
    "items_article_field",
    "items_id_field",
    "items_name_field",
    "stock_table",
    "stock_item_field",
    "stock_qty_field",
    "price_table",
    "price_item_field",
    "price_value_field",
)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Команда {' '.join(cmd)} провалилась:\n{result.stdout}\n{result.stderr}")


def main() -> None:
    if not CONFIG_PATH.exists():
        sys.exit(f"Не найден {CONFIG_PATH}. Сначала запусти setup.bat хотя бы до шага 4.")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    github_cfg = config["github"]

    repo_path = Path(github_cfg["repo_path"])
    repo_url = github_cfg["repo_url"]
    branch = github_cfg.get("branch", "main")
    token = github_cfg["token"]
    auth_url = repo_url.replace("https://", f"https://{token}@", 1)

    if not (repo_path / ".git").exists():
        repo_path.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "-b", branch, auth_url, str(repo_path)])
    else:
        run(["git", "checkout", branch], repo_path)
        run(["git", "pull", auth_url, branch], repo_path)

    mapping_path = repo_path / "bases_mapping.json"
    if not mapping_path.exists():
        sys.exit(
            f"В репозитории не найден bases_mapping.json (ожидался путь {mapping_path}).\n"
            "Сначала нужно, чтобы он был туда запушен с сопоставлением таблиц/полей."
        )

    mapping_list = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping_by_name = {entry["name"]: entry for entry in mapping_list if "name" in entry}

    if not mapping_by_name:
        sys.exit("bases_mapping.json пуст или у записей нет поля \"name\" (Base1..Base4).")

    updated = 0
    for base_cfg in config["bases"]:
        entry = mapping_by_name.get(base_cfg["name"])
        if not entry:
            print(f"Предупреждение: для {base_cfg['name']} нет записи в bases_mapping.json — пропускаю.")
            continue
        for field in MAPPING_FIELDS:
            if field in entry:
                base_cfg[field] = entry[field]
        updated += 1

    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Обновлено сопоставление полей для {updated} баз(ы). config.json сохранён.")


if __name__ == "__main__":
    main()
