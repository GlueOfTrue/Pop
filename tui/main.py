from __future__ import annotations

import curses
import sys
from pathlib import Path
from typing import List

# Make sure storage_core is importable when running this file directly.
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from storage_core import (
    add_file,
    auth_mac,
    get_stats,
    get_storage_root,
    init_storage,
    list_files,
    open_file,
    prune_objects,
    verify_storage,
)


def _render_lines(stdscr, title: str, lines: List[str]) -> None:
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    stdscr.addstr(0, 0, title[: width - 1])
    for i, line in enumerate(lines, start=2):
        if i >= height:
            break
        stdscr.addstr(i, 0, line[: width - 1])
    stdscr.addstr(height - 1, 0, "Press any key to return...")
    stdscr.refresh()
    stdscr.getch()


def _require_auth(stdscr, action: str) -> bool:
    """
    Temporarily leave curses to show system auth prompt (Touch ID / password).
    """
    curses.def_prog_mode()  # save current tty state
    curses.endwin()  # restore terminal to show prompt
    ok = auth_mac.require_local_auth(action)
    curses.reset_prog_mode()  # restore curses mode
    curses.curs_set(0)
    stdscr.refresh()
    return ok


def view_files(stdscr) -> None:
    storage_root = get_storage_root()
    try:
        index = list_files(storage_root)
    except Exception as exc:  # noqa: BLE001
        _render_lines(stdscr, "Files (error)", [f"ERROR: {exc}"])
        return

    files = index.get("files", {})
    if not files:
        _render_lines(stdscr, "Files", ["No files in storage."])
        return

    lines: List[str] = []
    for original_path, versions in files.items():
        lines.append(f"{original_path}")
        if isinstance(versions, list):
            latest = versions[-1] if versions else {}
            lines.append(f"  versions: {len(versions)}  latest hash: {str(latest.get('hash', ''))[:12]}...")
        else:
            lines.append("  invalid entry")
    _render_lines(stdscr, "Files", lines)


def view_verify(stdscr) -> None:
    storage_root = get_storage_root()
    try:
        result = verify_storage(storage_root)
    except Exception as exc:  # noqa: BLE001
        _render_lines(stdscr, "Verify (error)", [f"ERROR: {exc}"])
        return

    lines: List[str] = []
    for item in result["results"]:
        lines.append(f"{item['status']:<10} {item['path']}")
        for reason in item.get("reasons", []):
            lines.append(f"    {reason}")
    summary = result["summary"]
    lines.append(
        f"Summary: OK {summary['OK']}, Missing {summary['MISSING']}, Corrupted {summary['CORRUPTED']}"
    )
    if result.get("index_updated"):
        lines.append("Index updated to fix metadata inconsistencies.")
    _render_lines(stdscr, "Verify", lines)


def view_stats(stdscr) -> None:
    storage_root = get_storage_root()
    try:
        stats = get_stats(storage_root)
    except Exception as exc:  # noqa: BLE001
        _render_lines(stdscr, "Stats (error)", [f"ERROR: {exc}"])
        return

    lines = [
        f"Source paths: {stats['source_paths']}",
        f"Versions total: {stats['versions_total']}",
        f"Unique objects: {stats['unique_objects']}",
        f"Objects on disk: {stats['objects_on_disk']}",
        f"Objects dir size: {stats['objects_dir_size']} bytes",
        f"Largest object: {stats['largest_object'][0] or 'n/a'} ({stats['largest_object'][1]} bytes)",
        f"Average object size: {stats['avg_size']:.2f} bytes",
        f"Duplication ratio: {stats['duplication_ratio']:.2f}",
    ]
    if stats["invalid_entries"]:
        lines.append(f"WARNING: invalid index entries: {stats['invalid_entries']}")
    _render_lines(stdscr, "Stats", lines)


def run_prune(stdscr) -> None:
    storage_root = get_storage_root()
    try:
        result = prune_objects(storage_root)
    except Exception as exc:  # noqa: BLE001
        _render_lines(stdscr, "Prune (error)", [f"ERROR: {exc}"])
        return

    lines = [
        f"Removed: {result['removed']}",
        f"Failed: {result['failed']}",
        f"Skipped symlinks: {result['skipped_symlinks']}",
    ]
    _render_lines(stdscr, "Prune", lines)


def _prompt(stdscr, label: str) -> str:
    curses.echo()
    stdscr.clear()
    stdscr.addstr(0, 0, label)
    stdscr.refresh()
    value = stdscr.getstr(1, 0).decode("utf-8").strip()
    curses.noecho()
    return value


def open_from_storage(stdscr) -> None:
    source = _prompt(stdscr, "Enter source path (as in index):")
    if not source:
        _render_lines(stdscr, "Open", ["Canceled."])
        return
    version_str = _prompt(stdscr, "Enter version number (blank = latest):")
    version = None
    if version_str:
        try:
            version = int(version_str)
        except ValueError:
            _render_lines(stdscr, "Open", ["ERROR: version must be an integer."])
            return

    storage_root = get_storage_root()
    if not _require_auth(stdscr, "open file"):
        _render_lines(stdscr, "Open", ["Authentication failed or canceled."])
        return

    try:
        info = open_file(storage_root, source, version=version)
    except Exception as exc:  # noqa: BLE001
        retry = _prompt(stdscr, f"{exc}\nForce open anyway? (y/N):")
        if retry.lower() != "y":
            _render_lines(stdscr, "Open", ["Canceled."])
            return
        try:
            info = open_file(storage_root, source, version=version, force=True)
        except Exception as exc2:  # noqa: BLE001
            _render_lines(stdscr, "Open (error)", [f"ERROR: {exc2}"])
            return

    status = "Launched" if info["launched"] else f"Launch failed (exit {info['returncode']})"
    lines = [
        f"Restored v{info['version']} of {source}",
        f"Temp path: {info['path']}",
        status,
    ]
    if info.get("verification") != "ok":
        lines.append(f"WARNING: verification failed: {info.get('verification_reason')}")
    _render_lines(stdscr, "Open", lines)


def add_files(stdscr) -> None:
    paths_raw = _prompt(stdscr, "Enter file paths (space/comma separated):")
    if not paths_raw:
        _render_lines(stdscr, "Add", ["Canceled."])
        return
    paths = [p for p in paths_raw.replace(",", " ").split() if p]
    if not paths:
        _render_lines(stdscr, "Add", ["No paths provided."])
        return

    storage_root = get_storage_root()
    if not storage_root.exists():
        init_storage(storage_root, verbose=False)

    lines: List[str] = []
    for p in paths:
        try:
            entry = add_file(storage_root, Path(p))
            lines.append(f"OK    {p} -> hash {entry['hash'][:12]}..., size {entry['size']}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"ERROR {p}: {exc}")

    _render_lines(stdscr, "Add", lines)


def main(stdscr) -> None:
    curses.curs_set(0)
    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, "gs-backup-storage — TUI (macOS Terminal-friendly)")
        stdscr.addstr(2, 0, "[A] Add files")
        stdscr.addstr(3, 0, "[L] List files")
        stdscr.addstr(4, 0, "[V] Verify all")
        stdscr.addstr(5, 0, "[S] Stats")
        stdscr.addstr(6, 0, "[P] Prune unreferenced objects")
        stdscr.addstr(7, 0, "[O] Open file")
        stdscr.addstr(8, 0, "[Q] Quit")
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break
        if ch in (ord("a"), ord("A")):
            add_files(stdscr)
        elif ch in (ord("l"), ord("L")):
            view_files(stdscr)
        elif ch in (ord("v"), ord("V")):
            view_verify(stdscr)
        elif ch in (ord("s"), ord("S")):
            view_stats(stdscr)
        elif ch in (ord("p"), ord("P")):
            run_prune(stdscr)
        elif ch in (ord("o"), ord("O")):
            open_from_storage(stdscr)


if __name__ == "__main__":
    curses.wrapper(main)
