"""CoreMIDI 가상 포트. 수신 콜백은 CoreMIDI 스레드에서 불리므로 on_message로 넘기기만 한다."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

PORT_NAME = "LogicMCP"


class Transport(Protocol):
    on_message: Callable[[float, bytes], None]

    def open(self) -> None: ...
    def close(self) -> None: ...
    def send(self, data: bytes) -> None: ...


class RtMidiTransport:
    def __init__(self, port_name: str = PORT_NAME, clock: Callable[[], float] = time.monotonic) -> None:
        self.port_name = port_name
        self.on_message: Callable[[float, bytes], None] = lambda ts, data: None
        self._clock = clock
        self._in = None
        self._out = None

    def open(self) -> None:
        import rtmidi  # 지연 임포트: 테스트 환경에서 모듈 로드만으로 CoreMIDI를 건드리지 않게

        self._out = rtmidi.MidiOut()
        self._out.open_virtual_port(self.port_name)
        self._in = rtmidi.MidiIn()
        self._in.open_virtual_port(self.port_name)
        self._in.ignore_types(sysex=False, timing=True, active_sense=True)
        self._in.set_callback(self._callback)

    def _callback(self, event, _data=None) -> None:
        message, _delta = event
        self.on_message(self._clock(), bytes(message))

    def send(self, data: bytes) -> None:
        if self._out is None:
            raise RuntimeError("port not open")
        self._out.send_message(list(data))

    def close(self) -> None:
        # 가상 포트는 close_port로 닫히지 않고 인스턴스를 지워야 사라진다(python-rtmidi 문서)
        for port in (self._in, self._out):
            if port is not None:
                port.close_port()
                port.delete()
        self._in = self._out = None
