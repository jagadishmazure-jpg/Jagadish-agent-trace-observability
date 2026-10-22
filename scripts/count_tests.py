#!/usr/bin/env python3
"""Print the test total. Run: python3 scripts/count_tests.py"""
import subprocess
import sys


def main():
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        capture_output=True, text=True, cwd=".")
    for line in out.stdout.splitlines():
        if "tests collected" in line:
            print(line.strip())
            return
    print(out.stdout[-500:] if out.stdout else "no output")


if __name__ == "__main__":
    main()
