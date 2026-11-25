"""실기 확인(테스트 프로젝트 전용, 저장하지 말 것): 명령 계열마다 한두 개씩 돌려 결과를 한 줄씩 찍고 jsonl로 남긴다.
리팩토링 전후를 같은 순서로 돌려 비교하는 용도. 대상은 Logic 채널 번호로 준 트랙 하나(슬롯이 전부 비어 있어야 하고, 도는 동안 뮤트한다).
Compressor를 넣어 params·get·set·set_many·bypass·move·remove를, Channel EQ를 넣어 eq get·set·set_many를, 센드는 읽기와 거절 경로만 돈다.
끝나면 넣은 것을 제거하고 뮤트를 푼다. 숫자 set 결과는 직전 실행이 남긴 페이더 값에 따라 달라질 수 있다(docs/mcu-protocol.md Z28).
사용: scripts/live_smoke.py <out.jsonl> <label> [트랙 번호=6]"""
import json
import sys

from logic_mcp.server.main import build

OUT, LABEL, N = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6
commands, surface = build()
surface.start()
pc, eq, se = commands.plugin, commands.eq, commands.send
rows = []


def slots(r):
    """list 결과 → {슬롯: 이름}(빈 슬롯 제외)."""
    row = ((r.after or {}).get("tracks") or {}).get(str(N)) or {}
    return {k: (v or {}).get("name") or (v or {}).get("text") for k, v in row.items() if v}


def brief(after):
    if not isinstance(after, dict):
        return after
    keep = {k: after[k] for k in ("plugin", "slot", "index", "short", "value", "text", "pages", "has_eq", "done",
                                   "replaced", "from", "to", "abbrev") if k in after}
    if "params" in after:
        keep["params"] = len(after["params"])
    if "results" in after:
        keep["results"] = [(x.get("short") or f"{x.get('band')}{x.get('param')}", x["ok"], (x.get("after") or {}).get("text"))
                           for x in after["results"]]
    if "bands" in after:
        keep["bands"] = {k: v for k, v in after["bands"].items() if k in ("3", "4")}
    if "sends" in after:
        keep["sends"] = sum(1 for v in after["sends"].values() if v.get("present"))
    if "tracks" in after:
        keep["tracks"] = after["tracks"].get(str(N))
    return keep


def step(name, fn, *a):
    r = fn(*a)
    row = {"label": LABEL, "step": name, "ok": r.ok, "verified": r.verified, "note": r.note, "ms": r.elapsed_ms,
           "after": brief(r.after)}
    rows.append(row)
    print(f"{name:22} ok={r.ok!s:5} {r.verified:10} {r.elapsed_ms / 1000:5.1f}s {str(row['after'])[:150]} | {r.note[:90]}", flush=True)
    return r


try:
    print("ready:", commands.wait_ready(60).ok, flush=True)
    r = step("list(처음)", pc.list, None, N)
    if not r.ok or slots(r):
        raise SystemExit(f"!! 중단: 트랙 {N} 슬롯이 비어 있지 않음: {slots(r)}")
    m = commands.track("mute", None, N)                     # 임시 삽입 동안 트랙을 뮤트한다
    print(f"mute: ok={m.ok} {m.verified}", flush=True)
    try:
        step("insert", pc.insert, None, N, 1, "Compressor", False)
        step("params", pc.params, None, N, 1)
        step("get(이름)", pc.get, None, N, 1, "Ratio")
        step("set(인덱스)", pc.set, None, N, 1, 2, -24.0)
        step("set_many", pc.set_many, None, N, 1, [{"param": "Ratio", "value": 4.0}, {"param": "Attack", "value": 20.0}])
        step("bypass on", pc.bypass, None, N, 1, True)
        step("bypass off", pc.bypass, None, N, 1, False)
        step("move 1→3", pc.move, None, N, 1, 3)
        step("remove 3", pc.remove, None, N, 3)
        step("remove(이미 빔)", pc.remove, None, N, 3)
        step("get(빈 슬롯)", pc.get, None, N, 1, "Ratio")
        step("params(슬롯 9)", pc.params, None, N, 9)
        step("eq get(없음)", eq.get, None, N)
        step("eq set(삽입 금지)", eq.set, None, N, 3, "gain", 3.0, False)
        step("eq set(삽입)", eq.set, None, N, 3, "gain", 3.0, True)
        step("eq set_many", eq.set_many, None, N, [{"band": 4, "param": "freq", "value": 1000.0},
                                                   {"band": 4, "param": "q", "value": 1.0}], True)
        step("eq get", eq.get, None, N)
        step("send get", se.get, None, N)
        step("send level(없음)", se.set_level, None, N, 1, -6.0)
        step("send mute(범위 밖)", se.mute, None, N, 9, True)
    finally:
        r = step("list(정리 전)", pc.list, None, N)
        for k in sorted(slots(r)):
            step(f"정리 remove {k}", pc.remove, None, N, int(k))
        r = step("list(끝)", pc.list, None, N)
        if slots(r):
            print(f"!! 슬롯이 남아 있음: {slots(r)}", flush=True)
        m = commands.track("unmute", None, N)
        print(f"unmute: ok={m.ok} {m.verified}", flush=True)
    bk = commands.bank("first")
    st = commands.status()
    print(f"bank first: {bk.ok} {bk.verified} / status: {st.get('assignment_mode')} flip {st.get('flip')} "
          f"mute {[s.mute for s in surface.state.strips]}", flush=True)
finally:
    surface.stop()
    with open(OUT, "a") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
