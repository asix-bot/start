"""
Скачивает из репозитория GitHub файл bases_mapping.json (его туда кладёт
тот, кто сопоставляет таблицы/поля по report.txt — например, отдельная
сессия Клода) и подмешивает поля сопоставления в локальный config.json.

bases_mapping.json — список объектов вида:
[
  {
    "name": "Base1",
    "items_table": "...", "items_article_field": "...", "items_id_field": "...",
    "items_name_field": "...",
    "stock_table": "...", "stock_item_field": "...", "stock_qty_field": "...",
    "avg_cost_table": "...", "avg_cost_item_field": "...", "avg_cost_value_field": "...",
    "sale_price_table": "...", "sale_price_item_field": "...", "sale_price_value_field": "..."
  },
  ...
]

В нём НЕ должно быть github.token — секция github и поля path/suffix
в локальном config.json не трогаются, берутся только перечисленные выше
поля сопоставления (если какого-то поля нет в записи — оставляем как было).

Совместимо с Python 3.4: без f-строк, без subprocess.run (появился в 3.5),
без современных аннотаций типов.

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
    "avg_cost_table",
    "avg_cost_item_field",
    "avg_cost_value_field",
    "sale_price_table",
    "sale_price_item_field",
    "sale_price_value_field",
)


def run(cmd, cwd=None):
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        sys.exit("Команда {0} провалилась:\n{1}\n{2}".format(" ".join(cmd), stdout, stderr))


def main():
    if not CONFIG_PATH.exists():
        sys.exit("Не найден {0}. Сначала запусти setup.bat хотя бы до шага 4.".format(CONFIG_PATH))

    config = json.loads(open(str(CONFIG_PATH), encoding="utf-8").read())
    github_cfg = config["github"]

    repo_path = Path(github_cfg["repo_path"])
    repo_url = github_cfg["repo_url"]
    branch = github_cfg.get("branch", "main")
    token = github_cfg["token"]
    auth_url = repo_url.replace("https://", "https://{0}@".format(token), 1)

    if not (repo_path / ".git").exists():
        try:
            repo_path.mkdir(parents=True)
        except FileExistsError:
            pass
        run(["git", "clone", "-b", branch, auth_url, str(repo_path)])
    else:
        run(["git", "checkout", branch], repo_path)
        run(["git", "pull", auth_url, branch], repo_path)

    mapping_path = repo_path / "bases_mapping.json"
    if not mapping_path.exists():
        sys.exit(
            "В репозитории не найден bases_mapping.json (ожидался путь {0}).\n"
            "Сначала нужно, чтобы он был туда запушен с сопоставлением таблиц/полей.".format(mapping_path)
        )

    mapping_list = json.loads(open(str(mapping_path), encoding="utf-8").read())
    mapping_by_name = {}
    for entry in mapping_list:
        if "name" in entry:
            mapping_by_name[entry["name"]] = entry

    if not mapping_by_name:
        sys.exit("bases_mapping.json пуст или у записей нет поля \"name\" (Base1..Base4).")

    updated = 0
    for base_cfg in config["bases"]:
        entry = mapping_by_name.get(base_cfg["name"])
        if not entry:
            print("Предупреждение: для {0} нет записи в bases_mapping.json — пропускаю.".format(base_cfg["name"]))
            continue
        for field in MAPPING_FIELDS:
            if field in entry:
                base_cfg[field] = entry[field]
        updated += 1

    open(str(CONFIG_PATH), "w", encoding="utf-8").write(json.dumps(config, ensure_ascii=False, indent=2))
    print("Обновлено сопоставление полей для {0} баз(ы). config.json сохранён.".format(updated))


if __name__ == "__main__":
    main()
