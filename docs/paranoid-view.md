# Paranoid View

Paranoid view is an experimental open flow for reducing the lifetime of a named plaintext file on disk.

Normal restore writes plaintext to a destination path. Normal open decrypts a version to a temporary file and launches an external viewer. Paranoid view also decrypts to a temporary file, but after launching the viewer it tries to detect that the viewer opened the file and then unlinks the plaintext path.

On POSIX systems, a process that already opened a file may keep accessing that file through its file descriptor after the path is unlinked. This is the behavior paranoid view relies on when it works.

What paranoid view can help with:

- Shorten the time a named plaintext temp file exists in the filesystem.
- Reduce accidental discovery of the temp file by simple directory browsing.
- Clean the temporary directory when possible.

What paranoid view does not stop:

- The viewer reading or copying plaintext.
- Viewer caches, thumbnails, recent-file databases, autosave files, or indexing.
- OS swap, crash dumps, screenshots, screen recording, or clipboard leaks.
- Malware running on the client.
- A compromised operating system or Python runtime.

Use paranoid view only on trusted machines. Treat it as a best-effort convenience, not as a complete anti-forensics tool.
