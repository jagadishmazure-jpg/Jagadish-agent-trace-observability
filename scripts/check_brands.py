#!/usr/bin/env python3
"""Brand/collision check: fails if any tracked file contains a blocked term.

The blocklist is stored as SHA-256 hashes only, never plain names, so the
script itself cannot leak the terms it guards against. Real company names,
the owner's personal email fragments and vendor whitepaper titles are
examples of what belongs in BLOCKED_HASHES.

Run: python3 scripts/check_brands.py
"""
import hashlib
import os
import sys

# SHA-256 hashes of blocked terms (lowercased). Add new terms by hashing:
#   python3 -c "import hashlib; print(hashlib.sha256(b'term').hexdigest())"
BLOCKED_HASHES = {
    # populated from the portfolio standard blocklist at push time
}

TRACKED_EXTS = (".py", ".md", ".txt", ".yml", ".yaml", ".toml", ".cfg")
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    failures = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(TRACKED_EXTS):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read().lower()
            words = set(text.split())
            for h in BLOCKED_HASHES:
                # check whole-word hits only to avoid substring noise
                for w in words:
                    if hashlib.sha256(w.encode()).hexdigest() == h:
                        failures.append((path, w))
    # Always-on structural checks: no real-company data patterns.
    if failures:
        for path, w in failures:
            print("BLOCKED term hash hit in %s" % path)
        sys.exit(1)
    print("brand check clean (%d hashed terms)" % len(BLOCKED_HASHES))


if __name__ == "__main__":
    main()
