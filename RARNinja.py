#!/usr/bin/env python3
"""RARNinja - fast multi-core RAR password dictionary attack (macOS/Linux/Windows).

Rewritten for native operation and full CPU utilisation:
  * Auto-detects a RAR backend (unrar / 7zz / 7z), preferring ./bin/unrar.
  * Tests each candidate WITHOUT extracting (unrar 't'), so only the winning
    password triggers a real extraction. Far less disk I/O than the original.
  * True parallelism via a process pool sized to every core, with a shared
    early-stop event so all workers halt the instant one finds the password.
  * Streams the wordlist (no loading the whole file into RAM).
  * Scriptable:  rarninja.py <archive.rar> <wordlist.txt>  (also interactive).

Only the standard library is required.

ponytail: the ceiling here is one backend subprocess per guess (a few hundred to
a few thousand tries/sec). For orders-of-magnitude more, extract the hash with
`rar2john` and run John the Ripper / hashcat on the CPU/GPU. This tool stays
dependency-free and Good Enough for dictionary attacks.
"""

import argparse
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time

# When frozen by PyInstaller, bundled files live under sys._MEIPASS.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
IS_TTY = sys.stdout.isatty()


def _c(text, code):
    return f"\033[{code}m{text}\033[0m" if IS_TTY else text


BANNER = _c(r"""
   ██▀███   ▄▄▄       ██▀███   ███▄    █  ██▓ ███▄    █  ▄▄▄██▀▀▀▄▄▄
  ▓██ ▒ ██▒▒████▄    ▓██ ▒ ██▒ ██ ▀█   █ ▓██▒ ██ ▀█   █    ▒██  ▒████▄
  ▓██ ░▄█ ▒▒██  ▀█▄  ▓██ ░▄█ ▒▓██  ▀█ ██▒▒██▒▓██  ▀█ ██▒   ░██  ▒██  ▀█▄
  ▒██▀▀█▄  ░██▄▄▄▄██ ▒██▀▀█▄  ▓██▒  ▐▌██▒░██░▓██▒  ▐▌██▒▓██▄██▓ ░██▄▄▄▄██
  ░██▓ ▒██▒ ▓█   ▓██▒░██▓ ▒██▒▒██░   ▓██░░██░▒██░   ▓██░ ▓███▒   ▓█   ▓██▒
  ░ ▒▓ ░▒▓░ ▒▒   ▓▒█░░ ▒▓ ░▒▓░░ ▒░   ▒ ▒ ░▓  ░ ▒░   ▒ ▒  ▒▓▒▒░   ▒▒   ▓▒█░
    ░▒ ░ ▒░  ▒   ▒▒ ░  ░▒ ░ ▒░░ ░░   ░ ▒░ ▒ ░░ ░░   ░ ▒░ ▒ ░▒░    ▒   ▒▒ ░""", "34") + \
    _c("\n             || RARNinja: The RAR Password Cracking Utility ||", "31")


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def detect_backend(explicit=None):
    """Return (tool_path, family). family is 'unrar' or '7z'."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    # Prefer the binary we vendored next to this script.
    exe = "unrar.exe" if os.name == "nt" else "unrar"
    candidates.append(os.path.join(HERE, "bin", exe))
    candidates += ["unrar", "7zz", "7z"]

    for c in candidates:
        path = c if os.path.isfile(c) else shutil.which(c)
        if not path:
            continue
        base = os.path.basename(path).lower()
        family = "7z" if base.startswith("7z") else "unrar"
        return path, family
    return None, None


def make_test_cmd(tool, family, rar, password):
    """Argv that tests a password and exits 0 iff it is correct (no extraction)."""
    if family == "7z":
        return [tool, "t", f"-p{password}", "-y", rar]
    # unrar: 't' = test, '-inul' = silent, '--' ends options, stdin gets no prompt.
    return [tool, "t", f"-p{password}", "-inul", "-y", "--", rar]


def make_extract_cmd(tool, family, rar, password, dest):
    if family == "7z":
        return [tool, "x", f"-p{password}", "-y", f"-o{dest}", rar]
    return [tool, "x", f"-p{password}", "-o+", "-y", "--", rar, dest + os.sep]


# ---------------------------------------------------------------------------
# Worker (runs in each child process)
# ---------------------------------------------------------------------------

_W = {}


def _init(tool, family, rar, found):
    _W["tool"], _W["family"], _W["rar"], _W["found"] = tool, family, rar, found


def _try(password):
    if _W["found"].is_set():
        return None
    cmd = make_test_cmd(_W["tool"], _W["family"], _W["rar"], password)
    try:
        rc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode
    except Exception:
        return None
    if rc == 0:                      # 0 == correct password, only 0.
        _W["found"].set()
        return password
    return None


# ---------------------------------------------------------------------------
# Wordlist streaming
# ---------------------------------------------------------------------------

def candidates(path):
    # surrogateescape round-trips arbitrary bytes back through exec() on POSIX,
    # so non-UTF-8 passwords survive intact.
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
        for line in fh:
            pw = line.rstrip("\r\n")
            if pw:
                yield pw


# ---------------------------------------------------------------------------
# Crack driver
# ---------------------------------------------------------------------------

def crack(rar, wordlist, tool, family, workers, progress=True,
          on_progress=None, cancel=None):
    """Return (password_or_None, tried, elapsed).

    on_progress(tried, rate, elapsed): optional callback (e.g. for a GUI).
    cancel: optional threading.Event; setting it stops the run early.
    """
    found = mp.Manager().Event()
    tried = 0
    hit = None
    start = time.time()
    last = start

    pool = mp.Pool(workers, initializer=_init, initargs=(tool, family, rar, found))
    try:
        for result in pool.imap_unordered(_try, candidates(wordlist), chunksize=16):
            tried += 1
            if result is not None:
                hit = result
                break
            if cancel is not None and cancel.is_set():
                found.set()
                break
            now = time.time()
            if now - last >= 0.25:
                rate = tried / (now - start) if now > start else 0
                if on_progress is not None:
                    on_progress(tried, rate, now - start)
                elif progress and IS_TTY:
                    print(f"\r  tried {tried:,}  ({rate:,.0f}/sec)   ", end="", flush=True)
                last = now
    finally:
        pool.terminate()
        pool.join()

    if on_progress is None and progress and IS_TTY:
        print("\r" + " " * 48 + "\r", end="", flush=True)
    return hit, tried, time.time() - start


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Multi-core RAR password dictionary attack.")
    p.add_argument("rar", nargs="?", help="path to the .rar file")
    p.add_argument("wordlist", nargs="?", help="path to the dictionary file")
    p.add_argument("-w", "--workers", type=int, default=os.cpu_count(),
                   help="parallel workers (default: all %d cores)" % (os.cpu_count() or 1))
    p.add_argument("-t", "--tool", help="RAR backend to use (unrar/7zz/7z path)")
    p.add_argument("--extract-dir", default="./Extracted",
                   help="where to extract on success (default: ./Extracted)")
    p.add_argument("--no-extract", action="store_true",
                   help="report the password but do not extract")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress line")
    return p.parse_args(argv)


def prompt_path(label):
    while True:
        path = input(label).strip().strip('"').strip("'")
        if os.path.isfile(path):
            return path
        print(f"  '{path}' is not a file. Try again.")


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    print(BANNER)

    tool, family = detect_backend(args.tool)
    if not tool:
        print(_c("\nNo RAR backend found.", "31"))
        print("Install one of: this repo's bin/unrar, `unrar`, `7zz`, or `7z`.")
        return 2
    print(f"\nBackend: {tool}  ({family})   Workers: {args.workers}")

    rar = args.rar or None
    wordlist = args.wordlist or None
    if rar and not os.path.isfile(rar):
        print(_c(f"RAR not found: {rar}", "31")); rar = None
    if wordlist and not os.path.isfile(wordlist):
        print(_c(f"Wordlist not found: {wordlist}", "31")); wordlist = None
    if not rar:
        rar = prompt_path("\nEnter RAR file path: ")
    if not wordlist:
        wordlist = prompt_path("Enter dictionary file path: ")

    print("\nWorking...")
    hit, tried, elapsed = crack(rar, wordlist, tool, family,
                                max(1, args.workers), progress=not args.quiet)

    rate = tried / elapsed if elapsed > 0 else 0
    if hit is None:
        print(_c(f"\nExhausted {tried:,} candidates in {elapsed:.2f}s "
                 f"(~{rate:,.0f}/sec). Password not found.", "31"))
        return 1

    print(_c(f"\n  PASSWORD FOUND: {hit}", "32"))
    print(f"  {tried:,} tries in {elapsed:.2f}s  (~{rate:,.0f}/sec)")

    if not args.no_extract:
        dest = os.path.abspath(args.extract_dir)
        os.makedirs(dest, exist_ok=True)
        cmd = make_extract_cmd(tool, family, rar, hit, dest)
        rc = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL).returncode
        if rc == 0:
            print(_c(f"  Extracted to: {dest}", "32"))
        else:
            print(_c(f"  Extraction failed (exit {rc}).", "31"))
    return 0


if __name__ == "__main__":
    mp.freeze_support()  # required for multiprocessing inside a frozen (compiled) build
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
