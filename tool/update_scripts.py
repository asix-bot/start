"""
Подтягивает свежие версии скриптов из репозитория GitHub (папка tool/)
и перезаписывает ими локальные файлы рядом с этим скриптом.

Так разработка ведётся централизованно: при изменении скриптов их кладут
в репозиторий (в папку tool/), а удалённая машина сама подтягивает
обновления — при старте и по расписанию (см. run_export.bat и
schtasks в setup.bat), без необходимости руками копировать файлы.

config.json и .gitignore НЕ синхронизируются — это локальные настройки
конкретной машины (пути к базам, суффиксы, токен) и не должны
перезатираться.

Использование:
    python update_scripts.py
"""

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
REPO_SUBFOLDER = "tool"

SYNCED_FILES = (
    "main.py",
    "explore_dbf.py",
    "github_publish.py",
    "update_config.py",
    "merge_field_mapping.py",
    "update_scripts.py",
    "run_export.bat",
    "config.example.json",
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

    repo_url = github_cfg["repo_url"]
    branch = github_cfg.get("branch", "main")
    token = github_cfg["token"]
    auth_url = repo_url.replace("https://", f"https://{token}@", 1)

    with tempfile.TemporaryDirectory(prefix="1c_tool_update_") as tmp_dir:
        clone_dir = Path(tmp_dir) / "repo"
        run(["git", "clone", "--depth", "1", "-b", branch, auth_url, str(clone_dir)])

        tool_dir = clone_dir / REPO_SUBFOLDER
        if not tool_dir.exists():
            print(
                f"В репозитории нет папки {REPO_SUBFOLDER}/ — пока ничего обновлять. "
                "Скрипты туда кладут при разработке."
            )
            return

        updated = []
        for filename in SYNCED_FILES:
            remote_file = tool_dir / filename
            if not remote_file.exists():
                continue
            local_file = SCRIPT_DIR / filename
            if local_file.exists() and filecmp.cmp(remote_file, local_file, shallow=False):
                continue
            shutil.copyfile(remote_file, local_file)
            updated.append(filename)

        if updated:
            print("Обновлены файлы: " + ", ".join(updated))
        else:
            print("Все скрипты уже актуальны, обновлений нет.")


if __name__ == "__main__":
    main()
