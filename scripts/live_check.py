"""실제 Logic으로 명령→피드백을 확인한다. Logic에서 프로젝트를 열어 둔 상태로 실행.
사용: uv run python scripts/live_check.py"""
import time

from logic_mcp.server.main import build

commands, surface = build()
surface.start()
try:
    print("Logic이 서피스를 설치하기를 기다리는 중 (프로젝트를 열거나 다시 여세요)…")
    print(commands.wait_ready(60).model_dump())
    rows = [("configure", commands.configure())]
    rows.append(("status", commands.status()))
    rows.append(("mute 1", commands.track("mute", strip=1)))
    rows.append(("unmute 1", commands.track("unmute", strip=1)))
    rows.append(("play", commands.transport("play")))
    time.sleep(1.0)
    rows.append(("stop", commands.transport("stop")))
    rows.append(("cycle_on", commands.transport("cycle_on")))
    rows.append(("cycle_off", commands.transport("cycle_off")))
    rows.append(("volume -6", commands.mixer_volume(1, None, -6.0)))
    rows.append(("volume 0", commands.mixer_volume(1, None, 0.0)))
    rows.append(("pan +10", commands.mixer_pan(1, None, 10)))
    rows.append(("pan 0", commands.mixer_pan(1, None, 0)))
    rows.append(("bank right", commands.bank("right")))
    rows.append(("bank first", commands.bank("first")))
    for name, r in rows:
        if isinstance(r, dict):
            print(f"{name:12} {r}")
        else:
            print(f"{name:12} ok={r.ok} {r.verified:10} {r.elapsed_ms:4}ms {r.note}")
finally:
    surface.stop()
