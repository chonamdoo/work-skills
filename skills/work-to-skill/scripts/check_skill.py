#!/usr/bin/env python3
"""Check a skill folder's structure against the Agent Skills format and host limits.

Usage: python3 check_skill.py <skill-dir> [--host generic|anthropic]

Errors (exit 1) are format violations that make the package invalid for the
selected host. Warnings are guidance from host documentation, not failures.
Exit 2 means a frontmatter value uses YAML the fallback parser cannot read; the
other checks still run. Uses PyYAML when installed; otherwise a standard-library
parser for the frontmatter subset skills use (plain, quoted, and block scalars).
Without PyYAML, values nested under a key are checked for type only.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ImportError:  # the fallback parser below covers skill frontmatter
    yaml = None

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
XML_TAG = re.compile(r"</?[A-Za-z][\w.-]*(?:\s[^<>]*)?/?>")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b\s*[:\]]|\[(?:TODO|TBD|FIXME)\b|<(?:placeholder|TODO|TBD)>")
RESERVED = ("anthropic", "claude")
UNCHECKED = "frontmatter not checked:"


SCALARS = {"true": True, "false": False, "yes": True, "no": False, "null": None, "~": None}
NUMBER = re.compile(r"^[-+]?(?:\d[\d_]*(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")
ESCAPES = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v", "f": "\f",
           "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0",
           "L": "\u2028", "P": "\u2029"}
HEX_ESCAPES = {"x": 2, "u": 4, "U": 8}


class Unsupported(ValueError):
    """Valid-looking YAML the standard-library parser cannot interpret."""


class Unchecked:
    """A frontmatter value the fallback parser could not check."""

    def __init__(self, reason):
        self.reason = reason


def unescape_double_quoted(inner):
    out, i = [], 0
    while i < len(inner):
        char = inner[i]
        if char != "\\":
            out.append(char)
            i += 1
            continue
        code = inner[i + 1 : i + 2]
        if code in ESCAPES:
            out.append(ESCAPES[code])
            i += 2
        elif code in HEX_ESCAPES:
            digits = inner[i + 2 : i + 2 + HEX_ESCAPES[code]]
            if len(digits) != HEX_ESCAPES[code] or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                raise ValueError(f"invalid escape \\{code}{digits}")
            out.append(chr(int(digits, 16)))
            i += 2 + len(digits)
        else:
            raise ValueError(f"invalid escape \\{code}")
    return "".join(out)


def strip_comment(value):
    value = value.strip()
    return "" if value.startswith("#") else re.sub(r"\s+#.*$", "", value)


def plain_scalar(value):
    """Interpret a YAML scalar written on one logical line, keeping its type."""
    value = value.strip()
    if value[:1] == '"':
        end = re.match(r'"(?:[^"\\]|\\.)*"', value)
        if not end or value[end.end():].strip()[:1] not in ("", "#"):
            raise ValueError(f"malformed double-quoted value: {value}")
        return unescape_double_quoted(end.group(0)[1:-1])
    if value[:1] == "'":
        end = re.match(r"'(?:[^']|'')*'", value)
        if not end or value[end.end():].strip()[:1] not in ("", "#"):
            raise ValueError(f"malformed single-quoted value: {value}")
        return end.group(0)[1:-1].replace("''", "'")
    value = strip_comment(value)
    if value[:1] in ("&", "*", "!", "%", "@", "`", "[", "{", "]", "}", ",") or re.match(r"[-?:](?:\s|$)", value):
        raise Unsupported(f"YAML indicator syntax is not validated: {value[:40]}")
    if re.search(r":(?:\s|$)", value):
        raise ValueError(f"unquoted value contains ': ', which YAML reads as a mapping; quote it: {value[:60]}")
    if value == "":
        return None
    if value.lower() in SCALARS:
        return SCALARS[value.lower()]
    if NUMBER.match(value):
        return float(value) if any(c in value for c in ".eE") else int(value.replace("_", ""))
    return value


def block_scalar(indicator, block):
    lines = [b.strip() for b in block]
    if indicator.startswith("|"):
        text = "\n".join(lines)
    else:
        text = ""
        for line in lines:
            text += "\n" if not line else (" " if text and not text.endswith("\n") else "") + line
    return text.strip("\n") if "-" in indicator else text.rstrip("\n") + "\n"


def parse_fields(header):
    """Parse top-level frontmatter keys; nested mappings and lists keep only their type."""
    if yaml is not None:
        try:
            fields = yaml.safe_load(header)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML: {exc}") from None
        if fields is None:
            return {}
        if not isinstance(fields, dict):
            raise ValueError("frontmatter must be a mapping")
        return fields
    lines = header.split("\n")
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
        if not sep or not key.strip() or value[:1] not in ("", " ", "\t"):
            raise ValueError(f"frontmatter line is not 'key: value': {line.strip()}")
        key = key.strip()
        if key in fields:
            raise ValueError(f"duplicate frontmatter key: {key}")
        j = i
        while j < len(lines) and (not lines[j].strip() or lines[j][0] in " \t"):
            j += 1
        while j > i and not lines[j - 1].strip():
            j -= 1
        block, i = lines[i:j], j
        try:
            fields[key] = parse_value(key, value, block)
        except Unsupported as exc:
            fields[key] = Unchecked(str(exc))
    return fields


def parse_value(key, value, block):
    value = strip_comment(value) if value.strip()[:1] not in ("\"", "'") else value.strip()
    if value[:1] in (">", "|"):
        return block_scalar(value, block)
    parts = [b.strip() for b in block if b.strip()]
    if value and parts and value[:1] in "\"'":
        raise Unsupported(f"multi-line quoted value of '{key}'")
    if not value and parts:
        for part in parts:
            item = re.sub(r"^(?:-\s+)+", "", part)
            nested = re.match(r"^[^\s#\"'\[{][^:]*:(?:\s+|$)(.*)$", item)
            if (nested.group(1) if nested else item)[:1] in ("[", "{"):
                raise Unsupported(f"flow collection syntax is not validated in '{key}'")
    if not value and parts and (parts[0] == "-" or parts[0].startswith("- ")):
        return []
    if not value and parts and re.match(r"^[^\s#\"'][^:]*:(?:\s|$)", parts[0]):
        return {}
    if not value and parts and parts[0][:1] in "\"'":
        if len(parts) > 1:
            raise Unsupported(f"multi-line quoted value of '{key}'")
        return plain_scalar(parts[0])
    pieces = ([value] if value else []) + [strip_comment(p) for p in parts]
    return plain_scalar(" ".join(p for p in pieces if p))


def parse_frontmatter(text):
    """Return (fields, body)."""
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with a '---' YAML frontmatter line")
    end = text.find("\n---", 3)
    if end < 0 or text[end + 4 : end + 5] not in ("\n", ""):
        raise ValueError("frontmatter is not closed by a '---' line")
    return parse_fields(text[4:end]), text[end + 4 :]


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
    for key, value in fields.items():
        if isinstance(value, Unchecked):
            warnings.append(f"{UNCHECKED} {key}: {value.reason}; install PyYAML to check it")

    name = fields.get("name")
    if isinstance(name, Unchecked):
        pass
    elif name is None or name == "":
        errors.append("name: required")
    elif not isinstance(name, str):
        errors.append(f"name: must be a string, not {type(name).__name__}")
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
    if isinstance(description, Unchecked):
        pass
    elif description is not None and not isinstance(description, str):
        errors.append(f"description: must be a string, not {type(description).__name__}")
    elif not isinstance(description, str) or not description.strip():
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
        prose = re.sub(r"(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*$", "", content)
        prose = re.sub(r"`[^`\n]*`", "", prose)
        for target in LINK.findall(prose):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            if "\\" in url.path:
                warnings.append(f"{rel}: link '{target}' uses backslashes; use forward slashes")
            resolved = (path.parent / unquote(url.path)).resolve()
            if not resolved.exists():
                errors.append(f"{rel}: link '{target}' does not resolve")
            elif not resolved.is_relative_to(root):
                warnings.append(f"{rel}: link '{target}' points outside the skill folder and will not travel with it")
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
    unchecked = any(w.startswith(UNCHECKED) for w in warnings)
    if not errors and not unchecked:
        print(f"ok: {args.skill_dir} ({args.host})")
    return 1 if errors else 2 if unchecked else 0


if __name__ == "__main__":
    sys.exit(main())
