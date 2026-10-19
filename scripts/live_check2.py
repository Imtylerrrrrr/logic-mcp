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
    r = run("plugin list (bank)", lambda: commands.plugin.list(None, None))      # 뱅크 전체(m6 실기 확인)
    for n, row in ((r.after or {}).get("tracks") or {}).items():
        print(f"  track {n}:", {s: v["text"] for s, v in row.items() if v} or "(빈 인서트)")
    unresolved = {n: [v["text"] for v in row.values() if v and v["name"] is None] for n, row in ((r.after or {}).get("tracks") or {}).items()}
    unresolved = {n: xs for n, xs in unresolved.items() if xs}
    print("  bank list 식별 안 된 슬롯:", unresolved or "없음 (기대: 없음)")
    run("plugin insert Compressor s2", lambda: commands.plugin.insert(strip, None, 2, "Compressor"))
    r = run("plugin params s2", lambda: commands.plugin.params(strip, None, 2))
    print("  pages:", r.after and r.after.get("pages"))
    print("  params:", [(p["index"], p["short"], p["text"]) for p in (r.after or {}).get("params", [])])
    r = run("plugin get 21 (index)", lambda: commands.plugin.get(strip, None, 2, 21))   # 기대 short `Mode`(index 로 get, 미검증 경로)
    print("  short:", r.after and r.after.get("short"), "(기대 Mode)")
    run("plugin set Thrs -24", lambda: commands.plugin.set(strip, None, 2, "Thrs", -24.0))   # 실측 축약 `Thrs`(M)
    run("plugin get Thrs", lambda: commands.plugin.get(strip, None, 2, "Thrs"))
    run("plugin bypass s2 on", lambda: commands.plugin.bypass(strip, None, 2, True))
    run("plugin bypass s2 off", lambda: commands.plugin.bypass(strip, None, 2, False))
    run("plugin insert Limiter s2 repl", lambda: commands.plugin.insert(strip, None, 2, "Limiter", replace=True))   # 기대 verified(replace 경로)
    run("plugin remove s2", lambda: commands.plugin.remove(strip, None, 2))
    run("plugin remove s1 (Channel EQ)", lambda: commands.plugin.remove(strip, None, 1))
    r = run("send get (before)", lambda: commands.send.get(strip, None))
    run("send set_dest Bus 1 s1", lambda: commands.send.set_dest(strip, None, 1, "Bus 1"))      # Aux 자동 생성 → 뒤 번호 밀림(S5)
    run("send set_level -6 s1", lambda: commands.send.set_level(strip, None, 1, -6.0))
    run("send set_level -inf s1", lambda: commands.send.set_level(strip, None, 1, float("-inf")))
    run("send set_pos pre s1", lambda: commands.send.set_pos(strip, None, 1, "pre"))
    run("send mute on s1", lambda: commands.send.mute(strip, None, 1, True))
    run("send mute off s1", lambda: commands.send.mute(strip, None, 1, False))
    r = run("send get (after)", lambda: commands.send.get(strip, None))
    print("  send 1:", r.after and r.after["sends"]["1"])
    run("send remove s1", lambda: commands.send.remove(strip, None, 1))
    outs = [s.number for s in commands.surface.state.strips if s.number is not None and s.name.startswith(("St", "SOu", "Mas"))]
    if outs:                                                                                   # 출력 스트립 가드(Z4): skipped 기대. Stereo Out은 LCD에 'SOu'(실기 10차)
        run(f"plugin list #{outs[0]} (출력, skipped 기대)", lambda: commands.plugin.list(None, outs[0]))
        run(f"send get #{outs[0]} (출력, skipped 기대)", lambda: commands.send.get(None, outs[0]))
    if "--scan" in sys.argv:
        r = run("plugin scan (force)", lambda: commands.plugin.scan(force=True))
        print("  scan:", r.after)
    st = commands.status()
    print("status:", {k: st[k] for k in ("state", "assignment_mode", "flip", "view_kind")})
finally:
    surface.stop()
