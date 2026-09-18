"""Streaming Turtle subset parser for the OWN-PT RDF dumps."""

from __future__ import annotations

from typing import Iterator


def _is_name_char(ch: str) -> bool:
    return ch.isalnum() or ch in "_-:."


def iter_statements(path: str) -> Iterator[str]:
    """Yield Turtle statements, ignoring '.' inside literals and prefixed names."""
    in_string = False
    escape = False
    buf: list[str] = []
    started = False

    with open(path, "r", encoding="utf-8", errors="replace", buffering=1024 * 1024) as handle:
        for line in handle:
            if not started:
                stripped = line.lstrip()
                if not stripped or stripped.startswith("@") or stripped.startswith("#"):
                    continue
            for ch in line:
                if escape:
                    buf.append(ch)
                    escape = False
                    continue
                if ch == "\\" and in_string:
                    buf.append(ch)
                    escape = True
                    continue
                if ch == '"':
                    buf.append(ch)
                    in_string = not in_string
                    started = True
                    continue
                if ch == "." and not in_string and started:
                    prev = buf[-1] if buf else ""
                    if prev.isspace() or prev in "\">":
                        stmt = "".join(buf).strip()
                        if stmt:
                            yield stmt
                        buf = []
                        started = False
                        continue
                if not started and ch.isspace():
                    continue
                buf.append(ch)
                started = True
    leftover = "".join(buf).strip()
    if leftover:
        yield leftover


def tokenize(statement: str) -> list[tuple]:
    tokens: list[tuple] = []
    i = 0
    n = len(statement)
    while i < n:
        ch = statement[i]
        if ch.isspace():
            i += 1
            continue
        if ch in ".;,":
            tokens.append((ch, ch))
            i += 1
            continue
        if ch == '"':
            i += 1
            chars: list[str] = []
            escape = False
            while i < n:
                cur = statement[i]
                if escape:
                    chars.append(cur)
                    escape = False
                    i += 1
                    continue
                if cur == "\\":
                    escape = True
                    i += 1
                    continue
                if cur == '"':
                    i += 1
                    break
                chars.append(cur)
                i += 1
            lang = ""
            if i < n and statement[i] == "@":
                i += 1
                start = i
                while i < n and (statement[i].isalnum() or statement[i] == "-"):
                    i += 1
                lang = statement[start:i]
            elif i + 1 < n and statement[i : i + 2] == "^^":
                i += 2
                while i < n and not statement[i].isspace() and statement[i] not in ".;,":
                    i += 1
            tokens.append(("lit", "".join(chars), lang))
            continue
        if ch == "<":
            end = statement.find(">", i)
            if end < 0:
                break
            tokens.append(("iri", statement[i + 1 : end]))
            i = end + 1
            continue
        start = i
        while i < n and _is_name_char(statement[i]):
            i += 1
        raw = statement[start:i]
        if not raw:
            i += 1
            continue
        tokens.append(("name", raw.rstrip(".")))
    return tokens


def iter_triples(path: str) -> Iterator[tuple[str, str, object]]:
    """Yield (subject, predicate, object) from a Turtle file.

    Objects are either a resource name (str) or a (literal, lang) tuple.
    """
    for statement in iter_statements(path):
        tokens = tokenize(statement)
        if len(tokens) < 3:
            continue
        subject = tokens[0][1] if tokens[0][0] in {"name", "iri"} else None
        if not subject:
            continue
        predicate = None
        i = 1
        while i < len(tokens):
            kind, value, *rest = tokens[i]
            if kind == ";":
                predicate = None
                i += 1
                continue
            if kind in {".", ","}:
                i += 1
                continue
            if predicate is None:
                predicate = "a" if value == "a" else value
                i += 1
                continue
            if kind == "lit":
                yield subject, predicate, (value, rest[0] if rest else "")
            elif kind in {"name", "iri"}:
                yield subject, predicate, value
            i += 1


def local_name(term: str) -> str:
    if term.startswith("http"):
        return term.rsplit("/", 1)[-1]
    if ":" in term:
        return term.split(":", 1)[1]
    return term


def resource_lang(term: str) -> str:
    if term.startswith("own-en:") or "/own-en/" in term:
        return "en"
    return "pt"


def synset_id_from(term: str) -> str:
    name = local_name(term)
    if name.startswith("synset-"):
        return name[7:]
    if name.startswith("wordsense-"):
        parts = name.split("-")
        if len(parts) >= 3:
            return f"{parts[1]}-{parts[2]}"
    return name


def sense_id_from(term: str) -> str:
    name = local_name(term)
    if name.startswith("wordsense-"):
        return name
    return name


def word_id_from(term: str) -> str:
    name = local_name(term)
    if name.startswith("word-"):
        return name
    return name
