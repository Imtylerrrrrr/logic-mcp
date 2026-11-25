"""곡선 측정(테스트 프로젝트 전용, 임시 인스턴스의 값만 바꾼다, 저장 안 함, 번들·캐시 표를 고치지 않는다).
묶음의 플러그인마다: <strip>의 <slot>에 삽입 → 번들 표에서 map이 linear·log인 항목마다 Flip 페이더를 RAWS 위치로 보내고 값을 읽는다 → 제거.
결과는 플러그인당 한 줄(JSON)로 <out>에 덧붙인다. 사용: scripts/measure_curves.py <groups.json> <묶음 번호> <out.jsonl>
groups.json = [{"strip": 6, "expect": "6", "slot": 1, "plugins": [...]}, ...]
측정하는 동안 그 트랙을 뮤트하고 끝에 푼다. 환경 변수 CURVE_MODE=rest면 1차에서 건너뛴 항목(0·음수에서 시작하는 linear의 셋째부터)만 잰다.
결과 요약은 scripts/curve_summary.py, 2026-11-25~26 측정값은 docs/measurements/."""
import json
import os
import sys
import time

from logic_mcp.logic.modes import ModeError
from logic_mcp.logic.plugins.cache import BUNDLED
from logic_mcp.server.main import build

RAWS = (1, 4096, 8192, 12288, 16383)
group = json.load(open(sys.argv[1]))[int(sys.argv[2]) - 1]
out = sys.argv[3]
strip, slot, names = group["strip"], group.get("slot", 1), group["plugins"]
bundled = json.load(open(BUNDLED))["params"]
commands, surface = build()
surface.start()
d, pc = commands.modes, commands.plugin
b = pc.b


def emit(rec):
    with open(out, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def todo_items(name):
    items = sorted(bundled[name]["items"], key=lambda x: x["index"])
    half = len(items) // 2
    doubled = len(items) >= 2 and len(items) % 2 == 0 and [x["short"] for x in items[:half]] == [x["short"] for x in items[half:]]
    pool = items[:half] if doubled else items                # 두 벌 표(Space Designer)는 첫 묶음만
    todo, rest, sampled = [], [], 0
    for x in pool:                                           # log 전부 + 양수 범위 linear 전부(종류를 바꿀 수 있는 것) + 0·음수 범위 linear는 앞 2개만 표본
        m = x.get("map") or {}
        if m.get("type") == "log" or (m.get("type") == "linear" and min(m["lo"], m["hi"]) > 0):
            todo.append(x)
        elif m.get("type") == "linear" and sampled < 2:
            todo.append(x)
            sampled += 1
        elif m.get("type") == "linear":
            rest.append(x)                                   # 1차에서 재지 않은 나머지(0·음수 범위 linear)
    return items, (rest if os.environ.get("CURVE_MODE") == "rest" else todo)


def measure(name):
    recs, err = [], None
    with b._lock:
        ch = b._resolve(strip, None, "audit", b._now_ms())
        try:
            b._fresh()
            full, _abbrev, pages = pc._open_edit(ch, slot)
            if full not in bundled:
                return {"plugin": name, "full": full, "error": "번들에 없는 이름", "items": []}
            items, todo = todo_items(full)
            if pages != bundled[full]["pages"]:
                return {"plugin": name, "full": full, "error": f"화면 {pages}페이지 != 표 {bundled[full]['pages']}", "items": []}
            for n, it in enumerate(todo):
                try:
                    if n:                                    # set_many의 항목 사이와 같은 순서
                        d.settle_overlay()
                        d.flip(False)
                        d.toggle_name_value()
                    col = pc._goto_param(it, items)
                    d.flip(True)
                    pts = []
                    for raw in RAWS:
                        echo = d.fader(col, raw)
                        v = d.read_value(col)
                        pts.append([raw, echo, v.text, v.number, v.unit])
                    recs.append({"index": it["index"], "short": it["short"], "map": it["map"], "points": pts})
                except ModeError as e:                       # 상태를 믿을 수 없다: 이 플러그인은 여기서 끝낸다
                    err = f"index {it['index']} {it['short']}: ModeError {e.step}: {str(e)[:160]}"
                    break
            return {"plugin": name, "full": full, "todo": len(todo), "error": err, "items": recs}
        finally:
            d.leave_safely()


try:
    print("ready:", commands.wait_ready(60).ok, "plugins:", len(names), flush=True)
    got = surface.state.strips[strip - 1].name
    if group.get("expect") is not None and got != group["expect"]:
        print(f"!! 중단: strip {strip} 이름이 {got!r} (기대 {group['expect']!r})", flush=True)
        names = []
    inv = pc.list(strip, None) if names else None
    if inv is not None:
        row = next(iter(inv.after["tracks"].values())) if inv.ok and inv.after else None
        if not row or row.get(str(slot)) is not None:
            print(f"!! 중단: strip {strip} 슬롯 {slot}이 비어 있지 않거나 못 읽음: {str(row)[:120]}", flush=True)
            names = []
    muted_by_me = False                                   # 측정 중 소리가 나가지 않게 트랙을 뮤트한다(끝에 되돌린다)
    if names and not surface.state.strips[strip - 1].mute:
        m = commands.track("mute", strip)
        print(f"mute: ok={m.ok} {m.verified} {m.note[:80]}", flush=True)
        if not m.ok:
            print("!! 중단: 뮤트 실패", flush=True)
            names = []
        muted_by_me = m.ok
    for name in names:
        t0 = time.monotonic()
        r = pc.insert(strip, None, slot, name)
        if not r.ok:
            emit({"plugin": name, "error": f"insert_failed: {r.note[:160]}", "items": []})
            print(f"!! {name}: insert 실패 {r.verified} {r.note[:120]}", flush=True)
            chk = pc.remove(strip, None, slot)
            if not chk.ok:
                print("!! 제거 실패: 슬롯이 차 있어 여기서 멈춘다", flush=True)
                break
            continue
        line = ""
        try:
            rec = measure(name)
            emit(rec)
            line = f"항목 {len(rec['items'])}/{rec.get('todo', '?')}" + (f" 오류: {rec['error'][:110]}" if rec.get("error") else "")
            if rec.get("error"):
                print(f"!! {name}: {rec['error'][:170]}", flush=True)
        except Exception as e:                              # noqa: BLE001
            emit({"plugin": name, "error": f"{type(e).__name__}: {str(e)[:200]}", "items": []})
            line = f"오류 {type(e).__name__}"
            print(f"!! {name}: {type(e).__name__}: {str(e)[:160]}", flush=True)
        finally:
            rm = pc.remove(strip, None, slot)
            print(f"-- {name}: {time.monotonic() - t0:.0f}s {line} remove={rm.verified} {rm.note[:60]}", flush=True)
        if not rm.ok:
            print("!! 제거 실패: 슬롯이 차 있어 여기서 멈춘다", flush=True)
            break
    if muted_by_me:
        u = commands.track("unmute", strip)
        print(f"unmute: ok={u.ok} {u.verified} {u.note[:80]}", flush=True)
        if not u.ok:
            print("!! 뮤트 해제 실패: 트랙이 뮤트된 채 남음", flush=True)
    st = commands.status()
    print("status:", st.get("assignment_mode"), "flip", st.get("flip"), "mute", surface.state.strips[strip - 1].mute, flush=True)
finally:
    surface.stop()
