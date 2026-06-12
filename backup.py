#!/usr/bin/env python3
from __future__ import annotations

import getpass
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from storage_core import (
    add_file,
    clear_totp,
    configure_totp,
    get_metadata,
    get_stats,
    get_storage_root,
    get_totp_info,
    get_ui_language,
    init_storage,
    list_public,
    open_file,
    prune_objects,
    push_remote_mirror,
    remote_status,
    restore_file,
    set_ui_language,
    totp_is_configured,
    unlock_storage,
    verify_storage,
)
from storage_core.keystore import keystore_exists

try:
    import curses
except Exception:  # noqa: BLE001
    curses = None

try:
    import qrcode
except Exception:  # noqa: BLE001
    qrcode = None


STRINGS = {
    "ru": {
        "title": "gs-backup-storage (консоль)",
        "menu_header": "Выберите действие",
        "menu_add": "Добавить файл",
        "menu_list": "Список документов (публично)",
        "menu_meta": "Показать метаданные (защищено)",
        "menu_restore": "Восстановить файл",
        "menu_open": "Открыть файл",
        "menu_verify": "Проверить хранилище",
        "menu_stats": "Статистика",
        "menu_prune": "Очистка (prune)",
        "menu_paranoid": "Параноидальный просмотр",
        "menu_totp_status": "Статус TOTP",
        "menu_totp_setup": "Настроить/обновить TOTP",
        "menu_totp_disable": "Отключить TOTP",
        "menu_remote_status": "Статус Nextcloud mirror",
        "menu_remote_push": "Отправить mirror в Nextcloud",
        "menu_lang": "Язык интерфейса",
        "menu_quit": "Выход",
        "prompt_path": "Путь к файлу: ",
        "prompt_doc_name": "Имя документа (пусто = имя файла): ",
        "prompt_mode": "Режим (backup/secure) [backup]: ",
        "prompt_select_doc": "Номер документа: ",
        "prompt_version": "Версия (пусто = последняя): ",
        "prompt_dest": "Путь назначения (пусто = исходный): ",
        "prompt_overwrite": "Перезаписать, если существует? (y/N): ",
        "prompt_deep": "Глубокая проверка (расшифровать контент)? (y/N): ",
        "prompt_show_details": "Показать детали (нужна верификация)? (y/N): ",
        "prompt_rotate_totp": "TOTP уже настроен. Обновить секрет? (y/N): ",
        "prompt_label": "Метка/аккаунт [{default}]: ",
        "prompt_issuer": "Issuer [gs-backup]: ",
        "prompt_secret": "TOTP секрет (Base32, пусто = сгенерировать): ",
        "prompt_digits": "Цифр (6-10) [6]: ",
        "prompt_period": "Период секунд (10-120) [30]: ",
        "prompt_algo": "Алгоритм (SHA1/SHA256/SHA512) [SHA1]: ",
        "prompt_disable_totp": "Отключить TOTP? (y/N): ",
        "prompt_language": "Язык (ru/en) [{current}]: ",
        "prompt_master": "Мастер-пароль: ",
        "prompt_master_set": "Задайте мастер-пароль: ",
        "prompt_master_repeat": "Повторите мастер-пароль: ",
        "no_docs": "В хранилище нет документов.",
        "invalid_selection": "Неверный выбор.",
        "canceled": "Отменено.",
        "stored": "Сохранено {name} v{version} (enc {hash}...)",
        "restored": "Восстановлено {name} v{version} -> {dest}",
        "opened": "Открыто {name} v{version} (врем. очищено: {cleaned})",
        "opened_paranoid": (
            "Открыто {name} v{version} (opened: {opened}, unlinked: {unlinked}, "
            "temp cleaned: {cleaned})"
        ),
        "paranoid_on": "Параноидальный просмотр включён.",
        "paranoid_off": "Параноидальный просмотр выключен.",
        "totp_configured": "TOTP настроен.",
        "totp_not_configured": "TOTP не настроен.",
        "totp_disabled": "TOTP отключен.",
        "qr_unavailable": "QR недоступен. Установите пакет 'qrcode'.",
        "ok_summary": "OK {ok} | Missing {missing} | Corrupted {corrupted}",
        "language_set": "Язык установлен: {lang}",
        "closing_views": "Закрываю открытые просмотры...",
        "closed_views": "Закрыто просмотров: {closed}, ошибок: {failed}",
        "passwords_mismatch": "Пароли не совпадают.",
        "master_required": "Нужен мастер-пароль.",
        "unknown_option": "Неизвестная команда.",
        "press_any_key": "Нажмите любую клавишу...",
    },
    "en": {
        "title": "gs-backup-storage (console)",
        "menu_header": "Choose action",
        "menu_add": "Add file",
        "menu_list": "List documents (public)",
        "menu_meta": "Show metadata (protected)",
        "menu_restore": "Restore file",
        "menu_open": "Open file",
        "menu_verify": "Verify storage",
        "menu_stats": "Stats",
        "menu_prune": "Prune",
        "menu_paranoid": "Paranoid view",
        "menu_totp_status": "TOTP status",
        "menu_totp_setup": "Configure/rotate TOTP",
        "menu_totp_disable": "Disable TOTP",
        "menu_remote_status": "Remote status",
        "menu_remote_push": "Push remote mirror",
        "menu_lang": "Interface language",
        "menu_quit": "Quit",
        "prompt_path": "Path to file: ",
        "prompt_doc_name": "Document name (blank = file name): ",
        "prompt_mode": "Mode (backup/secure) [backup]: ",
        "prompt_select_doc": "Select document number: ",
        "prompt_version": "Version (blank = latest): ",
        "prompt_dest": "Destination path (blank = original): ",
        "prompt_overwrite": "Overwrite if exists? (y/N): ",
        "prompt_deep": "Deep verify (decrypt contents)? (y/N): ",
        "prompt_show_details": "Show details (requires auth)? (y/N): ",
        "prompt_rotate_totp": "TOTP already configured. Rotate secret? (y/N): ",
        "prompt_label": "Label/account [{default}]: ",
        "prompt_issuer": "Issuer [gs-backup]: ",
        "prompt_secret": "TOTP secret (Base32, blank = generate): ",
        "prompt_digits": "Digits (6-10) [6]: ",
        "prompt_period": "Period seconds (10-120) [30]: ",
        "prompt_algo": "Algorithm (SHA1/SHA256/SHA512) [SHA1]: ",
        "prompt_disable_totp": "Disable TOTP? (y/N): ",
        "prompt_language": "Language (ru/en) [{current}]: ",
        "prompt_master": "Master password: ",
        "prompt_master_set": "Set master password: ",
        "prompt_master_repeat": "Repeat master password: ",
        "no_docs": "No documents in storage.",
        "invalid_selection": "Invalid selection.",
        "canceled": "Canceled.",
        "stored": "Stored {name} v{version} (enc {hash}...)",
        "restored": "Restored {name} v{version} -> {dest}",
        "opened": "Opened {name} v{version} (temp cleaned: {cleaned})",
        "opened_paranoid": (
            "Opened {name} v{version} (opened: {opened}, unlinked: {unlinked}, "
            "temp cleaned: {cleaned})"
        ),
        "paranoid_on": "Paranoid view is now ON.",
        "paranoid_off": "Paranoid view is now OFF.",
        "totp_configured": "TOTP configured.",
        "totp_not_configured": "TOTP not configured.",
        "totp_disabled": "TOTP disabled.",
        "qr_unavailable": "QR render unavailable. Install package 'qrcode'.",
        "ok_summary": "OK {ok} | Missing {missing} | Corrupted {corrupted}",
        "language_set": "Language set: {lang}",
        "closing_views": "Closing open views...",
        "closed_views": "Closed views: {closed}, failed: {failed}",
        "passwords_mismatch": "Passwords do not match.",
        "master_required": "Master password required.",
        "unknown_option": "Unknown option.",
        "press_any_key": "Press any key...",
    },
}


def tr(lang: str, key: str) -> str:
    lang_map = STRINGS.get(lang, STRINGS["ru"])
    return lang_map.get(key, STRINGS["en"].get(key, key))

def _prompt(text: str) -> str:
    return input(text).strip()


def _prompt_int(text: str) -> int | None:
    raw = input(text).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _ensure_storage(master_password: str) -> None:
    root = get_storage_root()
    if not root.exists():
        init_storage(root, master_password=master_password, verbose=True)
    else:
        init_storage(root, master_password=master_password, verbose=False)


def _render_qr_ascii(data: str) -> str | None:
    if qrcode is None:
        return None
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    black = "##"
    white = "  "
    lines = ["".join(black if cell else white for cell in row) for row in matrix]
    return "\n".join(lines)


def _pid_start_time(pid: int) -> str | None:
    proc = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value if value else None


def _terminate_pids(entries: list[dict], timeout: float = 2.0) -> tuple[int, int]:
    alive: list[int] = []
    failed = 0
    for entry in entries:
        pid = entry.get("pid")
        if not isinstance(pid, int):
            continue
        expected = entry.get("start")
        current = _pid_start_time(pid)
        if expected and current and expected != current:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            alive.append(pid)
        except OSError:
            failed += 1

    if alive:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and alive:
            still_alive = []
            for pid in alive:
                try:
                    os.kill(pid, 0)
                    still_alive.append(pid)
                except OSError:
                    continue
            if not still_alive:
                alive = []
                break
            time.sleep(0.2)
            alive = still_alive

    if alive:
        for pid in alive:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                failed += 1
    closed = len(entries) - failed
    return max(closed, 0), failed


def _close_open_views(open_views: list[dict], lang: str) -> None:
    if not open_views:
        return
    print(tr(lang, "closing_views"))
    entries: list[dict] = []
    for view in open_views:
        pids = view.get("viewer_pids", [])
        if isinstance(pids, list):
            entries.extend([p for p in pids if isinstance(p, dict)])
    closed, failed = _terminate_pids(entries)
    for view in open_views:
        tempdir = view.get("tempdir")
        if tempdir:
            try:
                shutil.rmtree(tempdir, ignore_errors=True)
            except OSError:
                pass
    print(tr(lang, "closed_views").format(closed=closed, failed=failed))


def _select_doc(docs: dict, lang: str) -> str | None:
    if not docs:
        print(tr(lang, "no_docs"))
        return None
    names = []
    for doc_id, info in docs.items():
        name = info.get("name") or doc_id
        versions = info.get("versions", [])
        names.append((doc_id, name, len(versions)))

    for idx, (_doc_id, name, count) in enumerate(names, start=1):
        print(f"{idx}) {name} (versions: {count})")

    choice = _prompt_int(tr(lang, "prompt_select_doc"))
    if choice is None or choice < 1 or choice > len(names):
        print(tr(lang, "invalid_selection"))
        return None
    return names[choice - 1][1]


def _run_plain(master_key: bytes, lang: str) -> None:
    paranoid_view = False
    open_views: list[dict] = []

    while True:
        print(f"\n{tr(lang, 'menu_header')}:")
        print("1) " + tr(lang, "menu_add"))
        print("2) " + tr(lang, "menu_list"))
        print("3) " + tr(lang, "menu_meta"))
        print("4) " + tr(lang, "menu_restore"))
        print("5) " + tr(lang, "menu_open"))
        print("6) " + tr(lang, "menu_verify"))
        print("7) " + tr(lang, "menu_stats"))
        print("8) " + tr(lang, "menu_prune"))
        print(
            "9) "
            + tr(lang, "menu_paranoid")
            + f" ({'ON' if paranoid_view else 'OFF'})"
        )
        print("10) " + tr(lang, "menu_totp_status"))
        print("11) " + tr(lang, "menu_totp_setup"))
        print("12) " + tr(lang, "menu_totp_disable"))
        print("13) " + tr(lang, "menu_remote_status"))
        print("14) " + tr(lang, "menu_remote_push"))
        print("15) " + tr(lang, "menu_lang"))
        print("0) " + tr(lang, "menu_quit"))

        choice = _prompt(">> ")
        if choice == "1":
            path = _prompt(tr(lang, "prompt_path"))
            if not path:
                print(tr(lang, "canceled"))
                continue
            name = _prompt(tr(lang, "prompt_doc_name"))
            mode = _prompt(tr(lang, "prompt_mode")) or "backup"
            try:
                info = add_file(get_storage_root(), master_key, Path(path), doc_name=name or None, mode=mode)
                print(tr(lang, "stored").format(
                    name=info["name"],
                    version=info["version"],
                    hash=info["content_enc_hash"][:12],
                ))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "2":
            try:
                catalog = list_public(get_storage_root())
                docs = catalog.get("docs", {})
                if not docs:
                    print(tr(lang, "no_docs"))
                    continue
                for doc_id, info in docs.items():
                    name = info.get("name") or doc_id
                    versions = info.get("versions", [])
                    print(f"{name} (versions: {len(versions)})")
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "3":
            try:
                catalog = list_public(get_storage_root())
                docs = catalog.get("docs", {})
                name = _select_doc(docs, lang)
                if not name:
                    continue
                version = _prompt_int(tr(lang, "prompt_version"))
                meta = get_metadata(get_storage_root(), master_key, name, version=version)
                print(json.dumps(meta, indent=2, ensure_ascii=True))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "4":
            try:
                catalog = list_public(get_storage_root())
                docs = catalog.get("docs", {})
                name = _select_doc(docs, lang)
                if not name:
                    continue
                version = _prompt_int(tr(lang, "prompt_version"))
                dest = _prompt(tr(lang, "prompt_dest"))
                dest_path = Path(dest) if dest else None
                force = _prompt(tr(lang, "prompt_overwrite")).lower() == "y"
                info = restore_file(
                    get_storage_root(),
                    master_key,
                    name,
                    dest_path,
                    version=version,
                    force=force,
                )
                print(tr(lang, "restored").format(
                    name=info["doc"],
                    version=info["version"],
                    dest=info["destination"],
                ))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "5":
            try:
                catalog = list_public(get_storage_root())
                docs = catalog.get("docs", {})
                name = _select_doc(docs, lang)
                if not name:
                    continue
                version = _prompt_int(tr(lang, "prompt_version"))
                info = open_file(
                    get_storage_root(),
                    master_key,
                    name,
                    version=version,
                    paranoid=paranoid_view,
                )
                if info.get("viewer_pids"):
                    open_views.append(info)
                if paranoid_view:
                    print(tr(lang, "opened_paranoid").format(
                        name=info["doc"],
                        version=info["version"],
                        opened=info["opened"],
                        unlinked=info["unlinked"],
                        cleaned=info["cleaned"],
                    ))
                else:
                    print(tr(lang, "opened").format(
                        name=info["doc"],
                        version=info["version"],
                        cleaned=info["cleaned"],
                    ))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "6":
            try:
                deep = _prompt(tr(lang, "prompt_deep")).lower() == "y"
                result = verify_storage(get_storage_root(), master_key, deep=deep)
                summary = result["summary"]
                print(tr(lang, "ok_summary").format(
                    ok=summary["OK"],
                    missing=summary["MISSING"],
                    corrupted=summary["CORRUPTED"],
                ))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "7":
            try:
                stats = get_stats(get_storage_root(), master_key)
                print(json.dumps(stats, indent=2, ensure_ascii=True))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "8":
            try:
                result = prune_objects(get_storage_root(), master_key)
                msg = (
                    f"Removed {result['removed']} | Failed {result['failed']} "
                    f"| Skipped {result['skipped_symlinks']}"
                )
                if "versions_removed" in result:
                    msg += (
                        f" | Versions removed {result['versions_removed']} "
                        f"| Docs removed {result['docs_removed']} "
                        f"| Versions repaired {result['versions_repaired']} "
                        f"| Versions kept/problem {result.get('versions_kept_problem', 0)}"
                    )
                if "ecc_removed" in result:
                    msg += f" | ECC removed {result['ecc_removed']}"
                print(msg)
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "9":
            paranoid_view = not paranoid_view
            print(tr(lang, "paranoid_on" if paranoid_view else "paranoid_off"))
        elif choice == "10":
            try:
                if not totp_is_configured(get_storage_root()):
                    print(tr(lang, "totp_not_configured"))
                    continue
                show = _prompt(tr(lang, "prompt_show_details")).lower() == "y"
                if not show:
                    print(tr(lang, "totp_configured"))
                    continue
                info = get_totp_info(get_storage_root(), master_key)
                print(json.dumps(info, indent=2, ensure_ascii=True))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "11":
            try:
                if totp_is_configured(get_storage_root()):
                    confirm = _prompt(tr(lang, "prompt_rotate_totp")).lower() == "y"
                    if not confirm:
                        print(tr(lang, "canceled"))
                        continue
                default_label = platform.node() or "gs-backup"
                label = _prompt(tr(lang, "prompt_label").format(default=default_label)) or default_label
                issuer = _prompt(tr(lang, "prompt_issuer")) or "gs-backup"
                secret = getpass.getpass(tr(lang, "prompt_secret")).strip()
                digits = _prompt_int(tr(lang, "prompt_digits")) or 6
                period = _prompt_int(tr(lang, "prompt_period")) or 30
                algorithm = _prompt(tr(lang, "prompt_algo")) or "SHA1"
                info = configure_totp(
                    get_storage_root(),
                    master_key,
                    secret,
                    label,
                    issuer=issuer,
                    digits=digits,
                    period=period,
                    algorithm=algorithm,
                )
                print(tr(lang, "totp_configured"))
                print(f"Secret (Base32): {info['secret_b32']}")
                print(f"otpauth URI: {info['otpauth_uri']}")
                qr = _render_qr_ascii(info["otpauth_uri"])
                if qr:
                    print("\nQR:")
                    print(qr)
                else:
                    print(tr(lang, "qr_unavailable"))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "12":
            try:
                if not totp_is_configured(get_storage_root()):
                    print(tr(lang, "totp_not_configured"))
                    continue
                confirm = _prompt(tr(lang, "prompt_disable_totp")).lower() == "y"
                if not confirm:
                    print(tr(lang, "canceled"))
                    continue
                clear_totp(get_storage_root(), master_key)
                print(tr(lang, "totp_disabled"))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "13":
            try:
                status = remote_status(get_storage_root())
                print(json.dumps(status, indent=2, ensure_ascii=True))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "14":
            try:
                result = push_remote_mirror(get_storage_root(), master_key)
                print(json.dumps(result, indent=2, ensure_ascii=True))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "15":
            try:
                current = lang
                raw = _prompt(tr(lang, "prompt_language").format(current=current))
                if not raw:
                    print(tr(lang, "canceled"))
                    continue
                lang = set_ui_language(get_storage_root(), raw)
                print(tr(lang, "language_set").format(lang=lang))
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
        elif choice == "0":
            _close_open_views(open_views, lang)
            break
        else:
            print(tr(lang, "unknown_option"))


def _run_tui(master_key: bytes, lang: str) -> None:
    if curses is None or not sys.stdin.isatty() or not sys.stdout.isatty():
        _run_plain(master_key, lang)
        return

    def _tui(stdscr) -> None:
        nonlocal lang
        paranoid_view = False
        open_views: list[dict] = []

        curses.curs_set(0)
        stdscr.keypad(True)

        def _prompt_tui(prompt: str, secret: bool = False) -> str:
            h, w = stdscr.getmaxyx()
            stdscr.move(h - 2, 0)
            stdscr.clrtoeol()
            stdscr.addnstr(h - 2, 0, prompt, w - 1)
            stdscr.refresh()
            if secret:
                curses.noecho()
            else:
                curses.echo()
            try:
                raw = stdscr.getstr(h - 2, min(len(prompt), w - 2))
            finally:
                curses.noecho()
            stdscr.move(h - 2, 0)
            stdscr.clrtoeol()
            return raw.decode("utf-8").strip()

        def _prompt_int_tui(prompt: str) -> int | None:
            raw = _prompt_tui(prompt)
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        def _message_tui(text: str) -> None:
            lines = text.splitlines() or [""]
            h, w = stdscr.getmaxyx()
            stdscr.clear()
            for idx, line in enumerate(lines[: h - 2]):
                stdscr.addnstr(idx, 0, line, w - 1)
            stdscr.addnstr(h - 1, 0, tr(lang, "press_any_key"), w - 1)
            stdscr.refresh()
            stdscr.getch()

        def _text_view(text: str, title: str = "") -> None:
            lines = text.splitlines() or [""]
            pos = 0
            while True:
                h, w = stdscr.getmaxyx()
                stdscr.clear()
                if title:
                    stdscr.addnstr(0, 0, title, w - 1, curses.A_BOLD)
                view_height = h - 2
                for i in range(view_height):
                    idx = pos + i
                    if idx >= len(lines):
                        break
                    stdscr.addnstr(1 + i, 0, lines[idx], w - 1)
                stdscr.addnstr(h - 1, 0, "Up/Down PgUp/PgDn | Enter/q=back", w - 1)
                stdscr.refresh()
                key = stdscr.getch()
                if key in (ord("q"), 27, 10, 13):
                    break
                if key in (curses.KEY_UP, ord("k")):
                    pos = max(0, pos - 1)
                elif key in (curses.KEY_DOWN, ord("j")):
                    pos = min(max(len(lines) - 1, 0), pos + 1)
                elif key == curses.KEY_NPAGE:
                    pos = min(max(len(lines) - 1, 0), pos + view_height)
                elif key == curses.KEY_PPAGE:
                    pos = max(0, pos - view_height)

        def _choose_from_list(items: list[tuple[str, str]], title: str) -> str | None:
            if not items:
                _message_tui(tr(lang, "no_docs"))
                return None
            idx = 0
            while True:
                h, w = stdscr.getmaxyx()
                stdscr.clear()
                stdscr.addnstr(0, 0, title, w - 1, curses.A_BOLD)
                view_height = h - 2
                start = max(0, idx - view_height // 2)
                end = min(len(items), start + view_height)
                if end - start < view_height:
                    start = max(0, end - view_height)
                for row, item_idx in enumerate(range(start, end), start=1):
                    label = items[item_idx][0]
                    attr = curses.A_REVERSE if item_idx == idx else curses.A_NORMAL
                    stdscr.addnstr(row, 2, label, w - 4, attr)
                stdscr.addnstr(h - 1, 0, "↑↓ Enter | q", w - 1)
                stdscr.refresh()
                key = stdscr.getch()
                if key in (ord("q"), 27):
                    return None
                if key in (curses.KEY_UP, ord("k")):
                    idx = max(0, idx - 1)
                elif key in (curses.KEY_DOWN, ord("j")):
                    idx = min(len(items) - 1, idx + 1)
                elif key in (curses.KEY_ENTER, 10, 13):
                    return items[idx][1]

        def _select_doc_tui(docs: dict) -> str | None:
            items: list[tuple[str, str]] = []
            for doc_id, info in docs.items():
                name = info.get("name") or doc_id
                versions = info.get("versions", [])
                label = f"{name} (versions: {len(versions)})"
                items.append((label, name))
            return _choose_from_list(items, tr(lang, "menu_list"))

        def _close_views_tui() -> None:
            if not open_views:
                return
            entries: list[dict] = []
            for view in open_views:
                pids = view.get("viewer_pids", [])
                if isinstance(pids, list):
                    entries.extend([p for p in pids if isinstance(p, dict)])
            closed, failed = _terminate_pids(entries)
            for view in open_views:
                tempdir = view.get("tempdir")
                if tempdir:
                    try:
                        shutil.rmtree(tempdir, ignore_errors=True)
                    except OSError:
                        pass
            _message_tui(tr(lang, "closed_views").format(closed=closed, failed=failed))

        menu = [
            "menu_add",
            "menu_list",
            "menu_meta",
            "menu_restore",
            "menu_open",
            "menu_verify",
            "menu_stats",
            "menu_prune",
            "menu_paranoid",
            "menu_totp_status",
            "menu_totp_setup",
            "menu_totp_disable",
            "menu_remote_status",
            "menu_remote_push",
            "menu_lang",
            "menu_quit",
        ]
        idx = 0

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()
            stdscr.addnstr(0, 0, tr(lang, "title"), w - 1, curses.A_BOLD)
            for i, key in enumerate(menu):
                label = tr(lang, key)
                if key == "menu_paranoid":
                    label = f"{label}: {'ON' if paranoid_view else 'OFF'}"
                if key == "menu_lang":
                    label = f"{label}: {lang.upper()}"
                attr = curses.A_REVERSE if i == idx else curses.A_NORMAL
                stdscr.addnstr(2 + i, 2, label, w - 4, attr)
            stdscr.addnstr(h - 1, 0, "↑↓ Enter | q", w - 1)
            stdscr.refresh()

            key = stdscr.getch()
            if key in (ord("q"), 27):
                _close_views_tui()
                break
            if key in (curses.KEY_UP, ord("k")):
                idx = (idx - 1) % len(menu)
                continue
            if key in (curses.KEY_DOWN, ord("j")):
                idx = (idx + 1) % len(menu)
                continue
            if key not in (curses.KEY_ENTER, 10, 13):
                continue

            action = menu[idx]
            try:
                if action == "menu_add":
                    path = _prompt_tui(tr(lang, "prompt_path"))
                    if not path:
                        _message_tui(tr(lang, "canceled"))
                        continue
                    name = _prompt_tui(tr(lang, "prompt_doc_name"))
                    mode = _prompt_tui(tr(lang, "prompt_mode")) or "backup"
                    info = add_file(get_storage_root(), master_key, Path(path), doc_name=name or None, mode=mode)
                    _message_tui(tr(lang, "stored").format(
                        name=info["name"],
                        version=info["version"],
                        hash=info["content_enc_hash"][:12],
                    ))
                elif action == "menu_list":
                    catalog = list_public(get_storage_root())
                    docs = catalog.get("docs", {})
                    if not docs:
                        _message_tui(tr(lang, "no_docs"))
                        continue
                    lines = []
                    for doc_id, info in docs.items():
                        name = info.get("name") or doc_id
                        versions = info.get("versions", [])
                        lines.append(f"{name} (versions: {len(versions)})")
                    _text_view("\n".join(lines), tr(lang, "menu_list"))
                elif action == "menu_meta":
                    catalog = list_public(get_storage_root())
                    docs = catalog.get("docs", {})
                    name = _select_doc_tui(docs)
                    if not name:
                        continue
                    version = _prompt_int_tui(tr(lang, "prompt_version"))
                    meta = get_metadata(get_storage_root(), master_key, name, version=version)
                    _text_view(json.dumps(meta, indent=2, ensure_ascii=True), tr(lang, "menu_meta"))
                elif action == "menu_restore":
                    catalog = list_public(get_storage_root())
                    docs = catalog.get("docs", {})
                    name = _select_doc_tui(docs)
                    if not name:
                        continue
                    version = _prompt_int_tui(tr(lang, "prompt_version"))
                    dest = _prompt_tui(tr(lang, "prompt_dest"))
                    dest_path = Path(dest) if dest else None
                    force = _prompt_tui(tr(lang, "prompt_overwrite")).lower() == "y"
                    info = restore_file(
                        get_storage_root(),
                        master_key,
                        name,
                        dest_path,
                        version=version,
                        force=force,
                    )
                    _message_tui(tr(lang, "restored").format(
                        name=info["doc"],
                        version=info["version"],
                        dest=info["destination"],
                    ))
                elif action == "menu_open":
                    catalog = list_public(get_storage_root())
                    docs = catalog.get("docs", {})
                    name = _select_doc_tui(docs)
                    if not name:
                        continue
                    version = _prompt_int_tui(tr(lang, "prompt_version"))
                    info = open_file(
                        get_storage_root(),
                        master_key,
                        name,
                        version=version,
                        paranoid=paranoid_view,
                    )
                    if info.get("viewer_pids"):
                        open_views.append(info)
                    if paranoid_view:
                        _message_tui(tr(lang, "opened_paranoid").format(
                            name=info["doc"],
                            version=info["version"],
                            opened=info["opened"],
                            unlinked=info["unlinked"],
                            cleaned=info["cleaned"],
                        ))
                    else:
                        _message_tui(tr(lang, "opened").format(
                            name=info["doc"],
                            version=info["version"],
                            cleaned=info["cleaned"],
                        ))
                elif action == "menu_verify":
                    deep = _prompt_tui(tr(lang, "prompt_deep")).lower() == "y"
                    result = verify_storage(get_storage_root(), master_key, deep=deep)
                    summary = result["summary"]
                    _message_tui(tr(lang, "ok_summary").format(
                        ok=summary["OK"],
                        missing=summary["MISSING"],
                        corrupted=summary["CORRUPTED"],
                    ))
                elif action == "menu_stats":
                    stats = get_stats(get_storage_root(), master_key)
                    _text_view(json.dumps(stats, indent=2, ensure_ascii=True), tr(lang, "menu_stats"))
                elif action == "menu_prune":
                    result = prune_objects(get_storage_root(), master_key)
                    msg = (
                        f"Removed {result['removed']} | Failed {result['failed']} "
                        f"| Skipped {result['skipped_symlinks']}"
                    )
                    if "versions_removed" in result:
                        msg += (
                            f" | Versions removed {result['versions_removed']} "
                            f"| Docs removed {result['docs_removed']} "
                            f"| Versions repaired {result['versions_repaired']} "
                            f"| Versions kept/problem {result.get('versions_kept_problem', 0)}"
                        )
                    if "ecc_removed" in result:
                        msg += f" | ECC removed {result['ecc_removed']}"
                    _message_tui(msg)
                elif action == "menu_paranoid":
                    paranoid_view = not paranoid_view
                    _message_tui(tr(lang, "paranoid_on" if paranoid_view else "paranoid_off"))
                elif action == "menu_totp_status":
                    if not totp_is_configured(get_storage_root()):
                        _message_tui(tr(lang, "totp_not_configured"))
                        continue
                    info = get_totp_info(get_storage_root(), master_key)
                    _text_view(json.dumps(info, indent=2, ensure_ascii=True), tr(lang, "menu_totp_status"))
                elif action == "menu_totp_setup":
                    if totp_is_configured(get_storage_root()):
                        confirm = _prompt_tui(tr(lang, "prompt_rotate_totp")).lower() == "y"
                        if not confirm:
                            _message_tui(tr(lang, "canceled"))
                            continue
                    default_label = platform.node() or "gs-backup"
                    label = _prompt_tui(tr(lang, "prompt_label").format(default=default_label)) or default_label
                    issuer = _prompt_tui(tr(lang, "prompt_issuer")) or "gs-backup"
                    secret = _prompt_tui(tr(lang, "prompt_secret"), secret=True)
                    digits = _prompt_int_tui(tr(lang, "prompt_digits")) or 6
                    period = _prompt_int_tui(tr(lang, "prompt_period")) or 30
                    algorithm = _prompt_tui(tr(lang, "prompt_algo")) or "SHA1"
                    info = configure_totp(
                        get_storage_root(),
                        master_key,
                        secret,
                        label,
                        issuer=issuer,
                        digits=digits,
                        period=period,
                        algorithm=algorithm,
                    )
                    payload = [
                        tr(lang, "totp_configured"),
                        f"Secret (Base32): {info['secret_b32']}",
                        f"otpauth URI: {info['otpauth_uri']}",
                    ]
                    qr = _render_qr_ascii(info["otpauth_uri"])
                    if qr:
                        payload.append("QR:")
                        payload.append(qr)
                    else:
                        payload.append(tr(lang, "qr_unavailable"))
                    _text_view("\n".join(payload), tr(lang, "menu_totp_setup"))
                elif action == "menu_totp_disable":
                    if not totp_is_configured(get_storage_root()):
                        _message_tui(tr(lang, "totp_not_configured"))
                        continue
                    confirm = _prompt_tui(tr(lang, "prompt_disable_totp")).lower() == "y"
                    if not confirm:
                        _message_tui(tr(lang, "canceled"))
                        continue
                    clear_totp(get_storage_root(), master_key)
                    _message_tui(tr(lang, "totp_disabled"))
                elif action == "menu_remote_status":
                    status = remote_status(get_storage_root())
                    _text_view(
                        json.dumps(status, indent=2, ensure_ascii=True),
                        tr(lang, "menu_remote_status"),
                    )
                elif action == "menu_remote_push":
                    result = push_remote_mirror(get_storage_root(), master_key)
                    _text_view(
                        json.dumps(result, indent=2, ensure_ascii=True),
                        tr(lang, "menu_remote_push"),
                    )
                elif action == "menu_lang":
                    current = lang
                    raw = _prompt_tui(tr(lang, "prompt_language").format(current=current))
                    if not raw:
                        _message_tui(tr(lang, "canceled"))
                        continue
                    lang = set_ui_language(get_storage_root(), raw)
                    _message_tui(tr(lang, "language_set").format(lang=lang))
                elif action == "menu_quit":
                    _close_views_tui()
                    break
            except Exception as exc:  # noqa: BLE001
                _message_tui(f"ERROR: {exc}")

    curses.wrapper(_tui)


def main() -> None:
    root = get_storage_root()
    lang = get_ui_language(root)
    print(tr(lang, "title"))
    if keystore_exists(root):
        master_password = getpass.getpass(tr(lang, "prompt_master"))
    else:
        master_password = getpass.getpass(tr(lang, "prompt_master_set"))
        confirm = getpass.getpass(tr(lang, "prompt_master_repeat"))
        if master_password != confirm:
            print(tr(lang, "passwords_mismatch"))
            sys.exit(1)
    if not master_password:
        print(tr(lang, "master_required"))
        sys.exit(1)

    try:
        _ensure_storage(master_password)
        master_key = unlock_storage(root, master_password)
    except Exception as exc:  # noqa: BLE001
        print(f"Init/unlock error: {exc}", file=sys.stderr)
        sys.exit(1)

    _run_tui(master_key, lang)


if __name__ == "__main__":
    main()
