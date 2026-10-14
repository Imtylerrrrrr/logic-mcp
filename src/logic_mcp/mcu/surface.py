"""트랜스포트 + 상태 + 락 + 대기. 명령 계층은 이 클래스만 본다."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from . import protocol as P
from . import state as S
from .transport import Transport


class Surface:
    def __init__(self, transport: Transport, clock: Callable[[], float] = time.monotonic,
                 tick_interval: float = 0.1) -> None:
        self._t = transport
        self._t.on_message = self.handle_message
        self._clock = clock
        self._tick_interval = tick_interval
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._state = S.initial_state()
        self._stop = threading.Event()
        self._ticker: threading.Thread | None = None

    @property
    def state(self) -> S.SurfaceState:
        with self._lock:
            return self._state

    @property
    def clock(self) -> Callable[[], float]:
        return self._clock

    def start(self) -> None:
        self._t.open()
        self._stop.clear()
        self._ticker = threading.Thread(target=self._tick_loop, name="surface-tick", daemon=True)
        self._ticker.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ticker is not None:
            self._ticker.join(timeout=1.0)
        self._t.close()

    def _tick_loop(self) -> None:
        while not self._stop.wait(self._tick_interval):
            self.tick()

    def tick(self) -> None:
        with self._cond:
            self._state = S.tick(self._state, self._clock())
            self._cond.notify_all()

    def handle_message(self, ts: float, data: bytes) -> None:
        ev = P.decode(data)
        reply = P.handshake_reply(ev)
        if reply is not None:
            self._t.send(reply)
        with self._cond:
            self._state = S.reduce(self._state, ev, ts)
            self._cond.notify_all()

    def send(self, data: bytes) -> None:
        self._t.send(data)

    def wait_for(self, pred: Callable[[S.SurfaceState], bool], timeout: float) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: pred(self._state), timeout=timeout)

    def wait_settled(self, timeout: float = 1.0) -> bool:
        return self.wait_for(lambda s: self._clock() >= s.connection.dirty_until, timeout)
