"""Общая логика публикации файлов в GitHub через git + Personal Access Token.

Совместимо с Python 3.4: без f-строк, без subprocess.run (появился в 3.5),
без современных аннотаций типов вида list[str] / X | None (этого синтаксиса
нет до Python 3.9/3.10).
"""

import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None):
    process = subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        sys.exit("Команда {0} провалилась:\n{1}\n{2}".format(" ".join(cmd), stdout, stderr))
    return stdout


def run_ok(cmd, cwd=None):
    """Как run(), но возвращает True/False вместо exit при неудаче (для необязательных проверок)."""
    process = subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    process.communicate()
    return process.returncode == 0


def fresh_clone(repo_path, branch, repo_url, auth_url):
    """Клонирует репозиторий "с нуля" в repo_path, сохраняя файлы, которые уже
    лежали в repo_path (новый контент, который мы хотим закоммитить) - они
    переносятся в свежий клон поверх содержимого из репозитория.

    Используется, когда локальной .git папки ещё нет, либо когда она есть,
    но её история не связана с удалённым репозиторием (например, раньше
    была создана через "git init" вместо "git clone" - тогда git pull
    откажется со словами "refusing to merge unrelated histories").
    """
    tmp_clone = repo_path.parent / (repo_path.name + "_fresh_clone_tmp")
    if tmp_clone.exists():
        shutil.rmtree(str(tmp_clone))
    run(["git", "clone", "-b", branch, auth_url, str(tmp_clone)])

    if repo_path.exists():
        for item in repo_path.iterdir():
            if item.name == ".git":
                continue
            dest = tmp_clone / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(str(dest))
                shutil.copytree(str(item), str(dest))
            else:
                shutil.copyfile(str(item), str(dest))
        shutil.rmtree(str(repo_path))

    tmp_clone.rename(repo_path)


def ensure_repo(repo_path, branch, repo_url, auth_url):
    """Готовит локальный клон repo_path к коммиту: либо переключает на нужную
    ветку и подтягивает изменения, либо (если это не получается - например,
    локальная история не связана с удалённой) пересоздаёт клон с нуля."""
    needs_fresh_clone = not (repo_path / ".git").exists()

    if not needs_fresh_clone:
        if not run_ok(["git", "checkout", branch], repo_path):
            needs_fresh_clone = True
        elif not run_ok(["git", "pull", auth_url, branch], repo_path):
            needs_fresh_clone = True

    if needs_fresh_clone:
        fresh_clone(repo_path, branch, repo_url, auth_url)


def push_files(github_cfg, file_paths_in_repo, commit_message):
    """Коммитит и пушит указанные файлы (пути относительно repo_path) в GitHub."""
    repo_path = Path(github_cfg["repo_path"])
    branch = github_cfg.get("branch", "main")
    token = github_cfg["token"]
    repo_url = github_cfg["repo_url"]

    if not repo_url.startswith("https://"):
        sys.exit("repo_url должен начинаться с https:// для push по токену")
    auth_url = repo_url.replace("https://", "https://{0}@".format(token), 1)

    ensure_repo(repo_path, branch, repo_url, auth_url)

    run(["git", "config", "user.name", github_cfg.get("commit_author_name", "1C Export Bot")], repo_path)
    run(["git", "config", "user.email", github_cfg.get("commit_author_email", "bot@example.com")], repo_path)

    run(["git", "add"] + list(file_paths_in_repo), repo_path)

    has_changes = not run_ok(["git", "diff", "--cached", "--quiet"], repo_path)
    if not has_changes:
        print("Нет изменений — пропускаю commit/push.")
        return

    run(["git", "commit", "-m", commit_message], repo_path)

    push_retries = 5
    pushed = False
    for attempt in range(push_retries):
        if run_ok(["git", "push", auth_url, branch], repo_path):
            pushed = True
            break
        print(
            "Push отклонён (скорее всего, в репозиторий в это же время пишет другой "
            "процесс) - подтягиваю изменения и пробую снова, попытка {0} из {1}...".format(
                attempt + 1, push_retries
            )
        )
        if not run_ok(["git", "pull", auth_url, branch], repo_path):
            fresh_clone(repo_path, branch, repo_url, auth_url)
            run(["git", "add"] + list(file_paths_in_repo), repo_path)
            run_ok(["git", "commit", "-m", commit_message], repo_path)

    if not pushed:
        sys.exit("Не удалось запушить в GitHub после {0} попыток.".format(push_retries))

    print("Успешно запушено в GitHub.")
