"""Общая логика публикации файлов в GitHub через git + Personal Access Token."""

import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Команда {' '.join(cmd)} провалилась:\n{result.stdout}\n{result.stderr}")


def push_files(github_cfg: dict, file_paths_in_repo: list[str], commit_message: str) -> None:
    """Коммитит и пушит указанные файлы (пути относительно repo_path) в GitHub."""
    repo_path = Path(github_cfg["repo_path"])
    branch = github_cfg.get("branch", "main")
    token = github_cfg["token"]
    repo_url = github_cfg["repo_url"]

    if not repo_url.startswith("https://"):
        sys.exit("repo_url должен начинаться с https:// для push по токену")
    auth_url = repo_url.replace("https://", f"https://{token}@", 1)

    if not (repo_path / ".git").exists():
        repo_path.mkdir(parents=True, exist_ok=True)
        run(["git", "init"], repo_path)
        run(["git", "remote", "add", "origin", repo_url], repo_path)
        run(["git", "checkout", "-b", branch], repo_path)
    else:
        run(["git", "checkout", branch], repo_path)
        run(["git", "pull", auth_url, branch], repo_path)

    run(["git", "config", "user.name", github_cfg.get("commit_author_name", "1C Export Bot")], repo_path)
    run(["git", "config", "user.email", github_cfg.get("commit_author_email", "bot@example.com")], repo_path)

    run(["git", "add", *file_paths_in_repo], repo_path)

    status = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(repo_path))
    if status.returncode == 0:
        print("Нет изменений — пропускаю commit/push.")
        return

    run(["git", "commit", "-m", commit_message], repo_path)
    run(["git", "push", auth_url, branch], repo_path)
    print("Успешно запушено в GitHub.")
