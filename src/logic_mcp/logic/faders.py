"""Logic 페이더 14비트 값 ↔ dB. 표는 실측(캘리브레이션)으로 만든다."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

MAX_RAW = 14845      # +6.0 dB. Logic은 이 위를 클램프한다
ZERO_DB_RAW = 12443
MAX_DB = 6.0
_DB_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?|-oo)\s*dB?\s*$")
_PAN_RE = re.compile(r"^\s*([+-]?\d+)\s*$")


@dataclass(frozen=True)
class FaderTable:
    points: tuple[tuple[int, float], ...]  # (raw, db) 오름차순, db는 -inf 가능

    @classmethod
    def load(cls, path: Path | None = None) -> "FaderTable":
        p = path or Path(__file__).with_name("fader_db.json")
        data = json.loads(p.read_text())
        pts = [(int(r), -math.inf if d is None else float(d)) for r, d in data["points"]]
        pts.sort()
        return cls(points=tuple(pts))

    def _finite(self) -> list[tuple[int, float]]:
        return [(r, d) for r, d in self.points if d != -math.inf]

    def db_to_raw(self, db: float) -> int:
        if math.isnan(db):
            raise ValueError("db is NaN")
        if db == -math.inf:
            return 0
        if db >= MAX_DB:
            return MAX_RAW
        pts = self._finite()
        if db <= pts[0][1]:
            return pts[0][0]
        for (r0, d0), (r1, d1) in zip(pts, pts[1:]):
            if d0 <= db <= d1:
                if d1 == d0:
                    return r0
                return round(r0 + (r1 - r0) * (db - d0) / (d1 - d0))
        return pts[-1][0]

    def raw_to_db(self, raw: int) -> float:
        if raw <= 0:
            return -math.inf
        pts = self._finite()
        if raw <= pts[0][0]:
            return pts[0][1]
        if raw >= pts[-1][0]:
            return pts[-1][1]
        for (r0, d0), (r1, d1) in zip(pts, pts[1:]):
            if r0 <= raw <= r1:
                if r1 == r0:
                    return d0
                return round(d0 + (d1 - d0) * (raw - r0) / (r1 - r0), 1)
        return pts[-1][1]


def parse_db_text(text: str) -> float | None:
    m = _DB_RE.match(text)
    if not m:
        return None
    return -math.inf if m.group(1) == "-oo" else float(m.group(1))


def parse_pan_text(text: str) -> int | None:
    m = _PAN_RE.match(text)
    return int(m.group(1)) if m else None
