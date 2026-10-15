"""스펙 2a 실기 검증: EQ·플러그인 명령을 실제 Logic에서 돌려 결과 표를 찍는다. 테스트 프로젝트(저장 안 함)에서 실행.
사용: uv run python scripts/live_check2.py [strip=1] [--scan]"""
import sys

from logic_mcp.server.main import build

args = [a for a in sys.argv[1:] if not a.startswith("--")]
strip = int(args[0]) if args else 1
commands, surface = build()
surface.start()


def run(name, fn):
    r = fn()
    print(f"{name:30} ok={r.ok!s:5} {r.verified:10} {r.elapsed_ms:5}ms {r.note[:90]}")
    return r


try:
    print("Logic이 서피스를 설치하기를 기다리는 중…")
    print(commands.wait_ready(60).model_dump())
    run("configure", commands.configure)
    r = run("eq get (before)", lambda: commands.eq.get(strip, None))
    print("  has_eq:", r.after and r.after.get("has_eq"))
    run("eq set b3 freq 1000", lambda: commands.eq.set(strip, None, 3, "freq", 1000.0))
    run("eq set b3 gain -3", lambda: commands.eq.set(strip, None, 3, "gain", -3.0))
    run("eq set b1 slope 24", lambda: commands.eq.set(strip, None, 1, "slope", 24))
    run("eq set b8 on False", lambda: commands.eq.set(strip, None, 8, "on", False))
    run("eq set b4 q 2.0", lambda: commands.eq.set(strip, None, 4, "q", 2.0))
    r = run("eq get (after)", lambda: commands.eq.get(strip, None))
    for k in ("1", "3", "4", "7", "8"):
        print(f"  band {k}:", r.after and r.after.get("bands", {}).get(k))
    r = run("plugin list (strip)", lambda: commands.plugin.list(strip, None))
    print("  inserts:", r.after and {n: {s: v and v["text"] for s, v in row.items() if v} for n, row in r.after["tracks"].items()})
    run("plugin insert Compressor s2", lambda: commands.plugin.insert(strip, None, 2, "Compressor"))
    r = run("plugin params s2", lambda: commands.plugin.params(strip, None, 2))
    print("  pages:", r.after and r.after.get("pages"))
    print("  params:", [(p["index"], p["short"], p["text"]) for p in (r.after or {}).get("params", [])])
    run("plugin set Thrs -24", lambda: commands.plugin.set(strip, None, 2, "Thrs", -24.0))   # 실측 축약 `Thrs`(M)
    run("plugin get Thrs", lambda: commands.plugin.get(strip, None, 2, "Thrs"))
    run("plugin bypass s2 on", lambda: commands.plugin.bypass(strip, None, 2, True))
    run("plugin bypass s2 off", lambda: commands.plugin.bypass(strip, None, 2, False))
    run("plugin remove s2", lambda: commands.plugin.remove(strip, None, 2))
    run("plugin remove s1 (Channel EQ)", lambda: commands.plugin.remove(strip, None, 1))
    if "--scan" in sys.argv:
        r = run("plugin scan (force)", lambda: commands.plugin.scan(force=True))
        print("  scan:", r.after)
    st = commands.status()
    print("status:", {k: st[k] for k in ("state", "assignment_mode", "flip", "view_kind")})
finally:
    surface.stop()
