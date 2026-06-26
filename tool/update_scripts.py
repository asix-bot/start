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

Совместимо с Python 3.4: без f-строк, без subprocess.run (появился в 3.5),
без современных аннотаций типов.

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
    "explore.py",
    "explore_dbf.py",
    "explore_sql.py",
    "sqlcmd_client.py",
    "check_base.py",
    "github_publish.py",
    "update_config.py",
    "merge_field_mapping.py",
    "update_scripts.py",
    "run_export.bat",
    "config.example.json",
)

# Папки целиком (например, вендоренная dbfread/, чтобы не зависеть от pip
# на старых ОС без TLS 1.2 в pip/PyPI).
SYNCED_DIRS = ("dbfread",)


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

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    github_cfg = config["github"]

    repo_url = github_cfg["repo_url"]
    branch = github_cfg.get("branch", "main")
    token = github_cfg["token"]
    auth_url = repo_url.replace("https://", "https://{0}@".format(token), 1)

    tmp_dir = tempfile.mkdtemp(prefix="1c_tool_update_")
    try:
        clone_dir = Path(tmp_dir) / "repo"
        run(["git", "clone", "--depth", "1", "-b", branch, auth_url, str(clone_dir)])

        tool_dir = clone_dir / REPO_SUBFOLDER
        if not tool_dir.exists():
            print(
                "В репозитории нет папки {0}/ — пока ничего обновлять. "
                "Скрипты туда кладут при разработке.".format(REPO_SUBFOLDER)
            )
            return

        updated = []
        for filename in SYNCED_FILES:
            remote_file = tool_dir / filename
            if not remote_file.exists():
                continue
            local_file = SCRIPT_DIR / filename
            if local_file.exists() and filecmp.cmp(str(remote_file), str(local_file), shallow=False):
                continue
            shutil.copyfile(str(remote_file), str(local_file))
            updated.append(filename)

        for dirname in SYNCED_DIRS:
            remote_dir = tool_dir / dirname
            if not remote_dir.exists():
                continue
            local_dir = SCRIPT_DIR / dirname
            for remote_file in remote_dir.glob("*.py"):
                local_file = local_dir / remote_file.name
                if local_file.exists() and filecmp.cmp(str(remote_file), str(local_file), shallow=False):
                    continue
                local_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(remote_file), str(local_file))
                updated.append("{0}/{1}".format(dirname, remote_file.name))

        if updated:
            print("Обновлены файлы: " + ", ".join(updated))
        else:
            print("Все скрипты уже актуальны, обновлений нет.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
