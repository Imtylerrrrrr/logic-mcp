from __future__ import annotations

from collections.abc import Callable

from logic_mcp.mcu.surface import Surface


class FakeTransport:
    """send()에 대한 응답을 동기적으로 되돌려 주는 가짜 포트."""

    def __init__(self) -> None:
        self.on_message: Callable[[float, bytes], None] = lambda ts, data: None
        self.sent: list[bytes] = []
        self.replies: Callable[[bytes], list[bytes]] = lambda data: []
        self.now = 1000.0
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def send(self, data: bytes) -> None:
        self.sent.append(data)
        for reply in self.replies(data):
            self.on_message(self.now, reply)

    def feed(self, data: bytes) -> None:
        self.on_message(self.now, data)


def make_surface() -> tuple[Surface, FakeTransport]:
    fake = FakeTransport()
    surface = Surface(fake, clock=lambda: fake.now + 1.0, tick_interval=0.01)
    return surface, fake
