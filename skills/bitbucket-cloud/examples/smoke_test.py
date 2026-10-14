#!/usr/bin/env python3
"""Opt-in, read-only live smoke test for bitbucket_cloud.py.

Needs real credentials (configured file or BITBUCKET_* env vars). Sends only
GET requests: `check` and `repo list --limit 1`.

Run: BITBUCKET_SMOKE=1 python3 examples/smoke_test.py      (POSIX)
     $env:BITBUCKET_SMOKE = "1"; python examples/smoke_test.py   (PowerShell)
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "bitbucket_cloud.py")
STEPS = (["check"], ["repo", "list", "--limit", "1"])


def main():
    if os.environ.get("BITBUCKET_SMOKE") != "1":
        print("skipped: set BITBUCKET_SMOKE=1 to run against the live API")
        return 0
    failed = 0
    for argv in STEPS:
        proc = subprocess.run(
            [sys.executable, SCRIPT, *argv], capture_output=True, text=True, encoding="utf-8"
        )
        status = "ok" if proc.returncode == 0 else f"FAILED (exit {proc.returncode})"
        print(f"{' '.join(argv)}: {status}")
        if proc.returncode:
            failed += 1
            print(proc.stderr.strip())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
