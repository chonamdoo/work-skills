#!/usr/bin/env python3
"""Check a skill folder's structure against the Agent Skills format and host limits.

Usage: python3 check_skill.py <skill-dir> [--host generic|anthropic]

Errors (exit 1) are format violations that make the package invalid for the
selected host. Warnings are guidance from host documentation, not failures.
Standard library only, so it runs wherever the skill is authored.
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
XML_TAG = re.compile(r"</?[A-Za-z][\w.-]*(?:\s[^<>]*)?/?>")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b\s*[:\]]|\[(?:TODO|TBD|FIXME)\b|<(?:placeholder|TODO|TBD)>")
RESERVED = ("anthropic", "claude")


def unquote_scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner.replace('\\"', '"')
    return value


def parse_frontmatter(text):
    """Return (fields, body) for top-level scalar keys; nested values are kept as raw text."""
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with a '---' YAML frontmatter line")
    end = text.find("\n---", 4)
    if end < 0 or text[end + 4 : end + 5] not in ("\n", ""):
        raise ValueError("frontmatter is not closed by a '---' line")
    lines = text[4:end].split("\n")
    fields = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            raise ValueError(f"unexpected indented frontmatter line: {line.strip()}")
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            raise ValueError(f"frontmatter line is not 'key: value': {line.strip()}")
        key = key.strip()
        if key in fields:
            raise ValueError(f"duplicate frontmatter key: {key}")
        block = []
        while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t"):
            block.append(lines[i])
            i += 1
        value = value.strip()
        if value[:1] in (">", "|"):
            parts = [b.strip() for b in block]
            fields[key] = (" " if value[0] == ">" else "\n").join(parts).strip()
        elif value:
            fields[key] = unquote_scalar(value) if not block else " ".join([value] + [b.strip() for b in block])
        else:
            fields[key] = "\n".join(block)
    return fields, text[end + 4 :]


def check(skill_dir, host="generic"):
    errors, warnings = [], []
    skill_dir = Path(skill_dir)
    entry = skill_dir / "SKILL.md"
    if not entry.is_file():
        return [f"{entry}: missing"], warnings
    text = entry.read_text(encoding="utf-8")
    try:
        fields, body = parse_frontmatter(text)
    except ValueError as exc:
        return [f"SKILL.md: {exc}"], warnings

    name = fields.get("name")
    if not isinstance(name, str) or not name:
        errors.append("name: required")
    else:
        if len(name) > 64:
            errors.append(f"name: {len(name)} characters; the limit is 64")
        if not NAME.match(name):
            errors.append("name: use lowercase letters, digits, and single hyphens, not at either end")
        if name != skill_dir.resolve().name:
            errors.append(f"name: '{name}' does not match folder '{skill_dir.resolve().name}'")
        if host == "anthropic":
            for word in RESERVED:
                if word in name:
                    errors.append(f"name: contains '{word}', which Anthropic hosts reserve")

    description = fields.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("description: required")
    elif len(description) > 1024:
        errors.append(f"description: {len(description)} characters; the limit is 1024")

    if host == "anthropic":
        for key in ("name", "description"):
            if isinstance(fields.get(key), str) and XML_TAG.search(fields[key]):
                errors.append(f"{key}: contains an XML tag, which Anthropic hosts reject")

    if not body.strip():
        errors.append("SKILL.md: body is empty")
    body_lines = body.strip("\n").count("\n") + 1
    if body_lines > 500:
        warnings.append(f"SKILL.md: body has {body_lines} lines; host guidance suggests under 500 (not a format rule)")

    root = skill_dir.resolve()
    linked_from_entry = set()
    for path in sorted(skill_dir.rglob("*.md")):
        rel = path.relative_to(skill_dir)
        content = path.read_text(encoding="utf-8")
        for target in LINK.findall(content):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            if "\\" in url.path:
                warnings.append(f"{rel}: link '{target}' uses backslashes; use forward slashes")
            resolved = (path.parent / unquote(url.path)).resolve()
            if not resolved.is_relative_to(root):
                errors.append(f"{rel}: link '{target}' points outside the skill folder")
            elif not resolved.exists():
                errors.append(f"{rel}: link '{target}' does not resolve")
            elif path == entry:
                linked_from_entry.add(resolved)
        for lineno, line in enumerate(content.splitlines(), 1):
            if PLACEHOLDER.search(line):
                warnings.append(f"{rel}:{lineno}: unfinished placeholder: {line.strip()[:80]}")

    for path in sorted(skill_dir.rglob("*.md")):
        if path == entry or path.resolve() in linked_from_entry:
            continue
        if "references" in path.relative_to(skill_dir).parts:
            warnings.append(
                f"{path.relative_to(skill_dir)}: not linked directly from SKILL.md; "
                "nested references may be read only partially"
            )
    return errors, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("skill_dir")
    parser.add_argument("--host", choices=("generic", "anthropic"), default="generic",
                        help="apply a host's documented limits in addition to the common format")
    args = parser.parse_args(argv)
    errors, warnings = check(args.skill_dir, args.host)
    for message in errors:
        print(f"error: {message}")
    for message in warnings:
        print(f"warning: {message}")
    if not errors:
        print(f"ok: {args.skill_dir} ({args.host})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
