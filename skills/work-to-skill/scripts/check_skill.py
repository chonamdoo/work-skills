#!/usr/bin/env python3
"""Check a skill folder's structure against the Agent Skills format and host limits.

Usage: python3 check_skill.py <skill-dir> [--host generic|anthropic]

Errors (exit 1) are format violations that make the package invalid for the
selected host. Warnings are guidance from host documentation, not failures.
Exit 2 is a command-line usage error. Exit 3 means the frontmatter uses YAML
the fallback parser cannot read; the rest of the package is still checked, and
a "frontmatter not checked" warning keeps that meaning whatever the exit code.
Uses PyYAML when installed; otherwise a standard-library parser for the
frontmatter subset skills use (plain, quoted, and block scalars; block
mappings and lists), resolving plain scalars as PyYAML does.
"""

import argparse
import datetime
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
# Link text may hold one level of nested brackets and single line breaks, not a blank line.
_LABEL_CHAR = r"(?:[^\[\]\\\n]|\\.|\n(?![ \t]*\n))"
INLINE_LINK = re.compile(r"\[(?:%s|\[%s*\])*\]\(" % (_LABEL_CHAR, _LABEL_CHAR))
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b\s*[:\]]|\[(?:TODO|TBD|FIXME)\b|<(?:placeholder|TODO|TBD)>")
OPENING = re.compile(r"---[ \t]*\n")
CLOSING = re.compile(r"(?m)^---[ \t]*$")
QUOTED_KEY = re.compile(r"""^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')[ \t]*:(?=[ \t]|$)""")
PLAIN_KEY = re.compile(r"^([^\s#\"'\-?\[{&*!|>%@`][^\n]*?|-[^\s][^\n]*?):(?=[ \t]|$)")
SEQUENCE_ENTRY = re.compile(r"-(?:[ \t]|$)")
BLOCK_INDICATOR = re.compile(r"([|>])([+-]?)")
RESERVED = ("anthropic", "claude")
UNCHECKED = "frontmatter not checked:"

# PyYAML's YAML 1.1 implicit resolvers for plain scalars.
TIMESTAMP = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$|^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:[Tt]|[ \t]+)"
                       r"([0-9]{1,2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]*))?(?:[ \t]*(Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?$")
NULL = re.compile(r"^(?:~|null|Null|NULL)$")
BOOL = re.compile(r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$")
INT = re.compile(r"^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+"
                 r"|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$")
FLOAT = re.compile(r"^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9_]+(?:[eE][-+][0-9]+)?"
                   r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$")
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


def sexagesimal(text, convert):
    sign = -1 if text[:1] == "-" else 1
    total = 0
    for part in text.lstrip("+-").split(":"):
        total = total * 60 + convert(part)
    return sign * total


def resolve_plain(value):
    """Type a plain scalar the way PyYAML's SafeLoader does."""
    if NULL.match(value):
        return None
    timestamp = TIMESTAMP.match(value)
    if timestamp:
        groups = timestamp.groups()
        if groups[0] is not None:
            return datetime.date(*map(int, groups[:3]))
        year, month, day, hour, minute, second, fraction, zone = groups[3:]
        micro = int((fraction or "0")[:6].ljust(6, "0"))
        tzinfo = None
        if zone == "Z":
            tzinfo = datetime.timezone.utc
        elif zone:
            sign = -1 if zone[0] == "-" else 1
            hours, _, minutes = zone[1:].partition(":")
            tzinfo = datetime.timezone(sign * datetime.timedelta(hours=int(hours), minutes=int(minutes or 0)))
        return datetime.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second), micro, tzinfo)
    if BOOL.match(value):
        return value.lower() in ("yes", "true", "on")
    if INT.match(value):
        digits = value.replace("_", "")
        if ":" in digits:
            return sexagesimal(digits, int)
        body = digits.lstrip("+-")
        sign = -1 if digits[:1] == "-" else 1
        if body.startswith("0b"):
            return sign * int(body[2:], 2)
        if body.startswith("0x"):
            return sign * int(body[2:], 16)
        if body != "0" and body.startswith("0"):
            return sign * int(body, 8)
        return sign * int(body)
    if FLOAT.match(value):
        digits = value.replace("_", "").lower()
        if ":" in digits:
            return float(sexagesimal(digits, float))
        return float(digits.replace(".inf", "inf").replace(".nan", "nan"))
    return value


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
    if re.match(r"[-?:](?:\s|$)", value):
        raise ValueError(f"a value cannot start with '{value[0]} '; quote it: {value[:60]}")
    if re.search(r":(?:\s|$)", value):
        raise ValueError(f"unquoted value contains ': ', which YAML reads as a mapping; quote it: {value[:60]}")
    if value == "":
        return None
    return resolve_plain(value)


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def block_scalar(indicator, block):
    """Interpret a literal (|) or folded (>) block scalar with clip, strip, or keep chomping."""
    match = BLOCK_INDICATOR.fullmatch(indicator)
    if not match:
        raise Unsupported(f"block scalar indicator '{indicator}'")
    style, chomp = match.groups()
    content = [line for line in block if line.strip()]
    leading = []
    for line in block:
        if line.strip():
            break
        leading.append(len(line) - len(line.lstrip(" ")))
    # Like PyYAML, the indentation is the deepest of the leading blank lines and the first content line.
    indent = max([indent_of(content[0])] + leading) if content else 0
    lines, ended = [], False
    for line in block:
        if not line.strip():
            if not ended:
                lines.append("")
        elif indent_of(line) < indent:
            if line.lstrip().startswith("#"):
                ended = True  # a less-indented comment ends the scalar
                continue
            raise ValueError(f"block scalar line is less indented than its first line: {line.strip()}")
        elif ended:
            if not line.lstrip().startswith("#"):
                raise ValueError(f"indented line after the block scalar ended: {line.strip()}")
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
    plain = PLAIN_KEY.match(line)
    if not plain:
        return None
    key = plain.group(1).strip()
    return (key if key == "<<" else resolve_plain(key)), line[plain.end():]


def is_key_line(line):
    return bool(QUOTED_KEY.match(line) or PLAIN_KEY.match(line))


def block_end(lines, start, allow_sequence):
    """Index after the lines that belong to the value of the key on lines[start - 1]."""
    j = start
    while j < len(lines):
        line = lines[j]
        if not line.strip() or line[0] in " \t" or (allow_sequence and SEQUENCE_ENTRY.match(line)):
            j += 1
            continue
        if line.startswith("#"):
            k = j + 1
            while k < len(lines) and (not lines[k].strip() or lines[k].startswith("#")):
                k += 1
            if k < len(lines) and (lines[k][0] in " \t" or (allow_sequence and SEQUENCE_ENTRY.match(lines[k]))):
                j = k
                continue
        break
    return j


def plain_lines(value, commented, block):
    """Fold a multi-line plain scalar as PyYAML does: line breaks become spaces, blank lines newlines."""
    entries = []
    for raw in block:
        stripped = raw.strip()
        if not stripped:
            entries.append(("blank", "", False))
        elif stripped.startswith("#"):
            entries.append(("comment", "", False))
        else:
            piece = strip_comment(stripped)
            entries.append(("text", piece, piece != stripped))
    while entries and entries[-1][0] != "text":
        entries.pop()
    if not value:
        while entries and entries[0][0] != "text":
            entries.pop(0)
    if not entries:
        return plain_scalar(value)
    first = value or entries[0][1]
    if not value and re.match(r"\?(?:\s|$)", first):
        raise Unsupported(f"complex mapping key: {first[:40]}")
    if first[:1] in ("[", "{") and (value or len(entries) > 1):
        raise Unsupported(f"multi-line flow collection: {first[:40]}")
    text, blanks, ended = value, 0, bool(value) and commented
    if value:
        plain_scalar(value)
    for kind, piece, has_comment in entries:
        if kind == "blank":
            blanks += 1
            continue
        if kind == "comment":
            ended = True
            continue
        if ended:
            raise ValueError(f"a comment ends a multi-line value; quote the value or move the comment: {piece[:60]}")
        if text and re.search(r":(?:\s|$)", piece):
            raise ValueError(f"unquoted value contains ': ', which YAML reads as a mapping; quote it: {piece[:60]}")
        if text:
            text += "\n" * blanks if blanks else " "
        text += piece
        blanks, ended = 0, has_comment
    return plain_scalar(text) if "\n" not in text else text


def parse_mapping(lines):
    """Parse a block mapping with the standard library; lists keep only their type."""
    fields = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.rstrip() == "...":
            if any(rest.strip() and rest.rstrip() != "..." and not rest.lstrip().startswith("#") for rest in lines[i:]):
                raise ValueError("content after the '...' document end marker")
            break
        if line[0] in " \t":
            raise ValueError(f"unexpected indented frontmatter line: {line.strip()}")
        split = split_key(line)
        if split is None:
            raise ValueError(f"frontmatter line is not 'key: value': {line.strip()}")
        key, value = split
        if key == "<<":
            raise Unsupported("YAML merge key")
        if key in fields:
            raise ValueError(f"duplicate frontmatter key: {key}")
        quoted = value.strip()[:1] in ("\"", "'")
        raw_value = value
        commented = not quoted and strip_comment(value) != value.strip()
        value = value.strip() if quoted else strip_comment(value)
        j = block_end(lines, i, allow_sequence=not value)
        block, i = lines[i:j], j
        if quoted and not re.match(r"""^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')""", value):
            raise Unsupported(f"quoted value of '{key}' continues past its line")
        if quoted and not any(b.strip() and not b.lstrip().startswith("#") for b in block):
            plain_scalar(raw_value)  # rejects text after the closing quote
        if value[:1] in (">", "|"):
            if any(b[:1] == "#" for b in block):
                raise Unsupported(f"column-0 comment inside the block value of '{key}'")
            fields[key] = block_scalar(value, block)
            continue
        content = [b for b in block if b.strip() and not b.lstrip().startswith("#")]
        first = content[0].strip() if content else ""
        if not value and BLOCK_INDICATOR.match(first):
            raise Unsupported(f"block scalar indicator on the line after '{key}'")
        if value and content and value[:1] in "\"'":
            raise Unsupported(f"multi-line quoted value of '{key}'")
        if not value and content and SEQUENCE_ENTRY.match(first):
            indent = indent_of(content[0])
            if any(indent_of(b) < indent or (indent_of(b) == indent and not SEQUENCE_ENTRY.match(b.strip()))
                   for b in content):
                raise ValueError(f"'{key}' mixes list entries with other lines at the same indentation")
            fields[key] = []
        elif not value and content and is_key_line(first):
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
            fields[key] = plain_lines(value, commented, block)
    return fields


def yaml_loader():
    """PyYAML SafeLoader that rejects keys repeated in one mapping, as strict skill loaders do."""

    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            seen = set()
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    continue  # merged keys may be overridden; SafeLoader applies the merge
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
    if "\t" in header:
        raise Unsupported("tab characters, which YAML accepts only in some positions")
    return parse_mapping(header.splitlines())


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

    # The specification types these fields, but its reference validator (skills-ref)
    # stringifies metadata values and does not type allowed-tools, so mismatches warn.
    if "metadata" in fields:
        metadata = fields["metadata"]
        if metadata is None:
            warnings.append("metadata: empty; remove it or add key-value pairs")
        elif not isinstance(metadata, dict):
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


def skip_space(text, i):
    """Skip spaces and tabs with at most one line break; None at a blank line."""
    while i < len(text) and text[i] in " \t":
        i += 1
    if i < len(text) and text[i] == "\n":
        i += 1
        while i < len(text) and text[i] in " \t":
            i += 1
        if i < len(text) and text[i] == "\n":
            return None
    return i


def angle_destination(text, i):
    """Parse '<...>' at text[i]; return (destination, end) or None."""
    j, out = i + 1, []
    while j < len(text) and text[j] not in "<>\n":
        if text[j] == "\\" and text[j + 1 : j + 2] and text[j + 1] in string.punctuation:
            out.append(text[j + 1])
            j += 2
            continue
        out.append(text[j])
        j += 1
    if j >= len(text) or text[j] != ">":
        return None
    return "".join(out), j + 1


def raw_destination(text, i):
    """Parse a bare destination with balanced parentheses; return (destination, end)."""
    depth, j, out = 0, i, []
    while j < len(text):
        char = text[j]
        if char == "\\" and text[j + 1 : j + 2] and text[j + 1] in string.punctuation:
            out.append(text[j + 1])
            j += 2
            continue
        if char.isspace() or ord(char) < 32:
            break
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        out.append(char)
        j += 1
    return "".join(out), j


def skip_title(text, i):
    """Skip a link title opening at text[i]; return the end or None if it never closes."""
    close = {'"': '"', "'": "'", "(": ")"}[text[i]]
    j = i + 1
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == close:
            return j + 1
        if text[j] == "\n" and text[j + 1 : j + 2] == "\n":
            return None
        j += 1
    return None


def inline_destination(text, i):
    """Parse the inside of '(...)' after a link label; return the destination, '' if empty, or None."""
    i = skip_space(text, i)
    if i is None or i >= len(text):
        return None
    if text[i] == ")":
        return ""
    if text[i] == "<":
        parsed = angle_destination(text, i)
        if parsed is None:
            return None
        destination, end = parsed
    else:
        destination, end = raw_destination(text, i)
    k = skip_space(text, end)
    if k is None:
        return None
    if k > end and k < len(text) and text[k] in "\"'(":
        k = skip_title(text, k)
        if k is None:
            return None
        k = skip_space(text, k)
        if k is None:
            return None
    return destination if k < len(text) and text[k] == ")" else None


def is_image_opener(text, start):
    """Whether the '[' at text[start] follows an unescaped '!'."""
    before = text[:start]
    return before.endswith("!") and (len(before) - 1 - len(before[:-1].rstrip("\\"))) % 2 == 0


def complete_link(prose, start):
    """Destination of a complete inline link or image whose label opens at prose[start], or None."""
    label = INLINE_LINK.match(prose, start)
    if not label:
        return None
    if not is_image_opener(prose, start):
        # Links cannot contain links: link text holding a complete non-image link is plain text.
        inner = prose[start + 1 : label.end() - 2]
        for nested in re.finditer(r"\[", inner):
            if not is_image_opener(inner, nested.start()) and complete_link(inner, nested.start()) is not None:
                return None
    return inline_destination(prose, label.end())


def link_targets(prose):
    """Yield destinations of complete inline links, including links and images nested in link text.

    Reference-style definitions are not checked: telling them apart from template
    lines such as "[Severity]: high" needs a full CommonMark block parser.
    """
    for start in (m.start() for m in re.finditer(r"\[", prose)):
        destination = complete_link(prose, start)
        if destination is not None:
            yield destination


def markdown_files(skill_dir, errors, warnings):
    """Yield (path, text) for readable Markdown files, reporting the rest."""
    for path in sorted(skill_dir.rglob("*.md")):
        rel = path.relative_to(skill_dir)
        if not path.is_file():
            if path.is_symlink() and not path.exists():
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
        prose = re.sub(r"(?s)<!--.*?-->", "", prose)
        for target in link_targets(prose):
            try:
                url = urlsplit(target)
                if url.scheme or url.netloc or not url.path:
                    continue
                resolved = (path.parent / unquote(url.path)).resolve()
                exists = resolved.exists()
            except (ValueError, OSError):
                errors.append(f"{rel}: link '{target}' is not a valid local path")
                continue
            if "\\" in url.path:
                warnings.append(f"{rel}: link '{target}' uses backslashes; use forward slashes")
            if not exists:
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
