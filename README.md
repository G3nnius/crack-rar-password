# RARNinja: RAR Password Cracking Utility

A fast, multi-core dictionary attack against a password-protected RAR file.
This fork is rewritten to run **natively on macOS (Apple Silicon)** and Linux,
with a real process pool that uses every CPU core and stops the instant the
password is found.

## What changed in this fork
- **Native backend, no Windows binary.** The original hardcoded `UnRAR.exe`
  (a Windows executable). This version auto-detects a RAR backend and prefers
  the arm64 `unrar` shipped in [`bin/`](bin) (RARLAB unrar 7.12). `7zz`/`7z` on
  PATH also work.
- **Real parallelism with early-stop.** A `multiprocessing` pool sized to all
  cores; a shared event halts every worker the moment one succeeds. The old
  "multithreaded" script kept grinding all 8 threads after a hit.
- **Tests, don't extract.** Each candidate is checked with `unrar t` (no disk
  writes). Only the winning password triggers an actual extraction.
- **Streams the wordlist** instead of loading it entirely into RAM.
- **Zero pip dependencies** — standard library only.

## Usage

Scriptable (recommended):
```bash
python3 RARNinja.py <archive.rar> <wordlist.txt>
```

Interactive (prompts for paths) — just run it with no arguments:
```bash
python3 RARNinja.py
```

Options:
```
-w, --workers N     parallel workers (default: all cores)
-t, --tool PATH     force a specific backend (unrar / 7zz / 7z)
--extract-dir DIR   extraction target on success (default: ./Extracted)
--no-extract        report the password without extracting
-q, --quiet         suppress the live progress line
```

On success the archive is extracted into `./Extracted/`.

## Compiled binary (macOS arm64)

A standalone, optimized binary that needs no Python and bundles `unrar`:
```bash
./scripts/build.sh        # produces dist/rarninja
./dist/rarninja <archive.rar> <wordlist.txt>
```

## Tests
```bash
python3 tests/test_rarninja.py
```
Cracks the committed encrypted fixture (`tests/fixtures/locked.rar`) and checks
the not-found and extraction paths.

## Performance note
Each guess runs the backend's RAR5 key-derivation once, so throughput is on the
order of hundreds of tries/sec (about 315/sec across 11 cores on an M-series
Mac). For orders-of-magnitude more speed on large wordlists, extract the hash
with `rar2john` and run John the Ripper or hashcat.

------------
Original project by SHUR1K-N: https://TheComputerNoob.com
