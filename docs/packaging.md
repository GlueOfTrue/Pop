# App Packaging

Pop is packaged for Unix-like desktop systems only.

Windows builds are intentionally not produced because current behavior depends on POSIX/Unix filesystem semantics such as unlink-after-open, file modes, directory permissions, and sudo-style local authorization.

## Release Artifacts

GitHub Actions builds two artifact families:

- `Pop-linux-<arch>.tar.gz`
- `Pop-macos-<arch>.zip`

The Linux archive contains:

- `bin/pop`
- `share/applications/pop.desktop`
- `README.txt`

The macOS archive contains:

- `Pop.app`
- the bundled `pop` executable inside `Pop.app/Contents/MacOS/`
- `README.txt` in app resources

## Local Build

```bash
./scripts/build_local.sh
```

or, if build dependencies are already installed:

```bash
python3 scripts/build_app.py
```

Both commands use PyInstaller and write artifacts to `dist/`.

## Linux Security Defaults

Linux builds keep Pop as a terminal application and preserve the same storage layout as the Python source version.

Runtime behavior includes:

- storage directories are created with private permissions where Pop controls them;
- sensitive generated files are written with private file permissions;
- plaintext viewer temp directories prefer `XDG_RUNTIME_DIR` when it is owned by the current user and not accessible to group/other users;
- if `XDG_RUNTIME_DIR` is not safe, `/dev/shm` is preferred before the system temp directory;
- local authorization refuses root execution by default unless `POP_ALLOW_ROOT=1` is set.

The root guard exists because running the vault as root can create root-owned vault files and weakens the local-user authorization model.

## macOS Notes

`Pop.app` is currently an unsigned convenience wrapper around the terminal executable. It may require Gatekeeper bypass steps when downloaded outside the App Store or outside a signed release.

The terminal executable can also be run directly:

```bash
./Pop.app/Contents/MacOS/pop
```
