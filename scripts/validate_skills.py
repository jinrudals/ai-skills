#!/usr/bin/env python3
"""Validate that every skills/<name>/ has a well-formed SKILL.md.

Rules: SKILL.md exists; frontmatter has `name` (equal to the directory name)
and a non-empty `description`. Zero dependencies; emits GitHub annotations.
"""
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def parse_frontmatter(text):
    """Return top-level key -> value, supporting plain and folded/literal scalars."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None
    fields, key, buf = {}, None, []

    def flush():
        if key is not None:
            fields[key] = " ".join(p.strip() for p in buf if p.strip())

    for line in lines[1:end]:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            flush()
            key, val = m.group(1), m.group(2).strip()
            buf = [] if val in (">", "|", ">-", "|-", ">+", "|+") else [val.strip("\"'")]
        elif key is not None:
            buf.append(line)
    flush()
    return fields


def validate(skills_dir):
    errors = []
    for d in sorted(p for p in Path(skills_dir).iterdir() if p.is_dir()):
        md = d / "SKILL.md"
        if not md.is_file():
            errors.append((d, "missing SKILL.md"))
            continue
        fm = parse_frontmatter(md.read_text(encoding="utf-8"))
        if fm is None:
            errors.append((md, "missing or unterminated frontmatter"))
            continue
        name = fm.get("name", "")
        if not name:
            errors.append((md, "frontmatter `name` is missing"))
        elif not NAME_RE.match(name):
            errors.append((md, f"`name` {name!r} must be lowercase-hyphenated"))
        elif name != d.name:
            errors.append((md, f"`name` {name!r} does not match directory {d.name!r}"))
        if not fm.get("description"):
            errors.append((md, "frontmatter `description` is missing or empty"))
    return errors


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "skills"
    errors = validate(root)
    for path, msg in errors:
        print(f"::error file={path}::{msg}")
    print(f"{len(errors)} problem(s) found")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
