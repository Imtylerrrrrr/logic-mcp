"""어사인먼트 모드(PAN·EQ·PLUG-IN·FLIP)를 흉내 내는 가짜 Logic. FakeTransport.replies에 꽂아 쓴다.
2자리 코드·레이아웃은 스펙 2 부록 A 실측을 따르고, 값 모델(틱당 변화·범위)은 단순화했다.
시간은 sleep()으로만 흐른다: 오버레이 재묘사(2.0초 뒤)와 깜박임 위상, 확정 누름의 늦은 뷰 전환(실측 K)이 sleep에서 처리된다.
EQ 버튼은 실측 A처럼 down에 `E_`(메뉴)를, up 뒤에 뷰를 그린다. up의 응답은 deferred에 쌓였다가 드라이버가
기다리기 시작한 뒤(wait_for의 첫 판정 다음)나 다음 sleep·입력 때 도착한다.
lcd_lag(실측 X)의 LCD 값 쓰기는 lagged에 쌓여 sleep으로는 오지 않고, 판정이 안 끝난 wait_for나 다음 입력 때만 도착한다."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from logic_mcp.mcu import protocol as P
from logic_mcp.mcu.surface import Surface
from tests.fakes import FakeTransport

OVERLAY_S = 2.0
LCD_SYSEX = bytes.fromhex("F0 00 00 66 14 12")
MAX = P.MAX_FADER
SLOPES = ("6", "12", "18", "24", "36", "48")
PLUGIN_LIST = ["--", "Parametric EQ", "Low Pass Filter", "High Pass Filter", "Chorus", "Flanger",
               "Compressor", "Channel EQ", "Tuner", "Limiter", "Noise Gate", "Space Designer", "DeEsser"]
ABBREV = {"Parametric EQ": "ParEQ", "Channel EQ": "Cha EQ", "Compressor": "Comprs"}   # PL·Mixer 2행 축약(실측 C·M)


def lcd_write(offset: int, text: str) -> bytes:
    return LCD_SYSEX + bytes([offset]) + text.encode("latin1") + b"\xF7"


def digits(d: str) -> list[bytes]:
    """2자리 표시: CC 0x4B(왼쪽), 0x4A(오른쪽). 문자 코드는 ASCII & 0x3F (protocol.seg_char의 역)."""
    return [bytes([0xB0, 0x4B, ord(d[0].upper()) & 0x3F]), bytes([0xB0, 0x4A, ord(d[1].upper()) & 0x3F])]


def col(text: str) -> str:
    return text[:7].ljust(7)


def fader_echo(ch: int, raw: int) -> bytes:
    return bytes([0xE0 | ch, raw & 0x7F, raw >> 7])


@dataclass
class Param:
    short: str                  # 6자 축약명(열)
    name: str                   # 전체 이름(오버레이)
    kind: str                   # log | linear | enum
    lo: float = 0.0
    hi: float = 1.0
    value: float = 0.0          # enum이면 선택지 인덱스
    options: tuple[str, ...] = ()
    unit: str = ""              # Hz | dB | "" (enum이면 전체 값 접미사, 예 " dB/Oct")
    step: float = 1.0           # 틱당 변화: log면 비율, linear면 가산, enum이면 1
    digits: int = 1             # log 값 반올림 자릿수(Q는 실측 T처럼 3자리 유효숫자에 가깝게 3)

    def text(self) -> str:
        """7칸 열 텍스트. 실측 형식: 20.0Hz / 100 Hz / 1040Hz / 20000 / 0.0 dB / 0.71 / On."""
        if self.kind == "enum":
            return col(self.options[int(self.value)])
        v = self.value
        if self.unit == "Hz":
            s = f"{v:.1f}Hz" if v < 100 else f"{v:.0f} Hz" if v < 1000 else f"{v:.0f}Hz" if v < 10000 else f"{v:.0f}"
        elif self.unit == "dB":
            s = f"{v:.1f} dB"
        elif self.unit == "n1":                      # 단위 없는 소수 1자리(실측 W: Thrs `-20.0`)
            s = f"{v:.1f}"
        elif self.unit in ("ms", "%"):
            s = f"{v:.1f}{self.unit}"
        elif self.unit == ":1":
            s = f"{v:.1f}:1"
        else:
            s = f"{v:.2f}"
        return col(s)

    def full(self) -> str:
        """오버레이 전체 값(단위 포함)."""
        if self.kind == "enum":
            return self.options[int(self.value)] + self.unit
        if self.unit == "Hz":
            return f"{self.value:.1f} Hz"
        if self.unit == "dB":
            return f"{self.value:+.1f} dB"
        return f"{self.value:.2f}"

    def raw(self) -> int:
        if self.kind == "enum":
            return round(MAX * self.value / max(1, len(self.options) - 1))
        if self.kind == "log":
            return round(MAX * math.log(self.value / self.lo) / math.log(self.hi / self.lo))
        return round(MAX * (self.value - self.lo) / (self.hi - self.lo))

    def set_raw(self, raw: int) -> bool:
        """페이더 위치 → 값. 바뀌었으면 True(Logic은 바뀔 때만 에코)."""
        before = self.value
        f = max(0, min(MAX, raw)) / MAX
        if self.kind == "enum":
            self.value = round(f * (len(self.options) - 1))
        elif self.kind == "log":
            self.value = round(self.lo * (self.hi / self.lo) ** f, self.digits)
        else:
            self.value = round(self.lo + f * (self.hi - self.lo), 2)
        return self.value != before

    def tick(self, n: int) -> None:
        if self.kind == "enum":
            self.value = max(0, min(len(self.options) - 1, self.value + n))
        elif self.kind == "log":
            self.value = round(max(self.lo, min(self.hi, self.value * self.step ** n)), self.digits)
        else:
            self.value = round(max(self.lo, min(self.hi, self.value + self.step * n)), 2)


_EQ_BANDS = [  # (이름, (freq, gain|slope, q, on) 축약, 기본 freq, 기본 gain|slope, 기본 q, 기본 on, 슬로프 밴드?)
    ("Low Cut", ("LoCutF", "LoCutS", "LoCutQ", "LCO/Of"), 20.0, 12, 0.71, False, True),
    ("Low Shelf", ("LoShF", "LoShGa", "LoShQ", "LSO/Of"), 75.0, 0.0, 1.00, True, False),
    ("Peak 1", ("Peak1F", "Pea1Ga", "Peak1Q", "Pe1On/"), 100.0, 0.0, 0.60, True, False),
    ("Peak 2", ("Peak2F", "Pea2Ga", "Peak2Q", "Pe2On/"), 250.0, 0.0, 0.30, True, False),
    ("Peak 3", ("Peak3F", "Pea3Ga", "Peak3Q", "Pe3On/"), 1040.0, 0.0, 0.41, True, False),
    ("Peak 4", ("Peak4F", "Pea4Ga", "Peak4Q", "Pe4On/"), 2500.0, 0.0, 0.20, True, False),
    ("High Shelf", ("HiShF", "HiShGa", "HiShQ", "HSO/Of"), 7500.0, 0.0, 1.00, True, False),
    ("High Cut", ("HiCutF", "HiCutS", "HiCutQ", "HCO/Of"), 20000.0, 24, 0.71, False, True),
]


def channel_eq() -> list[list[Param]]:
    """8밴드 × (freq, gain|slope, q, on). 축약명은 밴드 1~6 실측, 7·8은 같은 규칙으로 지었다."""
    bands = []
    for name, (f, g, q, o), freq, gain, qv, on, is_slope in _EQ_BANDS:
        gp = (Param(g, f"{name} Slope", "enum", options=SLOPES, value=SLOPES.index(str(gain)), unit=" dB/Oct")
              if is_slope else Param(g, f"{name} Gain", "linear", -24.0, 24.0, gain, unit="dB", step=0.5))
        bands.append([Param(f, f"{name} Frequency", "log", 20.0, 20000.0, freq, unit="Hz", step=1.08), gp,
                      Param(q, f"{name} Q", "log", 0.10, 100.0, qv, step=1.06, digits=3),  # 실측 T·U: log 0.10~100, 틱당 ×≈1.06
                      Param(o, f"{name} On/Off", "enum", options=("Off", "On"), value=1 if on else 0)])
    return bands


def channel_eq_edit(bands: list[list[Param]]) -> list[Param]:
    """편집 뷰 순서(실측: 1페이지 슬로프/게인, 2페이지 주파수 …). 같은 Param 객체를 공유한다."""
    flat = [b[1] for b in bands] + [b[0] for b in bands] + [b[2] for b in bands] + [b[3] for b in bands]
    flat += [Param("Analyz", "Analyzer", "enum", options=("Off", "On"), value=0),
             Param("MasGai", "Master Gain", "linear", -24.0, 24.0, 0.0, unit="dB", step=0.5)]
    return flat


def compressor() -> list[Param]:
    """Compressor 실측 모델(W): 20개, 축약명·기본 표시는 Logic Pro 12.0.1 그대로(페이지 3은 오른쪽 정렬로 13~20)."""
    return [Param("CirTyp", "Circuit Type", "enum", options=("PltDig", "StdVCA", "StdFET", "ClsVCA"), value=0),
            Param("Thrs", "Threshold", "linear", -60.0, 0.0, -20.0, unit="n1", step=0.5),
            Param("Ratio", "Ratio", "linear", 1.0, 30.0, 2.1, unit=":1", step=0.1),
            Param("Attack", "Attack", "linear", 0.0, 200.0, 15.0, unit="ms", step=1.0),
            Param("Rel", "Release", "linear", 5.0, 5000.0, 51.0, unit="ms", step=5.0),
            Param("AutRel", "Auto Release", "enum", options=("Off", "On"), value=1),
            Param("MakeUp", "Make Up", "linear", -12.0, 40.0, 0.0, unit="dB", step=0.5),
            Param("AutGai", "Auto Gain", "enum", options=("Off", "-12dB", "0dB"), value=1),
            Param("Knee", "Knee", "linear", 0.0, 1.0, 0.7, unit="n1", step=0.05),
            Param("Peak/S", "Peak/RMS", "enum", options=("Peak", "RMS"), value=1),
            Param("LimrOn", "Limiter", "enum", options=("Off", "On"), value=0),
            Param("LimThr", "Limiter Threshold", "linear", -20.0, 20.0, 0.0, unit="dB", step=0.5),
            Param("Distrt", "Distortion", "enum", options=("Off", "Soft", "Hard"), value=0),
            Param("Mix", "Mix", "linear", 0.0, 100.0, 100.0, unit="%", step=1.0),
            Param("SiChDe", "Side Chain Detect", "enum", options=("Off", "Max"), value=1),
            Param("State", "Side Chain State", "enum", options=("Off", "On"), value=0),
            Param("Mode", "Filter Mode", "enum", options=("LP", "HP", "BP"), value=0),
            Param("Freq", "Filter Frequency", "linear", 20.0, 20000.0, 7040.0, unit="n1", step=10.0),
            Param("Q", "Filter Q", "linear", 0.1, 10.0, 1.0, step=0.05),
            Param("Gain", "Filter Gain", "linear", -24.0, 24.0, 0.0, unit="dB", step=0.5)]


def generic(name: str) -> list[Param]:
    """그 밖의 플러그인: Distortion 실측(Drive/Tone/Output) 모양."""
    return [Param("Drive", f"{name} Drive", "linear", 0.0, 10.0, 10.0, step=0.1),
            Param("Tone", f"{name} Tone", "linear", 0.0, 2000.0, 1100.0, step=10.0),
            Param("Output", f"{name} Output", "linear", -20.0, 20.0, -0.5, unit="dB", step=0.5)]


@dataclass
class Track:
    number: int
    name: str
    inserts: dict[int, str | None] = field(default_factory=lambda: {i: None for i in range(1, 16)})
    params: dict[int, list[Param]] = field(default_factory=dict)   # 슬롯 → 편집 뷰 파라미터
    eq: list[list[Param]] | None = None                           # Channel EQ 밴드(어느 슬롯에 있든)
    bypassed: set[int] = field(default_factory=set)
    eq_page: int = 1                                              # EQ 채널 뷰가 기억하는 마지막 페이지(실측 Q)

    def insert(self, slot: int, name: str) -> None:
        if self.inserts[slot] == "Channel EQ":
            self.eq = None
        self.inserts[slot] = name
        if name == "Channel EQ":
            self.eq = channel_eq()
            self.params[slot] = channel_eq_edit(self.eq)
        elif name == "Compressor":
            self.params[slot] = compressor()
        else:
            self.params[slot] = generic(name)

    def remove(self, slot: int) -> None:
        if self.inserts[slot] == "Channel EQ":
            self.eq = None
        self.inserts[slot] = None
        self.params.pop(slot, None)
        self.bypassed.discard(slot)

    def first_empty(self) -> int | None:
        return next((i for i in range(1, 16) if self.inserts[i] is None), None)


class FakeLogic:
    def __init__(self, fake: FakeTransport, tracks: list[Track], clock) -> None:
        self.fake, self.tracks, self.clock = fake, tracks, clock
        self.view = "pan"
        self.selected = 0
        self.slot = 1
        self.page = 1
        self.flip = False
        self.name_mode = False
        self.shift = False
        self.blink_on = True
        self.mode_note = P.Note.PAN
        self.before_midi = "plugin_mixer"
        self.pre: dict[int, int] = {}                  # V-Pot → 미리 선택 틱 위치(0 = `--`, 0..2·(목록-1)로 포화)
        self.pending: list[float] = []                 # 재묘사 예정 시각
        self.timers: list[tuple[float, object]] = []   # (시각, 할 일): 확정 누름 ≈2초 뒤 편집 뷰(실측 K)
        self.deferred: list = []                       # 드라이버가 기다리기 시작한 뒤 도착할 응답(EQ up)
        self.eq_held = False                           # EQ 버튼 down 중: 2자리 `E_`(실측 A)
        self.plugin_list = list(PLUGIN_LIST)
        self.lcd_lag = False                           # True면 페이더 이동의 LCD 값 쓰기가 에코보다 늦게 도착(실측 X)
        self.lagged: list = []                         # lcd_lag 응답: sleep·입력으로는 안 오고, 드라이버가 판정 안 된 wait_for에 들어가야 도착
        self.refuse: set[int] = set()                  # 반응하지 않을 노트(고장 흉내)
        fake.replies = self.replies

    # ---------- 시간 ----------
    def sleep(self, s: float) -> None:
        """드라이버의 sleep 훅. 시간을 보내고, 만기된 재묘사와 깜박임 위상을 처리한다."""
        self.flush()
        self.fake.now += s
        self.blink_on = not self.blink_on
        for t, fn in [x for x in self.timers if x[0] <= self.clock()]:
            self.timers.remove((t, fn))
            fn()
        due = [t for t in self.pending if t <= self.clock()]
        if due:
            self.pending = [t for t in self.pending if t > self.clock()]
            self.redraw()
        elif self.pre and self.view in ("plugin_mixer", "plugin_channel") and not self.pending:   # 오버레이 유효 중엔 깜박임 재묘사로 덮지 않음
            self.redraw()

    def flush(self) -> None:
        """미뤄 둔 응답을 지금 보낸다."""
        while self.deferred:
            self.deferred.pop(0)()

    def flush_lagged(self) -> None:
        while self.lagged:
            self.lagged.pop(0)()

    def boot(self) -> None:
        self._emit([P.button_down(P.Note.PAN), P.button_down(P.Note.BEATS_LED), P.button_down(P.Note.SELECT)])
        self._emit([fader_echo(ch, 12443) for ch in range(8)])
        self.redraw()

    # ---------- 화면 ----------
    def _emit(self, msgs: list[bytes]) -> None:
        for m in msgs:
            self.fake.on_message(self.clock(), m)

    def _track(self, ch: int) -> Track | None:
        return self.tracks[ch] if ch < len(self.tracks) else None

    def _names_row(self) -> str:
        return "".join(col(f"{t.number}:{t.name}") for t in self.tracks[:8]).ljust(56)

    def _slot_digits(self) -> str:
        return f"P{self.slot}" if self.slot <= 9 else str(self.slot)

    def _abbrev(self, name: str | None, slot: int, track: Track) -> str:
        if name is None:
            return col("--")
        short = ABBREV.get(name) or name.replace(" ", "")[:6]
        return col("*" + short[:5] if slot in track.bypassed else short)     # 바이패스: `*` + 5자(실측 N)

    def _pre_index(self, ch: int) -> int:
        return (self.pre[ch] + 1) // 2                          # ceil 모델: 1항목 = 2틱, 홀수 틱은 다음 항목(실측 E)

    def _pre_cell(self, ch: int, fallback: str) -> str:
        """미리 선택 중인 열: 깜박이는 축약."""
        if ch not in self.pre:
            return fallback
        return self._abbrev(self.plugin_list[self._pre_index(ch)], 0, self.tracks[self.selected]) if self.blink_on else col("")

    def _edit_params(self) -> list[Param]:
        return self.tracks[self.selected].params.get(self.slot, [])

    def _edit_pages(self) -> int:
        return max(1, math.ceil(len(self._edit_params()) / 8))

    def _edit_page(self) -> list[Param]:
        """편집 뷰 열. 마지막 페이지는 오른쪽 정렬: N % 8 != 0이면 항목 N-8..N-1을 보인다(실측 W)."""
        ps, pages = self._edit_params(), self._edit_pages()
        if self.page == pages and pages > 1 and len(ps) % 8:
            return ps[len(ps) - 8:]
        return ps[(self.page - 1) * 8:self.page * 8]

    def _column_param(self, ch: int) -> Param | None:
        t = self.tracks[self.selected]
        if self.view == "eq_channel" and t.eq is not None:
            ps = [p for band in t.eq[2 * self.page - 2:2 * self.page] for p in band]
            return ps[ch] if ch < len(ps) else None
        if self.view == "plugin_edit":
            ps = self._edit_page()
            return ps[ch] if ch < len(ps) else None
        return None

    def _rows(self) -> tuple[str, str, str]:
        """정착 화면 (1행, 2행, 2자리)."""
        t = self.tracks[self.selected]
        if self.view == "pan":
            return self._names_row(), "".join(col("0") for _ in self.tracks[:8]).ljust(56), "PN"
        if self.view == "eq_mixer":
            r2 = "".join(tr.eq[0][0].text() if tr.eq else col("") for tr in self.tracks[:8]).ljust(56)
            return self._names_row(), r2, "E1"
        if self.view == "eq_channel":
            ps = [p for band in t.eq[2 * self.page - 2:2 * self.page] for p in band]
            return "".join(col(p.short) for p in ps).ljust(56), "".join(p.text() for p in ps).ljust(56), "EQ"
        if self.view == "plugin_mixer":
            cells = [self._pre_cell(ch, self._abbrev(tr.inserts[self.slot], self.slot, tr))
                     for ch, tr in enumerate(self.tracks[:8])]
            return self._names_row(), "".join(cells).ljust(56), self._slot_digits()
        if self.view == "plugin_channel":                       # 선택 트랙의 슬롯 1~8(실측 C)
            r1 = "".join(col(f"Ins{i}Pl") for i in range(1, 9))
            r2 = "".join(self._pre_cell(i - 1, self._abbrev(t.inserts[i], i, t)) for i in range(1, 9))
            return r1, r2, "PL"
        if self.view == "plugin_edit":
            ps = self._edit_page()
            names = "".join(col(p.short) for p in ps).ljust(56)
            if self.name_mode:
                return self._header(t), names, self._slot_digits()
            return names, "".join(p.text() for p in ps).ljust(56), self._slot_digits()
        if self.view in ("empty_edit", "midi_fx"):
            return "-      " * 8, " " * 56, "M1" if self.view == "midi_fx" else self._slot_digits()
        raise AssertionError(self.view)

    def _header(self, t: Track) -> str:
        """NAME 모드 1행(56칸). 짧으면 `Page n/N`이 오른쪽에 보인다. 길면 1페이지는 56칸에서 잘려 Page가 안 보이고,
        2페이지부터는 이름이 잘리고 `Page n/N `이 보인다(실측 G·L)."""
        prefix = f'Track {t.number} "{t.number}:{t.name}" Ins.{self.slot} "'
        full = prefix + f'{t.inserts[self.slot]} (s/s)"'
        page = f"Page {self.page}/{self._edit_pages()}"
        if len(full) <= 48:
            return full.ljust(48) + page.rjust(8)
        if self.page == 1:
            return (full + " " + page)[:56]
        tail = page + " "
        return (prefix + t.inserts[self.slot])[:56 - len(tail) - 5].ljust(56 - len(tail)) + tail

    def redraw(self, overlay: tuple[int, str, str] | None = None, mode_overlay: str | None = None) -> None:
        """정착 화면을 그린다. 오버레이가 있으면 오버레이 판을 지금 그리고 2.0초 뒤 재묘사를 예약한다."""
        r1, r2, d = self._rows()
        if self.eq_held:
            d = "E_"
        if overlay is None and mode_overlay is None:
            self._emit([lcd_write(0, r1 + r2)] + digits(d))
            return
        o1, o2 = r1, r2
        if mode_overlay:
            o1 = r1[:56 - len(mode_overlay)] + mode_overlay
        if overlay:
            ch, name, value = overlay
            start = min(ch * 7, 56 - 21)
            fit = (lambda s: s[:20].rjust(20) + " ") if ch >= 6 else (lambda s: s[:21].ljust(21))   # 7·8: 오른쪽 정렬 + 끝 공백(실측 D)
            o1 = o1[:start] + fit(name) + o1[start + 21:]
            o2 = r2[:start] + fit(value) + r2[start + 21:]
        self._emit([lcd_write(0, o1[:56] + o2[:56])] + digits(d))
        self.pending = [self.clock() + OVERLAY_S]           # 새 오버레이가 이전 만기를 대체한다(마지막 쓰기 뒤 2.0초)

    # ---------- 입력 ----------
    def replies(self, data: bytes) -> list[bytes]:
        self.flush()
        st = data[0] & 0xF0
        if st == 0x90:
            note, on = data[1], data[2] != 0
            if note in self.refuse:
                return []
            if note == P.Note.SHIFT:
                self.shift = on
            elif note == P.Note.EQ:                              # 실측 A: down → `E_`, up 뒤 50 ms 안에 뷰
                self.eq_held = on
                if on:
                    self._emit(digits("E_"))
                else:
                    self.deferred.append(lambda: self._button(P.Note.EQ))
            elif on:
                self._button(note)
        elif st == 0xB0 and 0x10 <= data[1] <= 0x17:
            v = data[2]
            self._vpot(data[1] - 0x10, (v & 0x3F) * (-1 if v & 0x40 else 1))
        elif st == 0xE0 and (data[0] & 0x0F) < 8:
            self._fader(data[0] & 0x0F, data[1] | (data[2] << 7))
        return []

    def _set_mode(self, view: str, note: int) -> None:
        if self.mode_note != note:
            self._emit([P.button_up(self.mode_note), P.button_down(note)])
            self.mode_note = note
        self.view, self.page = view, 1
        self.pre.clear()

    def _button(self, note: int) -> None:
        N = P.Note
        if N.SELECT <= note < N.SELECT + 8:
            old, self.selected = self.selected, note - N.SELECT
            self._emit([P.button_up(N.SELECT + old), P.button_down(N.SELECT + self.selected)])
            self.pre.clear()
            self.redraw()
        elif note == N.PAN:
            self._set_mode("pan", N.PAN)
            self.redraw(mode_overlay="    Pan/Surround parameter:")
        elif note == N.EQ:
            if self.view == "eq_mixer":
                t = self.tracks[self.selected]
                if t.eq is None and t.first_empty():
                    t.insert(t.first_empty(), "Channel EQ")      # 실측: 채널 뷰 진입이 Channel EQ 삽입
                self.view, self.page = "eq_channel", t.eq_page
                self.redraw()
            elif self.view == "eq_channel":
                self.view = "eq_mixer"
                self.redraw(mode_overlay=" EQ 1 Parameter: Low Cut Frequency")
            else:
                self._set_mode("eq_mixer", N.EQ)
                self.redraw(mode_overlay=" EQ 1 Parameter: Low Cut Frequency")
        elif note == N.PLUGIN:
            if self.view == "plugin_mixer":
                self.view = "plugin_channel"
            elif self.view in ("plugin_channel", "plugin_edit", "empty_edit", "midi_fx"):
                self.view = "plugin_mixer"
            else:
                self._set_mode("plugin_mixer", N.PLUGIN)
            self.pre.clear()
            self.redraw()
        elif note == N.CURSOR_RIGHT:
            self._page(+1)
        elif note == N.CURSOR_LEFT:
            self._page(-1)
        elif note == N.CURSOR_DOWN:
            self._slot(+1)
        elif note == N.CURSOR_UP:
            self._slot(-1)
        elif note == N.FLIP:
            self.flip = not self.flip
            self._emit([P.button_down(N.FLIP) if self.flip else P.button_up(N.FLIP)])
            if self.flip:
                self._emit([fader_echo(ch, p.raw() if (p := self._column_param(ch)) else 0) for ch in range(8)])
            else:
                self._emit([fader_echo(ch, 12443) for ch in range(8)])
        elif note == N.NAME_VALUE:
            self.name_mode = not self.name_mode
            self.redraw()
        elif N.VPOT_PUSH <= note < N.VPOT_PUSH + 8:
            self._push(note - N.VPOT_PUSH)

    def _page(self, delta: int) -> None:
        old = self.page
        if self.view == "eq_channel":
            self.page = max(1, min(4, self.page + delta))      # 양 끝에서는 무반응(LCD 변화 없음, 실측 Q)
            if self.page == old:
                return
            self.tracks[self.selected].eq_page = self.page
        elif self.view == "plugin_edit":
            self.page = max(1, min(self._edit_pages(), self.page + delta))
        else:
            return
        self.redraw()

    def _slot(self, delta: int) -> None:
        """편집 뷰의 커서 ▲▼(스파이크 실측). Plug-in Mixer·Channel 뷰에서는 무반응(실측 B·C)."""
        if self.view == "midi_fx":
            if delta > 0:
                self.view, self.slot = self.before_midi, 1
        elif self.view in ("plugin_edit", "empty_edit"):
            new = self.slot + delta
            if new < 1:
                self.before_midi, self.view = self.view, "midi_fx"      # 실측: P1에서 ▲ → M1
            else:
                self.slot = min(15, new)
                if self.view in ("plugin_edit", "empty_edit"):
                    self.view = "plugin_edit" if self.tracks[self.selected].inserts[self.slot] else "empty_edit"
                    self.page = 1
        else:
            return
        self.redraw()

    def _preselect(self, ch: int, current: str | None, slot: int, ticks: int) -> None:
        """미리 선택 틱. 차 있는 슬롯의 시작 위치는 2·항목(-1 → 현재 항목, +1 → 다음 항목, 실측 E)."""
        if ch not in self.pre:                                          # 실측: 다른 V-Pot의 미리 선택은 취소됨
            self.pre = {ch: 2 * self.plugin_list.index(current or "--")}
        self.pre[ch] = max(0, min(2 * (len(self.plugin_list) - 1), self.pre[ch] + ticks))
        name = self.plugin_list[self._pre_index(ch)]
        self.redraw(overlay=(ch, f"Insert {slot} Plug-in", name if name == "--" else f"{name} (s/s)"))

    def _vpot(self, ch: int, ticks: int) -> None:
        if self.view == "plugin_mixer":
            t = self._track(ch)
            if t is None:
                return
            self._preselect(ch, t.inserts[self.slot], self.slot, ticks)
            return
        if self.view == "plugin_channel":                               # V-Pot n = 슬롯 n(실측 D)
            self._preselect(ch, self.tracks[self.selected].inserts[ch + 1], ch + 1, ticks)
            return
        if self.view == "eq_mixer":
            t = self._track(ch)
            p = t.eq[0][0] if (t and t.eq) else None
        else:
            p = self._column_param(ch)
        if p is None:
            return
        p.tick(ticks)
        self.redraw(overlay=(ch, p.name, p.full()))

    def _push(self, ch: int) -> None:
        if self.view == "plugin_channel":
            self._push_channel(ch)
            return
        if self.view != "plugin_mixer":
            return                                                      # 실측: 편집 뷰 누름은 기본값 리셋 안 함
        t = self._track(ch)
        if t is None:
            return
        if self.shift:
            t.bypassed ^= {self.slot}
            self.redraw()
            return
        if ch in self.pre:
            name = self.plugin_list[self._pre_index(ch)]
            self.pre.clear()
            self.selected = ch
            if name == "--":
                t.remove(self.slot)
                self.view = "empty_edit"
            else:
                if name != t.inserts[self.slot]:
                    t.insert(self.slot, name)                           # 같은 플러그인 확인은 값 보존(실측)
                self.view, self.page = "plugin_edit", 1
            self.redraw()
        elif t.inserts[self.slot]:
            self.selected = ch
            self.view, self.page = "plugin_edit", 1
            self.redraw()

    def _push_channel(self, ch: int) -> None:
        """PL에서 V-Pot n 누름. SHIFT면 바이패스 토글(실측 N). 미리 선택이 있으면 확정 → ≈2초 뒤 편집 뷰(실측 K),
        없으면 차 있는 슬롯은 곧바로 값 보존 편집 뷰, 빈 슬롯은 무반응(실측 F)."""
        t, slot = self.tracks[self.selected], ch + 1
        if self.shift:
            t.bypassed ^= {slot}
            self.redraw()
            return
        if ch in self.pre:
            name = self.plugin_list[self._pre_index(ch)]
            self.pre.clear()

            def commit() -> None:
                self.slot, self.page = slot, 1
                if name == "--":
                    t.remove(slot)
                    self.view = "empty_edit"
                else:
                    if name != t.inserts[slot]:
                        t.insert(slot, name)
                    self.view = "plugin_edit"
                self.redraw()
            self.timers.append((self.clock() + OVERLAY_S, commit))
        elif t.inserts[slot]:
            self.slot, self.page = slot, 1
            self.view = "plugin_edit"
            self.redraw()

    def _fader(self, ch: int, raw: int) -> None:
        if not self.flip or raw == 0:                                   # raw 0 무시(실측 사례)
            return
        p = self._column_param(ch)
        if p is None or not p.set_raw(raw):
            return
        self._emit([fader_echo(ch, p.raw())])
        if self.lcd_lag:
            self.lagged.append(lambda: self.redraw(overlay=(ch, p.name, p.full())))
        else:
            self.redraw(overlay=(ch, p.name, p.full()))


def default_tracks() -> list[Track]:
    return [Track(15, "DCl"), Track(16, "DCl"), Track(17, "DCl"), Track(18, "DCl"),
            Track(19, "DCl"), Track(20, "DCl"), Track(21, "SOu"), Track(24, "Mas")]


def make_assign_logic(tracks: list[Track] | None = None) -> tuple[Surface, FakeTransport, FakeLogic]:
    fake = FakeTransport()
    surface = Surface(fake, clock=lambda: fake.now + 1.0, tick_interval=0.01)
    logic = FakeLogic(fake, tracks or default_tracks(), surface.clock)
    logic.boot()
    wait_for = surface.wait_for

    def late_wait_for(pred, timeout: float) -> bool:
        """미뤄 둔 응답은 첫 판정 뒤에 도착한다(실측 A의 `E_` → E1 순서를 드라이버가 기다려야 함)."""
        if logic.deferred and not pred(surface.state):
            logic.flush()
        if logic.lagged and not pred(surface.state):
            logic.flush_lagged()
        return wait_for(pred, timeout)
    surface.wait_for = late_wait_for
    fake.now += 1.0                 # 조용 1초 → ready
    surface.tick()
    assert surface.state.connection.state == "ready"
    return surface, fake, logic
