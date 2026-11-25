"""플러그인 뷰의 LCD를 읽는 상수와 순수 함수(상태 없음). plugin.py·plugin_mixer.py·plugins/calibrate.py가 같이 쓴다."""
from __future__ import annotations

import re

from ...mcu import state as S
from ..modes import OVERLAY_WIDTH, overlay_start
from .match import strip_suffix

MAX_SLOT = 8            # 2a는 Plug-in Channel 뷰(PL)의 슬롯 1~8만(실측 C: 9~15 접근 경로 미확인)
EMPTY_TEXTS = ("", "--")  # PL·Mixer 2행에서 빈 슬롯(`--` 또는 갱신 전 공백, 실측 C·H)
EMPTY_SHORTS = ("", "-")  # 편집 뷰 빈 파라미터 칸(공백 또는 1행 `-`, 실기 10차: Adaptive Limiter·Overdrive·Distortion)
_HEADER_RE = re.compile(r'Ins\.(\d+) "([^"]*)("?)')
_TRACK_RE = re.compile(r"\s*Track\s+(\d+)")
_PAGE_TAIL_RE = re.compile(r"\s*Page\s*\d+/\d+.*$")


def _header_name(row1: str) -> tuple[int | None, str, bool]:
    """NAME 모드 1행 → (인서트 번호, 이름, 닫는 따옴표까지 보였는지). 56자 잘림으로 따옴표·`(s/s)`·Page가
    빠지거나 이름이 잘릴 수 있다(실측 G·L)."""
    m = _HEADER_RE.search(row1)
    if not m:
        return None, "", False
    text = _PAGE_TAIL_RE.sub("", m.group(2))
    return int(m.group(1)), strip_suffix(text).rstrip(" ("), m.group(3) == '"'


def _header_track(row1: str) -> int | None:
    """NAME 모드 1행 맨 앞 `Track <n>`의 n(실측 G). 편집 뷰는 채널 뷰가 따라가는 트랙을 보여 준다(실전 F2)."""
    m = _TRACK_RE.match(row1)
    return int(m.group(1)) if m else None


def pair_columns(shorts: list[str], cols: list[str]) -> list[tuple[int, str, str]]:
    """NAME 행 축약명(strip)과 VALUE 행 원문(7칸) → (열, 축약명, 값 텍스트). 두 열을 쓰는 파라미터(실기 11/11 Silver Compressor
    `Thresho`|`ld`, Distortion II·Parametric EQ 값 `12000 H`|`z`)는 하나로 잇는다: 축약명이 열을 꽉 채우고(7자) 다음 열에
    축약명이 있으면 이름을 잇고, 값이 열을 꽉 채우고(7자, 구분 공백 없음) 다음 열 값이 있으면 값도 잇는다(리뷰 M1).
    값만 넘치고 다음 열 축약명이 비어 있을 때도 값은 잇는다. 뒤 열은 항목을 만들지 않는다."""
    out, i = [], 0
    while i < len(shorts):
        short, text, width = shorts[i], cols[i], 1
        nxt = i + 1 < len(shorts)
        name_spills = len(short) == S.COL_W and nxt and shorts[i + 1] not in EMPTY_SHORTS
        value_spills = len(cols[i].rstrip()) == S.COL_W and nxt and cols[i + 1].strip() != ""
        if name_spills:
            short, width = short + shorts[i + 1], 2
        if value_spills and (name_spills or shorts[i + 1] in EMPTY_SHORTS):
            text, width = cols[i] + cols[i + 1], 2
        out.append((i, short, text))
        i += width
    return out


def overlay_param_name(header: str, row: str, col: int) -> str:
    """편집 뷰 1행에서 파라미터 전체 이름만 떼어 낸다. header = 틱 전 1행(축약명), row = 틱 뒤 1행(오버레이를 덧쓴 상태).
    이름은 해당 열부터 2열(길면 3열) 폭으로만 덧쓰이고 나머지 칸은 축약명이 남는다(실기 10차). 창은 min(col*7, 56-21)부터
    3칸(7자 단위): 대상 열 앞 칸은 바뀌었을 때만, 대상 열 칸은 항상 넣고, 그 뒤 칸은 바뀌지 않은 첫 칸부터 버린다.
    이어 붙여 strip. 아무것도 안 바뀌면 ""."""
    w = S.COL_W
    first = overlay_start(col) // w
    cells = [(c, row[c * w:(c + 1) * w], row[c * w:(c + 1) * w] != header[c * w:(c + 1) * w])
             for c in range(first, first + OVERLAY_WIDTH // w)]
    if not any(changed for _c, _t, changed in cells):
        return ""
    parts = []
    for c, text, changed in cells:
        if c > col and not changed:
            break
        if c >= col or changed:
            parts.append(text)
    return "".join(parts).strip()
