#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from storage_core import (
    add_file,
    auth_mac,
    get_stats,
    get_storage_root,
    init_storage,
    list_files,
    open_file,
    prune_objects,
    restore_file,
    verify_storage,
)

def ensure_storage_exists(storage_root: Path) -> None:
    if not storage_root.exists():
        print("[init] Storage not found, initializing...")
        init_storage(storage_root, verbose=True)


def cmd_init(args) -> None:
    storage_root = get_storage_root()
    init_storage(storage_root, verbose=True)
    print(f"[init] Done. Storage root: {storage_root}")


def cmd_add(args) -> None:
    storage_root = get_storage_root()
    ensure_storage_exists(storage_root)
    for name in args.files:
        path = Path(name)
        print(f"[add] Processing: {path}")
        try:
            entry = add_file(storage_root, path)
        except Exception as exc:  # noqa: BLE001
            print(f"[add] ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"[add] Stored hash: {entry['hash']}")
        print(f"[add] Size: {entry['size']} bytes  mtime: {entry['mtime']}")


def cmd_list(args) -> None:
    storage_root = get_storage_root()
    try:
        index = list_files(storage_root)
    except Exception as exc:  # noqa: BLE001
        print(f"[list] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    files = index.get("files", {})
    if not isinstance(files, dict):
        print("[list] ERROR: index format is invalid: 'files' must be an object.", file=sys.stderr)
        sys.exit(1)

    if not files:
        print("[list] Storage is empty.")
        return

    for original_path, versions in files.items():
        if not isinstance(versions, list) or not versions:
            print(f"[list] WARNING: invalid versions for {original_path}")
            continue

        if not args.verbose:
            latest = versions[-1]
            latest_hash = str(latest.get("hash", ""))[:12]
            size = latest.get("size", "?")
            print(f"{original_path}  (versions: {len(versions)}, latest hash: {latest_hash}..., size: {size})")
        else:
            print(f"{original_path}")
            for idx, v in enumerate(versions, start=1):
                h = v.get("hash", "?")
                size = v.get("size", "?")
                mtime = v.get("mtime", "?")
                stored_at = v.get("stored_at", "?")
                print(f"    v{idx}: hash: {h}  size: {size} bytes  stored_at: {stored_at}  mtime: {mtime}")
        print()


def cmd_verify(args) -> None:
    storage_root = get_storage_root()
    try:
        result = verify_storage(storage_root, target_paths=args.files)
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    summary = result["summary"]
    for item in result["results"]:
        status = item["status"]
        path = item["path"]
        print(f"{status:<10} {path}")
        for reason in item.get("reasons", []):
            print(f"    reason: {reason}")
        print()

    errors = summary["MISSING"] + summary["CORRUPTED"]
    total = summary["OK"] + errors
    print(f"[verify] Paths checked: {total}. OK: {summary['OK']}, "
          f"Missing: {summary['MISSING']}, Corrupted: {summary['CORRUPTED']}.")
    if result.get("index_updated"):
        print("[verify] Fixed metadata inconsistencies (saved to index).")
    if errors:
        sys.exit(1)


def cmd_restore(args) -> None:
    if not auth_mac.require_local_auth("restore file"):
        print("[restore] Authentication failed or canceled.", file=sys.stderr)
        sys.exit(1)

    storage_root = get_storage_root()
    try:
        info = restore_file(
            storage_root,
            args.source_path,
            Path(args.dest_path),
            version=args.version,
            force=args.force,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[restore] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[restore] Restored v{info['version']} of {info['restored_from']} -> {info['destination']}")


def cmd_stats(args) -> None:
    storage_root = get_storage_root()
    try:
        stats = get_stats(storage_root)
    except Exception as exc:  # noqa: BLE001
        print(f"[stats] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[stats] Source paths: {stats['source_paths']}")
    print(f"[stats] Versions total: {stats['versions_total']}")
    if stats["invalid_entries"]:
        print(f"[stats] WARNING: skipped {stats['invalid_entries']} invalid index entries.", file=sys.stderr)
    print(f"[stats] Unique objects referenced: {stats['unique_objects']}")
    print(f"[stats] Objects on disk: {stats['objects_on_disk']}")
    print(f"[stats] Objects dir size: {stats['objects_dir_size']} bytes")
    largest_hash, largest_size = stats["largest_object"]
    if largest_hash:
        print(f"[stats] Largest object: {largest_hash} ({largest_size} bytes)")
    else:
        print("[stats] Largest object: n/a")
    print(f"[stats] Average object size: {stats['avg_size']:.2f} bytes")
    print(f"[stats] Duplication ratio (versions / unique hashes): {stats['duplication_ratio']:.2f}")
    if not stats["objects_dir_exists"]:
        print("[stats] WARNING: objects directory is missing; run init or add.", file=sys.stderr)


def cmd_prune(args) -> None:
    storage_root = get_storage_root()
    try:
        result = prune_objects(storage_root)
    except Exception as exc:  # noqa: BLE001
        print(f"[prune] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[prune] Removed {result['removed']} unreferenced object(s).")
    if result["skipped_symlinks"]:
        print(f"[prune] Skipped symlinks: {result['skipped_symlinks']}", file=sys.stderr)
    if result["failed"]:
        print(f"[prune] Failures: {result['failed']}", file=sys.stderr)
        sys.exit(1)


def cmd_open(args) -> None:
    if not auth_mac.require_local_auth("open file"):
        print("[open] Authentication failed or canceled.", file=sys.stderr)
        sys.exit(1)

    storage_root = get_storage_root()
    try:
        info = open_file(
            storage_root,
            args.source_path,
            version=args.version,
            force=args.force,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[open] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[open] Restored v{info['version']} of {args.source_path}")
    print(f"[open] Temp path: {info['path']}")
    if info.get("verification") != "ok":
        print(f"[open] WARNING: verification failed: {info.get('verification_reason')}", file=sys.stderr)
    if info["launched"]:
        print("[open] Launched with default app.")
    else:
        print(f"[open] Launch failed (exit {info['returncode']}); file is available at the temp path.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simple local backup storage (macOS-first draft)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Initialize storage (if needed)")
    p_init.set_defaults(func=cmd_init)

    p_add = subparsers.add_parser("add", help="Add files to storage")
    p_add.add_argument("files", nargs="+", help="File paths to store")
    p_add.set_defaults(func=cmd_add)

    p_list = subparsers.add_parser("list", help="Show contents of storage")
    p_list.add_argument("--verbose", "-v", action="store_true", help="Show full details for every version")
    p_list.set_defaults(func=cmd_list)

    p_verify = subparsers.add_parser("verify", help="Verify stored objects integrity")
    p_verify.add_argument("files", nargs="*", help="Original file paths to verify (default: all)")
    p_verify.set_defaults(func=cmd_verify)

    p_restore = subparsers.add_parser("restore", help="Restore a file from storage")
    p_restore.add_argument("source_path", help="Original path recorded in the index")
    p_restore.add_argument("dest_path", help="Destination path to restore into")
    p_restore.add_argument("--version", type=int, help="Version number to restore (1 = oldest, default: latest)")
    p_restore.add_argument("--force", action="store_true", help="Overwrite destination if it exists")
    p_restore.set_defaults(func=cmd_restore)

    p_stats = subparsers.add_parser("stats", help="Show storage statistics")
    p_stats.set_defaults(func=cmd_stats)

    p_prune = subparsers.add_parser("prune", help="Remove unreferenced objects")
    p_prune.set_defaults(func=cmd_prune)

    p_open = subparsers.add_parser("open", help="Restore to temp and open with default app")
    p_open.add_argument("source_path", help="Original path recorded in the index")
    p_open.add_argument("--version", type=int, help="Version number to open (1 = oldest, default: latest)")
    p_open.add_argument("--force", action="store_true", help="Proceed even if verification fails")
    p_open.set_defaults(func=cmd_open)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
