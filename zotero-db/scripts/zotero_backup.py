"""Online, consistent backup of Zotero's SQLite databases (WAL-aware).

Why this approach
-----------------
Zotero runs SQLite in WAL mode. Two things follow:

1. Copying zotero.sqlite alone is WRONG. Uncommitted-to-the-main-file
   transactions live in zotero.sqlite-wal. A main-file-only copy silently
   loses the most recent changes.

2. The live database is hard to open from another process on this machine:
   a plain connection reports "database is locked" because SQLite needs to
   write the -shm (shared-memory index) sidecar, which is not possible while
   Zotero owns it. Opening with ?immutable=1 bypasses the lock but reads a
   stale snapshot that excludes the WAL.

So the method is: copy the main file AND the -wal sidecar, drop the stale
-shm (SQLite rebuilds it), then open the copy normally. SQLite then replays
the WAL into the copy and checkpoints it, producing one self-consistent
database containing everything Zotero had committed.

Usage:
    python zotero_backup.py <dest_dir>
"""
import os
import shutil
import sqlite3
import sys
import time

# The main library is mandatory. The others are plugin databases whose loss
# only costs an index rebuild, but they are cheap (largest is 63 MB) so they
# get backed up too.
DATABASES = [
    "zotero.sqlite",
    "fulltext.sqlite",
    "llm-for-zotero-index.sqlite",
    "zotero-mcp-vectors.sqlite",
    "zoplicate.sqlite",
    "beaver.sqlite",
]


def backup_db(src: str, dst: str) -> tuple[bool, str]:
    """Back up one WAL-mode SQLite database: copy main + wal, then recover."""
    try:
        for p in (dst, dst + "-wal", dst + "-shm"):
            if os.path.exists(p):
                os.remove(p)

        # 1. Copy the main database file.
        shutil.copy2(src, dst)

        # 2. Copy the WAL sidecar if it exists. This carries transactions that
        #    have not yet been checkpointed into the main file.
        had_wal = False
        if os.path.exists(src + "-wal"):
            shutil.copy2(src + "-wal", dst + "-wal")
            had_wal = True

        # 3. Open the copy normally. SQLite rebuilds -shm and replays the WAL.
        conn = sqlite3.connect(dst, timeout=30)
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            # Touch a table to force the WAL replay to actually happen.
            conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()

            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            extra = ""
            try:
                n = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
                extra = f", {n} items"
            except sqlite3.Error:
                pass
        finally:
            conn.close()

        # 4. Drop the now-redundant sidecars so the backup is one clean file.
        for p in (dst + "-wal", dst + "-shm"):
            if os.path.exists(p):
                os.remove(p)

        if check != "ok":
            return False, f"integrity_check = {check}"
        size_mb = os.path.getsize(dst) / 1024 / 1024
        wal_note = " (WAL merged)" if had_wal else ""
        return True, f"ok ({tables} tables{extra}, {size_mb:.2f} MB){wal_note}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: zotero_backup.py <dest_dir>", flush=True)
        return 1

    dest = sys.argv[1]
    os.makedirs(dest, exist_ok=True)

    src_dir = r"E:\CodeProject\Zotero"
    print(f"Source: {src_dir}", flush=True)
    print(f"Dest:   {dest}\n", flush=True)

    results = []
    for name in DATABASES:
        src = os.path.join(src_dir, name)
        if not os.path.exists(src):
            results.append((name, False, "source missing"))
            print(f"  SKIP  {name} (not found)", flush=True)
            continue
        t0 = time.time()
        ok, msg = backup_db(src, os.path.join(dest, name))
        elapsed = time.time() - t0
        results.append((name, ok, msg))
        print(f"  {'OK  ' if ok else 'FAIL'}  {name}  ({msg}, {elapsed:.1f}s)", flush=True)

    manifest = os.path.join(dest, "BACKUP_INFO.txt")
    with open(manifest, "w", encoding="utf-8") as f:
        f.write("Zotero database backup\n")
        f.write(f"Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Source:  {src_dir}\n")
        f.write("Method:  main-file + WAL copy, then WAL replay/checkpoint\n")
        f.write("         (sidecars removed; each .sqlite is self-contained)\n\n")
        for name, ok, msg in results:
            f.write(f"{'OK' if ok else 'FAIL'}\t{name}\t{msg}\n")
        f.write("\nRestore steps:\n")
        f.write("  1. Close Zotero completely.\n")
        f.write("  2. Replace the matching file in the source dir with this copy.\n")
        f.write("  3. Delete the stale *.sqlite-wal and *.sqlite-shm files.\n")
        f.write("  4. Start Zotero and verify the library.\n")

    failures = [r for r in results if not r[1]]
    print(f"\nManifest: {manifest}", flush=True)
    if failures:
        print(f"FAILED: {len(failures)} database(s)", flush=True)
        return 1
    print("All databases backed up successfully.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
