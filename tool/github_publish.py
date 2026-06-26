"""Общая логика публикации файлов в GitHub через git + Personal Access Token.

Совместимо с Python 3.4: без f-строк, без subprocess.run (появился в 3.5),
без современных аннотаций типов вида list[str] / X | None (этого синтаксиса
нет до Python 3.9/3.10).
"""

import subprocess
import sys
from pathlib import Path


def run(cmd, cwd):
    process = subprocess.Popen(
        cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        sys.exit("Команда {0} провалилась:\n{1}\n{2}".format(" ".join(cmd), stdout, stderr))
    return stdout


def run_ok(cmd, cwd):
    """Как run(), но возвращает True/False вместо exit при неудаче (для необязательных проверок)."""
    process = subprocess.Popen(
        cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    process.communicate()
    return process.returncode == 0


def push_files(github_cfg, file_paths_in_repo, commit_message):
    """Коммитит и пушит указанные файлы (пути относительно repo_path) в GitHub."""
    repo_path = Path(github_cfg["repo_path"])
    branch = github_cfg.get("branch", "main")
    token = github_cfg["token"]
    repo_url = github_cfg["repo_url"]

    if not repo_url.startswith("https://"):
        sys.exit("repo_url должен начинаться с https:// для push по токену")
    auth_url = repo_url.replace("https://", "https://{0}@".format(token), 1)

    if not (repo_path / ".git").exists():
        try:
            repo_path.mkdir(parents=True)
        except FileExistsError:
            pass
        run(["git", "init"], repo_path)
        run(["git", "remote", "add", "origin", repo_url], repo_path)
        run(["git", "checkout", "-b", branch], repo_path)
    else:
        run(["git", "checkout", branch], repo_path)
        run(["git", "pull", auth_url, branch], repo_path)

    run(["git", "config", "user.name", github_cfg.get("commit_author_name", "1C Export Bot")], repo_path)
    run(["git", "config", "user.email", github_cfg.get("commit_author_email", "bot@example.com")], repo_path)

    run(["git", "add"] + list(file_paths_in_repo), repo_path)

    has_changes = not run_ok(["git", "diff", "--cached", "--quiet"], repo_path)
    if not has_changes:
        print("Нет изменений — пропускаю commit/push.")
        return

    run(["git", "commit", "-m", commit_message], repo_path)
    run(["git", "push", auth_url, branch], repo_path)
    print("Успешно запушено в GitHub.")
