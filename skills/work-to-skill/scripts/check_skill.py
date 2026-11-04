#!/usr/bin/env python3
"""Check a skill folder's structure against the Agent Skills format and host limits.

Usage: python3 check_skill.py <skill-dir> [--host generic|anthropic]

Errors (exit 1) are format violations that make the package invalid for the
selected host. Warnings are guidance from host documentation, not failures.
Exit 2 is a command-line usage error. Exit 3 means the frontmatter uses YAML
the fallback parser cannot read; links and placeholders are still checked.
Uses PyYAML when installed; otherwise a standard-library parser for the
frontmatter subset skills use (plain, quoted, and block scalars; block
mappings and lists).
"""

import argparse
import re
import string
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ImportError:  # the fallback parser below covers skill frontmatter
    yaml = None

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
XML_TAG = re.compile(r"</?[A-Za-z][\w.-]*(?:\s[^<>]*)?/?>")
INLINE_LINK = re.compile(r"!?\[(?:[^\]\\\n]|\\.)*\]\(")
REFERENCE_LINK = re.compile(r"(?m)^ {0,3}\[(?!\^)[^\]\n]+\]:[ \t]*(<[^>\n]*>|\S+)")
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b\s*[:\]]|\[(?:TODO|TBD|FIXME)\b|<(?:placeholder|TODO|TBD)>")
OPENING = re.compile(r"---[ \t]*\n")
CLOSING = re.compile(r"(?m)^---[ \t]*$")
QUOTED_KEY = re.compile(r"""^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')[ \t]*:(?=[ \t]|$)""")
BLOCK_INDICATOR = re.compile(r"([|>])([+-]?)")
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
    if value[:1] in ("&", "*", "!", "%", "@", "`"):
        raise Unsupported(f"YAML anchors, aliases, tags, or reserved indicators: {value[:40]}")
    if value[:1] in ("[", "{"):
        if value in ("[]", "{}"):
            return [] if value == "[]" else {}
        raise Unsupported(f"YAML flow collection: {value[:40]}")
    if re.search(r":(?:\s|$)", value):
        raise ValueError(f"unquoted value contains ': ', which YAML reads as a mapping; quote it: {value[:60]}")
    if value == "":
        return None
    if value.lower() in SCALARS:
        return SCALARS[value.lower()]
    if NUMBER.match(value):
        return float(value) if any(c in value for c in ".eE") else int(value.replace("_", ""))
    return value


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def block_scalar(indicator, block):
    """Interpret a literal (|) or folded (>) block scalar with clip, strip, or keep chomping."""
    match = BLOCK_INDICATOR.fullmatch(indicator)
    if not match:
        raise Unsupported(f"block scalar indicator '{indicator}'")
    style, chomp = match.groups()
    content = [line for line in block if line.strip()]
    indent = indent_of(content[0]) if content else 0
    lines = []
    for line in block:
        if not line.strip():
            lines.append("")
        elif indent_of(line) < indent:
            raise ValueError(f"block scalar line is less indented than its first line: {line.strip()}")
        else:
            lines.append(line[indent:])
    trailing = 0
    while lines and lines[-1] == "":
        lines.pop()
        trailing += 1
    if style == "|":
        text = "\n".join(lines)
    else:
        text, blanks, previous = "", 0, None
        for line in lines:
            if line == "":
                blanks += 1
                continue
            if previous is None:
                text = "\n" * blanks + line
            elif previous[:1] not in (" ", "\t") and line[:1] not in (" ", "\t"):
                text += (" " if blanks == 0 else "\n" * blanks) + line
            else:
                text += "\n" * (blanks + 1) + line
            previous, blanks = line, 0
    if chomp == "-" or not text:
        return text if chomp != "+" else text + "\n" * trailing
    return text + "\n" if chomp == "" else text + "\n" * (trailing + 1)


def split_key(line):
    """Return (key, rest) for a 'key: value' line, or None."""
    quoted = QUOTED_KEY.match(line)
    if quoted:
        return plain_scalar(quoted.group(1)), line[quoted.end():]
    if line[:1] in ("?", "[", "{", "&", "*", "!"):
        raise Unsupported(f"complex or flow mapping key: {line.strip()[:40]}")
    key, sep, rest = line.partition(":")
    if not sep or not key.strip() or key[:1] in ("\"", "'", "-") or rest[:1] not in ("", " ", "\t"):
        return None
    return key.strip(), rest


def parse_mapping(lines):
    """Parse a block mapping with the standard library; lists keep only their type."""
    fields = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            raise ValueError(f"unexpected indented frontmatter line: {line.strip()}")
        split = split_key(line)
        if split is None:
            raise ValueError(f"frontmatter line is not 'key: value': {line.strip()}")
        key, value = split
        if key in fields:
            raise ValueError(f"duplicate frontmatter key: {key}")
        j = i
        while j < len(lines) and (not lines[j].strip() or lines[j][0] in " \t"):
            j += 1
        block, i = lines[i:j], j
        value = strip_comment(value) if value.strip()[:1] not in ("\"", "'") else value.strip()
        if value[:1] in (">", "|"):
            fields[key] = block_scalar(value, block)
            continue
        content = [b for b in block if b.strip() and not b.lstrip().startswith("#")]
        first = content[0].strip() if content else ""
        if value and content and value[:1] in "\"'":
            raise Unsupported(f"multi-line quoted value of '{key}'")
        if not value and content and (first == "-" or first.startswith("- ")):
            fields[key] = []
        elif not value and content and (QUOTED_KEY.match(first) or re.match(r"^[^\s#\"'\-][^:]*:(?:\s|$)", first)):
            indent = indent_of(content[0])
            if any(indent_of(b) < indent for b in content):
                raise ValueError(f"inconsistent indentation under '{key}'")
            nested = ["" if not b.strip() or b.lstrip().startswith("#") else b[indent:] for b in block]
            fields[key] = parse_mapping(nested)
        elif not value and content and first[:1] in "\"'":
            if len(content) > 1:
                raise Unsupported(f"multi-line quoted value of '{key}'")
            fields[key] = plain_scalar(first)
        else:
            pieces = ([value] if value else []) + [strip_comment(p) for p in content]
            fields[key] = plain_scalar(" ".join(p for p in pieces if p))
    return fields


def yaml_loader():
    """PyYAML SafeLoader that rejects duplicate keys, as strict skill loaders do."""

    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in seen
                except TypeError:
                    continue
                if duplicate:
                    raise yaml.constructor.ConstructorError(
                        None, None, f"duplicate key: {key}", key_node.start_mark)
                seen.add(key)
            return super().construct_mapping(node, deep)

    return UniqueKeyLoader


def parse_fields(header):
    """Parse frontmatter into a mapping."""
    if yaml is not None:
        try:
            fields = yaml.load(header, Loader=yaml_loader())
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML: {exc}") from None
        if fields is None:
            return {}
        if not isinstance(fields, dict):
            raise ValueError("frontmatter must be a mapping")
        return fields
    return parse_mapping(header.split("\n"))


def split_frontmatter(text):
    """Return (header, body)."""
    if text.startswith("\ufeff"):
        raise ValueError("SKILL.md starts with a UTF-8 byte-order mark; save it without one so it begins with '---'")
    opening = OPENING.match(text)
    if not opening:
        raise ValueError("SKILL.md must start with a '---' YAML frontmatter line")
    closing = CLOSING.search(text, opening.end())
    if not closing:
        raise ValueError("frontmatter is not closed by a '---' line")
    return text[opening.end() : closing.start()], text[closing.end() :]


def parse_frontmatter(text):
    """Return (fields, body)."""
    header, body = split_frontmatter(text)
    return parse_fields(header), body


def check_fields(fields, skill_dir, host, errors, warnings):
    name = fields.get("name")
    if name is None or name == "":
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
    if description is not None and not isinstance(description, str):
        errors.append(f"description: must be a string, not {type(description).__name__}")
    elif not isinstance(description, str) or not description.strip():
        errors.append("description: required")
    elif len(description) > 1024:
        errors.append(f"description: {len(description)} characters; the limit is 1024")

    if "compatibility" in fields:
        compatibility = fields["compatibility"]
        if not isinstance(compatibility, str) or not compatibility.strip():
            errors.append("compatibility: must be a non-empty string when present")
        elif len(compatibility) > 500:
            errors.append(f"compatibility: {len(compatibility)} characters; the limit is 500")

    if "metadata" in fields:
        metadata = fields["metadata"]
        if not isinstance(metadata, dict):
            errors.append(f"metadata: must be a mapping, not {type(metadata).__name__}")
        else:
            loose = [str(k) for k, v in metadata.items() if not isinstance(k, str) or not isinstance(v, str)]
            if loose:
                warnings.append(
                    "metadata: the specification defines string keys and values; "
                    f"quote or flatten: {', '.join(loose)}"
                )

    if "allowed-tools" in fields and not isinstance(fields["allowed-tools"], str):
        warnings.append(
            "allowed-tools: the specification defines a space-separated string; "
            "support for other forms varies by host"
        )

    if host == "anthropic":
        for key in ("name", "description"):
            if isinstance(fields.get(key), str) and XML_TAG.search(fields[key]):
                errors.append(f"{key}: contains an XML tag, which Anthropic hosts reject")


def link_targets(prose):
    """Yield local-or-remote destinations of inline and reference-style Markdown links."""
    for match in INLINE_LINK.finditer(prose):
        i = match.end()
        while i < len(prose) and prose[i] in " \t":
            i += 1
        if prose[i : i + 1] == "<":
            end = prose.find(">", i)
            if end > i and "\n" not in prose[i:end]:
                yield prose[i + 1 : end]
            continue
        depth, j, out = 0, i, []
        while j < len(prose):
            char = prose[j]
            if char == "\\" and prose[j + 1 : j + 2] and prose[j + 1] in string.punctuation:
                out.append(prose[j + 1])
                j += 2
                continue
            if char.isspace():
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            out.append(char)
            j += 1
        if out:
            yield "".join(out)
    for match in REFERENCE_LINK.finditer(prose):
        target = match.group(1)
        yield target[1:-1] if target.startswith("<") else target


def markdown_files(skill_dir, errors, warnings):
    """Yield (path, text) for readable Markdown files, reporting the rest."""
    for path in sorted(skill_dir.rglob("*.md")):
        rel = path.relative_to(skill_dir)
        if not path.is_file():
            if path.is_symlink():
                errors.append(f"{rel}: broken symbolic link")
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(f"{rel}: cannot be read as UTF-8 text ({type(exc).__name__}); links not checked")


def check(skill_dir, host="generic"):
    errors, warnings = [], []
    skill_dir = Path(skill_dir)
    entry = skill_dir / "SKILL.md"
    if not entry.is_file():
        return [f"{entry}: missing"], warnings
    try:
        text = entry.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"SKILL.md: cannot be read as UTF-8 text ({type(exc).__name__})"], warnings
    try:
        header, body = split_frontmatter(text)
    except ValueError as exc:
        return [f"SKILL.md: {exc}"], warnings
    try:
        fields = parse_fields(header)
    except Unsupported as exc:
        warnings.append(f"{UNCHECKED} {exc}; install PyYAML to check the frontmatter")
    except ValueError as exc:
        errors.append(f"SKILL.md: {exc}")
    else:
        check_fields(fields, skill_dir, host, errors, warnings)

    if not body.strip():
        errors.append("SKILL.md: body is empty")
    body_lines = body.strip("\n").count("\n") + 1
    if body_lines > 500:
        warnings.append(f"SKILL.md: body has {body_lines} lines; host guidance suggests under 500 (not a format rule)")

    root = skill_dir.resolve()
    linked_from_entry = set()
    documents = list(markdown_files(skill_dir, errors, warnings))
    for path, content in documents:
        rel = path.relative_to(skill_dir)
        prose = re.sub(r"(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*$", "", content)
        prose = re.sub(r"`[^`\n]*`", "", prose)
        for target in link_targets(prose):
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

    for path, _ in documents:
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
    return 1 if errors else 3 if unchecked else 0


if __name__ == "__main__":
    sys.exit(main())
