"""
Утилита для диагностических скриптов: перехватывает весь print()-вывод
работы скрипта, сохраняет его в файл и пушит в GitHub - чтобы результат
проверки можно было скачать из репозитория, а не делать скриншоты терминала.

Совместимо с Python 3.4: без f-строк, без современных аннотаций типов.
"""

import io
import json
import sys
from pathlib import Path

from github_publish import push_files

CONFIG_PATH = Path(__file__).parent / "config.json"


class _Tee(object):
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)

    def flush(self):
        for s in self.streams:
            s.flush()


def run_with_log(log_filename, commit_message, work_fn):
    """Запускает work_fn() (без аргументов), перехватывая весь print()-вывод
    (он всё равно показывается на экране как обычно), сохраняет полный
    вывод в log_filename рядом со скриптом и пушит в репозиторий (если
    github.token настроен в config.json)."""
    buf = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = _Tee(real_stdout, buf)
    pending_exit = None
    try:
        work_fn()
    except SystemExit as exc:
        # sys.exit("сообщение об ошибке") - частый паттерн в диагностических
        # скриптах. Сохраняем лог в любом случае, потом перевыбрасываем,
        # чтобы код возврата bat-файла остался правильным (errorlevel 1).
        pending_exit = exc
    finally:
        sys.stdout = real_stdout

    if pending_exit is not None and isinstance(pending_exit.code, str):
        # sys.exit("текст") обычно сам печатает текст в stderr при обычном
        # завершении - раз мы перехватили исключение, делаем это сами.
        # stdout уже восстановлен (мы вне Tee), поэтому пишем явно в обе
        # стороны: и на экран, и в буфер лога.
        print(pending_exit.code)
        buf.write(pending_exit.code + "\n")

    output_text = buf.getvalue()
    local_log_path = Path(__file__).parent / log_filename
    open(str(local_log_path), "w", encoding="utf-8").write(output_text)
    print("\nПолный вывод сохранён в {0}".format(local_log_path))

    pushed = False
    if CONFIG_PATH.exists():
        config = json.loads(open(str(CONFIG_PATH), encoding="utf-8-sig").read())
        github_cfg = config.get("github")
        if github_cfg and github_cfg.get("token") and "ВСТАВЬ_СЮДА" not in github_cfg.get("token", ""):
            repo_log_path = Path(github_cfg["repo_path"]) / log_filename
            try:
                repo_log_path.parent.mkdir(parents=True)
            except FileExistsError:
                pass
            # дописываем финальную строку уже в файл, который реально пушим
            final_text = open(str(local_log_path), encoding="utf-8").read()
            open(str(repo_log_path), "w", encoding="utf-8").write(final_text)
            push_files(github_cfg, [log_filename], commit_message)
            print("Результат запушен в GitHub как {0}".format(log_filename))
            pushed = True
        else:
            print("github.token не заполнен - результат не запушен в GitHub.")

    if pending_exit is not None:
        sys.exit(pending_exit.code)
    return pushed
