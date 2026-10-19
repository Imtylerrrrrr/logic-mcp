"""어사인먼트 모드(PAN·EQ·PLUG-IN·FLIP)를 흉내 내는 가짜 Logic. FakeTransport.replies에 꽂아 쓴다.
2자리 코드·레이아웃은 스펙 2 부록 A 실측을 따르고, 값 모델(틱당 변화·범위)은 단순화했다.
시간은 sleep()으로만 흐른다: 오버레이 재묘사(2.0초 뒤)와 깜박임 위상, 확정 누름의 늦은 뷰 전환(실측 K)이 sleep에서 처리된다.
EQ 버튼은 실측 A처럼 down에 `E_`(메뉴)를, up 뒤에 뷰를 그린다. up의 응답은 deferred에 쌓였다가 드라이버가
기다리기 시작한 뒤(wait_for의 첫 판정 다음)나 다음 sleep·입력 때 도착한다.
lcd_lag(실측 X)의 LCD 값 쓰기는 lagged에 쌓여 sleep으로는 오지 않고, 판정이 안 끝난 wait_for나 다음 입력 때만 도착한다.
drop_first_fader(실측 Z1)는 Flip을 켠 뒤 처음 오는 페이더 이동을, drop_first_flip(실측 Z2)은 처음 FLIP 누름을 한 번 무시한다.
drop_all_faders는 페이더 이동을 항상 무시한다(반응 없는 Logic).
flip_led_lag(리뷰 C1)는 처음 처리된 FLIP 누름의 LED 변화를 flip_lagged에 쌓아 두었다가, 드라이버가 FLIP LED 대기에서 한 번
시간 초과한 뒤 다음 판정 거짓 wait_for에 들어갈 때 보낸다. Flip이 꺼진 상태의 페이더 이동은 해당 스트립 트랙 볼륨(Track.volume, raw)을 바꾼다.
drop_all_flips는 FLIP 누름을 항상, drop_all_name_value는 NAME/VALUE 누름을 항상 무시한다.
name_value_lag(실기 10차)는 NAME/VALUE 누름의 1행 쓰기는 바로 보내고 2행 쓰기는 lagged에 쌓는다(lcd_lag와 같은 도착 규칙).
value_row_partial(재수집 근사)은 VALUE 전환의 2행 중 열 0만 바로 쓰고 열 1~7은 lagged에 쌓는다: 토글의 2행 변화 판정은 참이 되지만
대상 열은 아직 축약명이다. stale_value_cols의 열은 VALUE 전환 뒤에도 2행에 축약명이 남아 다음 재묘사(틱 등)에서야 값이 된다.
no_overlay_on_nochange는 값이 끝에 닿아 바뀌지 않은 파라미터 틱에 LCD를 그리지 않는다(리뷰 I3, 실기 미측정).
narrow_name_overlay(실기 10차)는 틱 이름 오버레이를 1행 해당 열부터 2열(이름이 길면 3열) 폭으로만 덧쓰고 나머지 1행 칸은 축약명을 남긴다.
refuse에 V-Pot 누름 노트를 넣으면 누름이 드롭되어 미리 선택이 계속 깜박인다(리뷰 I2, 실측 S4).
late_preselect_items의 목록 항목은 처음 닿은 틱에 이전 항목 오버레이를 다시 그리고, LATE_PRESELECT_S 뒤 sleep에서야 제 이름을 그린다
(재수집: 스캔에서 빠진 Rotor Cabinet·Fuzz Machine). 한 번 그린 항목은 집합에서 빠진다.
미리 선택이 목록 끝에 클램프되어 위치가 그대로면 LCD를 그리지 않는다(실측 scan_diag). drop_preselect_at의 위치(`--`에서 센 틱 위치)에
닿은 틱은 오버레이 쓰기를 빠뜨린다(늦는 게 아니라 안 옴, 실측 scan_diag 27번 위치)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from logic_mcp.mcu.surface import Surface
from tests.fakes import FakeTransport

OVERLAY_S = 2.0
LATE_PRESELECT_S = 0.5      # 틱 뒤 조용 대기(TICK_QUIET_S 0.4초)보다 늦게
LCD_SYSEX = bytes.fromhex("F0 00 00 66 14 12")
MAX = P.MAX_FADER
SLOPES = ("6", "12", "18", "24", "36", "48")
PLUGIN_LIST = ["--", "Parametric EQ", "Low Pass Filter", "High Pass Filter", "Chorus", "Flanger",
               "Compressor", "Channel EQ", "Tuner", "Limiter", "Noise Gate", "Space Designer", "DeEsser"]
ABBREV = {"Parametric EQ": "ParEQ", "Channel EQ": "Cha EQ", "Compressor": "Comprs"}   # PL·Mixer 2행 축약(실측 C·M)

DEST_LIST = ["--", "1", "2"] + [f"Bus {i}" for i in range(1, 9)]   # 실측 S4: 앞의 `1`, `2`는 정체 미확인, 1틱 = 1항목
POS_COL = ("Pre", "Post", "PosPan")                                 # 정착 열(실측 S8)
POS_FULL = ("Pre", "Post", "Post Pan")                              # 오버레이
SEND_MENU = "Dest   Level  Pos    Mute   CStrip CStr2  Ds/LvM Ds/LvC "
FADERS = FaderTable.load()
LEVEL_FLOOR = -96.0                                                  # 이 아래는 `-oodB`


def lcd_write(offset: int, text: str) -> bytes:
    return LCD_SYSEX + bytes([offset]) + text.encode("latin1") + b"\xF7"


def digits(d: str) -> list[bytes]:
    """2자리 표시: CC 0x4B(왼쪽), 0x4A(오른쪽). 문자 코드는 ASCII & 0x3F (protocol.seg_char의 역)."""
    return [bytes([0xB0, 0x4B, ord(d[0].upper()) & 0x3F]), bytes([0xB0, 0x4A, ord(d[1].upper()) & 0x3F])]

TRACK_MENU = ["Volume", "Pan", "TrkFmt", "Input", "Output", "Auto", "DisplP", "Setup"]   # TRACK 홀드 메뉴(실측 Z5)


def col(text: str) -> str:
    return text[:7].ljust(7)


def fader_echo(ch: int, raw: int) -> bytes:
    return bytes([0xE0 | ch, raw & 0x7F, raw >> 7])


@dataclass
class Send:
    dest: str                   # `Bus 2`
    level: float = float("-inf")
    pos: int = 2                # 0 Pre, 1 Post, 2 Post Pan (새 센드 기본 Post Pan, 실측 S5)
    muted: bool = False

    def level_col(self) -> str:
        return col("-oodB" if self.level <= LEVEL_FLOOR else f"{self.level:+.1f}dB")

    def level_full(self) -> str:
        return "-oo dB" if self.level <= LEVEL_FLOOR else f"{self.level:+.1f} dB"


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
    ends: tuple[str, str] | None = None   # 양 끝 값의 표시 텍스트(예: Min/Max). 숫자가 아닌 끝을 가진 파라미터 흉내(리뷰 I4)
    digits: int = 1             # log 값 반올림 자릿수(Q는 실측 T처럼 3자리 유효숫자에 가깝게 3)

    def text(self) -> str:
        """7칸 열 텍스트. 실측 형식: 20.0Hz / 100 Hz / 1040Hz / 20000 / 0.0 dB / 0.71 / On."""
        if self.kind == "enum":
            return col(self.options[int(self.value)])
        if self.ends and self.value in (self.lo, self.hi):
            return col(self.ends[self.value == self.hi])
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
        if self.ends and self.value in (self.lo, self.hi):
            return self.ends[self.value == self.hi]
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


_SPACED = ("OutDry OutWet Predly Length LatCom InCrss Qualit Revers VoInLe VoATim VolAX1 VolAY1 VolAX2 VolAY2 "
           "VoDTim VolDX1 VolDY1 VolDX2 VolDY2 VoEnLe FiInLe FiATim FirAX1 FirAY1").split()


def space_designer() -> list[Param]:
    """Space Designer 실측 모델: 23페이지 × 8 = 184개. 1~3페이지 축약명은 실기, 나머지는 `P025`… 로 채움. 값은 전부 숫자."""
    names = _SPACED + [f"P{i:03d}" for i in range(len(_SPACED) + 1, 185)]
    return [Param(n, f"Space Designer {n}", "linear", 0.0, 100.0, 50.0, step=1.0) for n in names]


def with_dash_cells(params: list[Param], n: int) -> list[Param]:
    """빈 파라미터 칸 n개를 끝에 붙인다: 1행 `-`, 2행 공백, 틱·페이더에 무반응(실기 10차: Adaptive Limiter·Overdrive·Distortion)."""
    return params + [Param("-", "-", "enum", options=(" ",)) for _ in range(n)]


@dataclass
class Track:
    number: int
    name: str
    inserts: dict[int, str | None] = field(default_factory=lambda: {i: None for i in range(1, 16)})
    params: dict[int, list[Param]] = field(default_factory=dict)   # 슬롯 → 편집 뷰 파라미터
    eq: list[list[Param]] | None = None                           # Channel EQ 밴드(어느 슬롯에 있든)
    bypassed: set[int] = field(default_factory=set)
    volume: int | None = None                                     # 페이더 raw. Flip이 꺼진 상태의 페이더 이동이 바꾼다(None = 건드린 적 없음)
    eq_page: int = 1                                              # EQ 채널 뷰가 기억하는 마지막 페이지(실측 Q)
    kind: str = "track"                                           # track | output | master (실측 Z4: 출력·Master는 채널 뷰가 안 따라감)
    sends: dict[int, Send | None] = field(default_factory=lambda: {i: None for i in range(1, 9)})
    se_page: int = 1                                              # SE 뷰가 기억하는 마지막 페이지(실측 S3)

    @property
    def follows(self) -> bool:
        return self.kind == "track"

    def insert(self, slot: int, name: str) -> None:
        if self.inserts[slot] == "Channel EQ":
            self.eq = None
        self.inserts[slot] = name
        if name == "Channel EQ":
            self.eq = channel_eq()
            self.params[slot] = channel_eq_edit(self.eq)
        elif name == "Compressor":
            self.params[slot] = compressor()
        elif name == "Space Designer":
            self.params[slot] = space_designer()
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
        self.pl_track = 0                              # PL 뷰 2행이 보여 주는 트랙
        self.pl_select_stale = False                   # 켜면 PL 안에서 SELECT 해도 2행이 이전 트랙 슬롯을 유지(실기 8차 Z3 근사)
        self.slot = 1
        self.page = 1
        self.edit_open_page = 1                        # 편집 뷰가 1페이지가 아닌 곳에서 열림(실측 Space Designer: 임의 위치에서 시작)
        self.flip = False
        self.name_mode = False
        self.shift = False
        self.blink_on = True
        self.mode_note = P.Note.PAN
        self.cs_param = 0                              # TRACK 모드가 보여 주는 채널 스트립 파라미터(TRACK_MENU 인덱스)
        self.menu_labels = list(TRACK_MENU)
        self.track_held = False                        # TRACK 버튼 down 중: 2자리 `C_` + 2행 메뉴(실측 Z5)
        self.before_midi = "plugin_mixer"
        self.pre: dict[int, int] = {}                  # V-Pot → 미리 선택 틱 위치(0 = `--`, 0..2·(목록-1)로 포화)
        self.pending: list[float] = []                 # 재묘사 예정 시각
        self.timers: list[tuple[float, object]] = []   # (시각, 할 일): 확정 누름 ≈2초 뒤 편집 뷰(실측 K)
        self.deferred: list = []                       # 드라이버가 기다리기 시작한 뒤 도착할 응답(EQ up)
        self.eq_held = False                           # EQ 버튼 down 중: 2자리 `E_`(실측 A)
        self.plugin_list = list(PLUGIN_LIST)
        self.se_track = 0                              # SE 뷰 2행이 보여 주는 트랙(출력·Master를 고르면 안 바뀜, 실측 S10)
        self.send_held = False
        self.dest_list = list(DEST_LIST)
        self.lcd_lag = False                           # True면 페이더 이동의 LCD 값 쓰기가 에코보다 늦게 도착(실측 X)
        self.lagged: list = []                         # lcd_lag 응답: sleep·입력으로는 안 오고, 드라이버가 판정 안 된 wait_for에 들어가야 도착
        self.drop_first_fader = False                  # True면 Flip을 켠 뒤 처음 페이더 이동을 한 번 무시(에코·LCD 없음, 실측 Z1)
        self._fader_armed = False
        self.drop_all_faders = False                   # True면 페이더 이동을 항상 무시
        self.drop_all_vpots = False                    # True면 V-Pot 틱을 항상 무시(반응 없는 Logic)
        self.drop_first_flip = False                   # True면 처음 FLIP 누름을 한 번 무시(LED 변화 없음, 실측 Z2)
        self.flip_led_lag = False                      # True면 처음 처리된 FLIP 누름의 LED 변화가 첫 대기 시간 초과 뒤에 도착(리뷰 C1)
        self.flip_lagged: list = []
        self.flip_waits = 0                            # flip_lagged가 쌓인 뒤 판정 거짓 wait_for에 들어간 횟수
        self._flip_lag_used = False
        self.drop_all_flips = False                    # True면 FLIP 누름을 항상 무시
        self.drop_all_name_value = False               # True면 NAME/VALUE 누름을 항상 무시
        self.name_value_lag = False                    # True면 NAME/VALUE 누름의 2행 쓰기가 늦게 도착(lagged, 실기 10차)
        self.value_row_partial = False                 # True면 VALUE 전환의 2행 열 1~7이 늦게 도착(lagged, 재수집 근사)
        self.stale_value_cols: set[int] = set()        # VALUE 전환 뒤에도 2행에 축약명이 남는 열(다음 재묘사까지)
        self.refuse: set[int] = set()                  # 반응하지 않을 노트(고장 흉내)
        self.late_preselect_items: set[int] = set()    # 미리 선택 오버레이가 늦게 오는 목록 항목(처음 닿을 때 한 번)
        self.drop_preselect_at: set[int] = set()       # 오버레이 쓰기가 오지 않는 미리 선택 틱 위치
        self.no_overlay_on_nochange = False            # True면 값이 안 바뀐 V-Pot 틱(끝값)에 오버레이를 그리지 않음(리뷰 I3)
        self.narrow_name_overlay = False               # True면 틱 이름 오버레이가 1행 2~3열만 덮음(실기 10차)
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
        elif self.pre and self.view in ("plugin_mixer", "plugin_channel", "send_channel") and not self.pending:   # 오버레이 유효 중엔 깜박임 재묘사로 덮지 않음
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

    def _pre_cell_send(self, n: int, fallback: str) -> str:
        ch = ((n - 1) % 2) * 4
        if self.view != "send_channel" or ch not in self.pre:
            return fallback
        return col(self.dest_list[self.pre[ch]]) if self.blink_on else col("")

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
        if self.view == "track_menu":
            return " " * 56, "".join(col(x) for x in self.menu_labels).ljust(56), "C_"
        if self.view == "track":
            cells = []
            for tr in self.tracks[:8]:
                if self.cs_param == 0:
                    cells.append(col("+0.0dB"))
                elif self.cs_param == 1:
                    cells.append(col("" if tr.kind == "master" else "0"))
                elif self.cs_param == 4:
                    cells.append(col("St Out" if tr.follows else ""))          # 출력·Master는 빈칸(실측 Z5)
                else:
                    cells.append(col(""))
            return self._names_row(), "".join(cells).ljust(56), "CS"
        if self.view == "send_menu":
            return " " * 56, SEND_MENU, "S_"
        if self.view == "send_mixer":
            cells = [col(tr.sends[1].dest if tr.sends[1] else "--") for tr in self.tracks[:8]]
            return self._names_row(), "".join(cells).ljust(56), "S1"
        if self.view == "send_channel":
            st = self.tracks[self.se_track]
            r1, r2 = [], []
            for n in (2 * self.page - 1, 2 * self.page):
                s = st.sends.get(n)
                if s is None:
                    r1 += [col(f"Sen{n}In"), col("-"), col("-"), col("-")]
                    r2 += [self._pre_cell_send(n, col("--")), col(""), col(""), col("")]
                else:
                    r1 += [col(f"Sen{n}De"), col(s.dest.replace("Bus ", "")), col(f"Sen{n}Po"), col(f"Sen{n}Mu")]
                    r2 += [self._pre_cell_send(n, col(("*" if s.muted else "") + s.dest)), s.level_col(),
                           col(POS_COL[s.pos]), col("muted" if s.muted else "active")]
            return "".join(r1).ljust(56), "".join(r2).ljust(56), "SE"
        if self.view == "pan":
            return self._names_row(), "".join(col("0") for _ in self.tracks[:8]).ljust(56), "PN"
        if self.view == "eq_mixer":
            r2 = "".join(tr.eq[0][0].text() if tr.eq else col("") for tr in self.tracks[:8]).ljust(56)
            return self._names_row(), r2, "E1"
        if self.view == "eq_channel":
            ps = [p for band in t.eq[2 * self.page - 2:2 * self.page] for p in band]
            names = "".join(col(p.short) for p in ps).ljust(56)
            return names, names if self.name_mode else "".join(p.text() for p in ps).ljust(56), "EQ"   # NAME/VALUE: 2행 이름/값 토글
        if self.view == "plugin_mixer":
            cells = [self._pre_cell(ch, self._abbrev(tr.inserts[self.slot], self.slot, tr))
                     for ch, tr in enumerate(self.tracks[:8])]
            return self._names_row(), "".join(cells).ljust(56), self._slot_digits()
        if self.view == "plugin_channel":                       # 선택 트랙의 슬롯 1~8(실측 C)
            r1 = "".join(col(f"Ins{i}Pl") for i in range(1, 9))
            pt = self.tracks[self.pl_track]
            r2 = "".join(self._pre_cell(i - 1, self._abbrev(pt.inserts[i], i, pt)) for i in range(1, 9))
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
            return full.ljust(56 - len(page)) + page          # 두 자리 페이지(`Page 20/23`)도 56칸 안
        if self.page == 1:
            return (full + " " + page)[:56]
        tail = page + " "
        return (prefix + t.inserts[self.slot])[:56 - len(tail) - 5].ljust(56 - len(tail)) + tail

    def redraw(self, overlay: tuple[int, str, str] | None = None, mode_overlay: str | None = None,
               narrow_name: bool = False) -> None:
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
            if narrow_name:     # 실기 10차: 이름 뒤 공백 1칸 이상인 7칸 단위 폭(최소 14), 오른쪽 끝에서 밀리면 오른쪽 정렬 + 끝 공백
                w = max(14, (len(name) // 7 + 1) * 7)
                at = min(ch * 7, 56 - w)
                o1 = o1[:at] + (name.ljust(w) if at == ch * 7 else name.rjust(w - 1) + " ") + o1[at + w:]
            else:
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
            elif note == P.Note.TRACK:                           # 실측 Z5: down → `C_` 메뉴, up 뒤 CS 뷰
                self.track_held = on
                if on:
                    self.view = "track_menu"
                    self.redraw()
                else:
                    self.deferred.append(lambda: self._button(P.Note.TRACK))
            elif note == P.Note.SEND:                             # 실측 S1: down → `S_` 메뉴, up 뒤 뷰
                self.send_held = on
                if on:
                    self.view_before_menu = self.view
                    self.view = "send_menu"
                    self.redraw()
                else:
                    self.deferred.append(lambda: self._button(P.Note.SEND))
            elif note == P.Note.EQ:                              # 실측 A: down → `E_`, up 뒤 50 ms 안에 뷰
                self.eq_held = on
                if on:
                    self._emit(digits("E_"))
                else:
                    self.deferred.append(lambda: self._button(P.Note.EQ))
            elif on:
                self._button(note)
        elif st == 0xB0 and 0x10 <= data[1] <= 0x17:
            if self.drop_all_vpots:
                return []
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
            if self.tracks[self.selected].follows:           # 출력·Master 선택은 PL·SE 2행을 바꾸지 않음(실측 Z4·S10)
                if not (self.pl_select_stale and self.view == "plugin_channel"):
                    self.pl_track = self.selected
                self.se_track = self.selected
            self.pre.clear()
            self.redraw()
        elif note == N.TRACK:
            self._set_mode("track", N.TRACK)
            self.redraw(mode_overlay="Channel Strip parameter:")
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
        elif note == N.SEND:
            prev = getattr(self, "view_before_menu", "pan")
            if prev == "send_mixer":
                self.view, self.page = "send_channel", self.tracks[self.se_track].se_page
                self.pre.clear()
                self.redraw()
            elif prev == "send_channel":
                self.view = "send_mixer"
                self.pre.clear()
                self.redraw()
            else:
                self._set_mode("send_mixer", N.SEND)
                self.se_track = self.selected if self.tracks[self.selected].follows else self.se_track
                self.redraw(mode_overlay="Send 1 Parameter: Send 1 Destination")
        elif note == N.PLUGIN:
            if self.view == "plugin_mixer":
                self.view = "plugin_channel"
                if self.tracks[self.selected].follows:
                    self.pl_track = self.selected
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
            if self.drop_all_flips:
                return
            if self.drop_first_flip:
                self.drop_first_flip = False
                return
            self.flip = not self.flip
            self._fader_armed = self.flip
            led = [P.button_down(N.FLIP) if self.flip else P.button_up(N.FLIP)]
            if self.flip_led_lag and not self._flip_lag_used:
                self._flip_lag_used = True
                self.flip_waits = 0
                self.flip_lagged.append(lambda: self._emit(led))
            else:
                self._emit(led)
            if self.flip:
                self._emit([fader_echo(ch, self._flip_raw(ch)) for ch in range(8)])
            else:
                self._emit([fader_echo(ch, 12443) for ch in range(8)])
        elif note == N.NAME_VALUE:
            if self.drop_all_name_value:
                return
            self.name_mode = not self.name_mode
            if self.name_value_lag:
                r1, _r2, d = self._rows()
                self._emit([lcd_write(0, r1)] + digits(d))
                self.lagged.append(lambda: self._emit([lcd_write(56, self._rows()[1])]))
            elif self.value_row_partial and not self.name_mode:
                r1, r2, d = self._rows()
                self._emit([lcd_write(0, r1 + r2[:7])] + digits(d))
                self.lagged.append(lambda: self._emit([lcd_write(56 + 7, self._rows()[1][7:])]))
            elif self.stale_value_cols and not self.name_mode:
                r1, r2, d = self._rows()
                r2 = "".join((r1 if c in self.stale_value_cols else r2)[c * 7:(c + 1) * 7] for c in range(8))
                self._emit([lcd_write(0, r1 + r2)] + digits(d))
            else:
                self.redraw()
        elif N.VPOT_PUSH <= note < N.VPOT_PUSH + 8:
            if self.track_held and self.view == "track_menu":
                self.cs_param = note - N.VPOT_PUSH               # 홀드 메뉴 선택. 6(DisplP)·7(Setup)의 부작용은 흉내 내지 않음
                return
            self._push(note - N.VPOT_PUSH)

    def _flip_raw(self, ch: int) -> int:
        if self.view == "send_channel":
            _n, fld, s = self._send_at(ch)
            if fld == 1 and s is not None:
                return 0 if s.level <= LEVEL_FLOOR else FADERS.db_to_raw(s.level)
            return 0
        p = self._column_param(ch)
        return p.raw() if p else 0

    def _page(self, delta: int) -> None:
        old = self.page
        if self.view == "eq_channel":
            self.page = max(1, min(4, self.page + delta))      # 양 끝에서는 무반응(LCD 변화 없음, 실측 Q)
            if self.page == old:
                return
            self.tracks[self.selected].eq_page = self.page
        elif self.view == "plugin_edit":
            self.page = max(1, min(self._edit_pages(), self.page + delta))
        elif self.view == "send_channel":
            self.page = max(1, min(4, self.page + delta))
            if self.page == old:
                return
            self.tracks[self.se_track].se_page = self.page
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
        started = ch in self.pre
        if not started:                                                 # 실측: 다른 V-Pot의 미리 선택은 취소됨
            self.pre = {ch: 2 * self.plugin_list.index(current or "--")}
        before = self.pre[ch]
        self.pre[ch] = max(0, min(2 * (len(self.plugin_list) - 1), self.pre[ch] + ticks))
        if (started and self.pre[ch] == before) or self.pre[ch] in self.drop_preselect_at:
            return                                                      # 끝에 클램프(무변화) 또는 빠진 쓰기
        i = self._pre_index(ch)
        if i in self.late_preselect_items:                              # 늦은 오버레이: 지금은 이전 항목, 나중에 그때의 항목
            self.late_preselect_items.discard(i)
            self._draw_pre(ch, slot, max(0, i - 1))
            self.timers.append((self.clock() + LATE_PRESELECT_S,
                                lambda: ch in self.pre and self._draw_pre(ch, slot, self._pre_index(ch))))
            return
        self._draw_pre(ch, slot, i)

    def _draw_pre(self, ch: int, slot: int, i: int) -> None:
        name = self.plugin_list[i]
        self.redraw(overlay=(ch, f"Insert {slot} Plug-in", name if name == "--" else f"{name} (s/s)"))

    def _send_at(self, ch: int) -> tuple[int, int, Send | None]:
        """SE 열 → (센드 번호, 필드 0 dest·1 level·2 pos·3 mute, 센드)."""
        n = 2 * self.page - 1 + ch // 4
        return n, ch % 4, self.tracks[self.se_track].sends.get(n)

    def _vpot_send(self, ch: int, ticks: int) -> None:
        n, fld, s = self._send_at(ch)
        if fld == 0:                                                 # 목적지 미리 선택: 1틱 = 1항목(실측 S4)
            if ch not in self.pre:
                self.pre = {ch: self.dest_list.index(s.dest) if s else 0}
            self.pre[ch] = max(0, min(len(self.dest_list) - 1, self.pre[ch] + ticks))
            self.redraw(overlay=(ch, f"Send {n} Destination", self.dest_list[self.pre[ch]]))
            return
        if s is None:
            return                                                   # 센드 없으면 level/pos/mute 무반응(실측 S11)
        if fld == 1:
            s.level = max(LEVEL_FLOOR - 1, min(6.0, (LEVEL_FLOOR if s.level < LEVEL_FLOOR else s.level) + 0.5 * ticks))
            self.redraw(overlay=(ch, f"{n}  Aux 1      Sen{n}Mu", s.level_full()))
        elif fld == 2:
            s.pos = max(0, min(2, s.pos + ticks))
            self.redraw(overlay=(ch, f"Send {n} Position", POS_FULL[s.pos]))
        else:
            s.muted = ticks > 0
            self.redraw(overlay=(ch, f"Send {n} Mute   -", "muted" if s.muted else "active"))

    def _vpot(self, ch: int, ticks: int) -> None:
        if self.view == "send_channel":
            self._vpot_send(ch, ticks)
            return
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
        if p is None or p.short == "-":                                 # 빈 칸(1행 `-`)은 틱에 무반응
            return
        before = p.full()
        p.tick(ticks)
        if self.no_overlay_on_nochange and p.full() == before:
            return                                                      # 끝값 무변화 틱: 오버레이 없음(실기 미측정, 리뷰 I3)
        self.redraw(overlay=(ch, p.name, p.full()), narrow_name=self.narrow_name_overlay)

    def _push_send(self, ch: int) -> None:
        """dest 열 누름: 미리 선택이 있으면 `Send n Instantiate` 오버레이 → 2초 뒤 센드 생성/제거(실측 S5)."""
        n, fld, _s = self._send_at(ch)
        if fld != 0 or ch not in self.pre:
            return
        name = self.dest_list[self.pre[ch]]
        self.pre.clear()
        track = self.tracks[self.se_track]

        def commit() -> None:
            track.sends[n] = None if name == "--" else Send(name)
            self.redraw()
        self.timers.append((self.clock() + OVERLAY_S, commit))
        self.redraw(overlay=(ch, f"Send {n} Instantiate", name))

    def _push(self, ch: int) -> None:
        if self.view == "send_channel":
            self._push_send(ch)
            return
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
                self.view, self.page = "plugin_edit", self.edit_open_page
            self.redraw()
        elif t.inserts[self.slot]:
            self.selected = ch
            self.view, self.page = "plugin_edit", self.edit_open_page
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
                self.slot, self.page = slot, self.edit_open_page
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
            self.slot, self.page = slot, self.edit_open_page
            self.view = "plugin_edit"
            self.redraw()

    def _fader(self, ch: int, raw: int) -> None:
        if raw == 0:                                                    # raw 0 무시(실측 사례)
            return
        if not self.flip:                                               # Flip 꺼짐: 페이더는 트랙 볼륨을 움직인다(리뷰 C1)
            if (t := self._track(ch)) is not None:
                t.volume = raw
                self._emit([fader_echo(ch, raw)])
            return
        if self.drop_all_faders or (self.drop_first_fader and self._fader_armed):
            self._fader_armed = False
            return
        if self.view == "send_channel":                                 # SE Flip: 레벨 열 페이더 = 센드 dB(볼륨 표, 실측 S6)
            n, fld, s = self._send_at(ch)
            if fld != 1 or s is None:
                return
            new = FADERS.raw_to_db(raw)
            if new == s.level:
                return
            s.level = new
            self._emit([fader_echo(ch, FADERS.db_to_raw(new) if new > LEVEL_FLOOR else 1)])
            self.redraw(overlay=(ch, f"{n}  Aux 1      Sen{n}Mu", s.level_full()))
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
        if logic.flip_lagged and not pred(surface.state):
            logic.flip_waits += 1
            if logic.flip_waits >= 2:
                while logic.flip_lagged:
                    logic.flip_lagged.pop(0)()
        return wait_for(pred, timeout)
    surface.wait_for = late_wait_for
    fake.now += 1.0                 # 조용 1초 → ready
    surface.tick()
    assert surface.state.connection.state == "ready"
    return surface, fake, logic
