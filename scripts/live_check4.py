"""스펙 4(실전 수정) 실기 검증: 이름 탐색 삽입·Aux 판정·허용 오차·move를 실제 Logic에서 돌려 한 줄씩 찍는다.
테스트 프로젝트(또는 저장하지 않을 프로젝트)에서 실행. move는 플러그인 설정값을 초기화한다. 프로젝트는 저장하지 않는다.
사용: uv run python scripts/live_check4.py [strip=1]"""
import sys

from logic_mcp.server.main import build

strip = int(sys.argv[1]) if len(sys.argv) > 1 else 1
commands, surface = build()
surface.start()


def run(name, fn):
    r = fn()
    print(f"{name:36} {r.verified:10} | {r.note}")
    return r


def slots(r) -> dict[int, str | None]:
    """plugin list(스트립 하나) 결과 → 슬롯 번호 → 이름(모르면 축약, 비면 None)."""
    rows = (r.after or {}).get("tracks") or {}
    row = next(iter(rows.values()), None) or {}
    return {int(k): v and (v["name"] or v["text"]) for k, v in row.items()}


try:
    print("Logic이 서피스를 설치하기를 기다리는 중…")
    print(commands.wait_ready(60).model_dump())
    run("configure", commands.configure)
    inv = slots(run(f"plugin list (strip {strip})", lambda: commands.plugin.list(strip, None)))
    print("  inserts:", {k: v for k, v in inv.items() if v} or "(빈 인서트)")
    empty = next((k for k in sorted(inv) if inv[k] is None), None)
    kept = None

    # ① 이름 탐색 폴백이 들어갈 수 있는 삽입 → 제거(note: "" = 캐시 위치, name_scan:<틱> = 이름 탐색)
    if empty is None:
        print("① 빈 슬롯 없음: 삽입·제거 건너뜀")
    else:
        r = run(f"① insert Channel EQ s{empty}", lambda: commands.plugin.insert(strip, None, empty, "Channel EQ"))
        if r.verified == "verified" and not any(inv.values()):     # 빈 트랙: ③④용으로 남겨 두고 끝에 제거
            inv[empty] = "Channel EQ"
            kept = empty
        elif r.verified == "verified":
            run(f"① remove s{empty}", lambda: commands.plugin.remove(strip, None, empty))

    # ② 뱅크 전체 list: Aux 행은 슬롯 1만, 나머지는 null
    r = run("② plugin list (bank)", lambda: commands.plugin.list(None, None))
    aux = (r.after or {}).get("aux") or []
    print("  aux:", aux, " unsupported:", (r.after or {}).get("unsupported"))
    for n in aux:
        row = r.after["tracks"][str(n)]
        print(f"  aux {n}:", {k: v for k, v in row.items() if v} or "(슬롯 1 빈칸)",
              "| 슬롯 2~8 모두 null:", all(row[str(i)] is None for i in range(2, 9)))
    if aux:                                                       # Aux로 판정된 스트립만: 슬롯 2 삽입은 누르기 전에 skipped 기대(Z19)
        run(f"② insert Chorus aux {aux[0]} s2 (skipped 기대)", lambda: commands.plugin.insert(None, aux[0], 2, "Chorus"))

    # ③ Channel EQ Low Shelf Gain 3 dB(기본 허용 오차 0.2, 보정 10회)
    eq_slot = next((k for k in sorted(inv) if inv[k] == "Channel EQ"), None)
    if eq_slot is None:
        print("③ Channel EQ 슬롯 없음: 건너뜀")
    else:
        r = run(f"③ set Low Shelf Gain 3 s{eq_slot}", lambda: commands.plugin.set(strip, None, eq_slot, "Low Shelf Gain", 3.0))
        print("  after:", r.after and r.after.get("text"))

    # ④ 마지막 차 있는 슬롯 → 첫 빈 슬롯으로 move, 다시 되돌림(설정값 초기화)
    inv = slots(commands.plugin.list(strip, None))
    last = next((k for k in sorted(inv, reverse=True) if inv[k]), None)
    empty = next((k for k in sorted(inv) if inv[k] is None), None)
    if last is None or empty is None:
        print("④ 차 있는 슬롯이나 빈 슬롯이 없음: move 건너뜀")
    else:
        r = run(f"④ move s{last} -> s{empty}", lambda: commands.plugin.move(strip, None, last, empty))
        if r.verified == "verified":
            run(f"④ move s{empty} -> s{last} (되돌림)", lambda: commands.plugin.move(strip, None, empty, last))
    if kept is not None:
        run(f"① remove s{kept} (정리)", lambda: commands.plugin.remove(strip, None, kept))
    st = commands.status()
    print("status:", {k: st[k] for k in ("state", "assignment_mode", "flip", "view_kind")})
finally:
    surface.stop()
