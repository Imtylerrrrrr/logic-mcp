"""가상 포트를 열고 Logic이 보내는 MCU 트래픽을 'ts RX|TX hex' 픽스처 형식으로 기록한다.
사용: uv run python scripts/capture.py <초> <출력경로>"""
import sys
import time

from logic_mcp.mcu import protocol as P
from logic_mcp.mcu.surface import Surface
from logic_mcp.mcu.transport import RtMidiTransport

duration = float(sys.argv[1]) if len(sys.argv) > 1 else 600
out_path = sys.argv[2] if len(sys.argv) > 2 else f"capture_{int(time.time())}.log"
t0 = time.monotonic()
log = open(out_path, "a", buffering=1)


class LoggingTransport(RtMidiTransport):
    def send(self, data: bytes) -> None:
        log.write(f"{time.monotonic() - t0:9.3f} TX {data.hex(' ').upper()}\n")
        super().send(data)


transport = LoggingTransport()
surface = Surface(transport)
inner = surface.handle_message


def handle(ts: float, data: bytes) -> None:
    log.write(f"{ts - t0:9.3f} RX {data.hex(' ').upper()}\n")
    inner(ts, data)
    ev = P.decode(data)
    if not isinstance(ev, (P.Meter, P.TimeDigit)):
        print(f"[{ts - t0:7.2f}] {ev}", flush=True)


transport.on_message = handle
surface.start()
print(f"포트 LogicMCP 열림. {duration:.0f}초 기록 → {out_path}")
try:
    time.sleep(duration)
finally:
    surface.stop()
    print("LCD:", surface.state.lcd)
