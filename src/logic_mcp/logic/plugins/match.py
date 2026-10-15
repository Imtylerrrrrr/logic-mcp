"""플러그인 이름 매칭. LCD는 `(s/s)` 같은 채널 구성 접미를 붙이고 21자에서 자른다."""
from __future__ import annotations

import re

_SUFFIX_RE = re.compile(r"\s*\((?:s/s|m/s|m/m|s|m|st|mono|stereo|dual mono)[^)]*\)?\s*$", re.IGNORECASE)
_JUNK_RE = re.compile(r"[\s\-_]+")


def normalize(name: str) -> str:
    return _JUNK_RE.sub("", _SUFFIX_RE.sub("", name.strip())).lower()


def find(items: list[str], query: str) -> tuple[int | None, list[str]]:
    """정규화 뒤 정확 일치 → 접두 일치(잘린 이름 포함) → 부분 일치. (인덱스, 후보). 후보 2개 이상이면 인덱스 None."""
    q = normalize(query)
    if not q or query.strip() == "--":
        return None, []
    norm = [(i, normalize(n)) for i, n in enumerate(items) if n != "--"]
    rules = (lambda a, b: a == b,
             lambda a, b: a.startswith(b) or b.startswith(a),
             lambda a, b: b in a)
    for rule in rules:
        hits = [i for i, n in norm if rule(n, q)]
        if len(hits) == 1:
            return hits[0], [items[hits[0]]]
        if len(hits) > 1:
            return None, [items[i] for i in hits]
    return None, []


def strip_suffix(name: str) -> str:
    """`Channel EQ (s/s)` → `Channel EQ`. 잘린 `(s/` 도 떼어낸다."""
    return _SUFFIX_RE.sub("", name.strip()).strip()
