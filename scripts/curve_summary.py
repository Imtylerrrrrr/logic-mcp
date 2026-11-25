"""곡선 측정 요약(오프라인). 사용: scripts/curve_summary.py <측정.jsonl> [--detail <플러그인>] [--json <out.json>]
항목마다 안쪽 세 점이 linear·log 중 어느 쪽에 맞는지 페이더 비율 오차(0~1)로 본다. 양 끝은 이번에 잰 값을 쓴다."""
import json
import math
import sys

MAXR = 16383
FIT, MISS = 0.02, 0.05          # 새 종류가 이 안에 맞고(FIT) 지금 종류가 이만큼 어긋나면(MISS) 종류 변경 후보


def same_unit(a, b):
    if a == b or a is None or b is None:
        return True
    return a.startswith(b) or b.startswith(a)             # 값 오버레이는 단위가 잘린다(`dB` → `d`, `ms` → `m`)


def analyse(it):
    stale = [p[0] for p in it["points"] if p[1] is None]     # 에코가 없던 이동: 값이 안 바뀌었을 수 있어 버린다
    pts = [p for p in it["points"] if p[1] is not None]
    if len(pts) < 4 or pts[0][0] != 1 and pts[-1][0] != MAXR:
        return {"index": it["index"], "short": it["short"], "type": it["map"]["type"], "lo": it["map"]["lo"], "hi": it["map"]["hi"],
                "texts": [p[2] for p in it["points"]], "verdict": "unreadable"}
    if pts[0][0] != 1:                                       # 한쪽 끝이 빠졌으면 표의 끝값으로 채운다
        pts = [[1, 0, "(표)", min(it["map"]["lo"], it["map"]["hi"]) if pts[-1][3] > pts[0][3] else max(it["map"]["lo"], it["map"]["hi"]), pts[0][4]]] + pts
    if pts[-1][0] != MAXR:
        pts = pts + [[MAXR, MAXR, "(표)", max(it["map"]["lo"], it["map"]["hi"]) if pts[-1][3] > pts[0][3] else min(it["map"]["lo"], it["map"]["hi"]), pts[0][4]]]
    end_stale = []                                           # 끝 읽기가 바로 안쪽 점과 같으면 이동 전 값을 읽은 것일 수 있다: 표의 끝값으로 바꿔 맞춰 본다
    lo_t, hi_t = it["map"]["lo"], it["map"]["hi"]
    if len(pts) >= 4 and pts[-1][3] is not None and pts[-1][3] == pts[-2][3] and pts[-1][3] != hi_t:
        pts = pts[:-1] + [[MAXR, MAXR, "(표)", hi_t, pts[0][4]]]
        end_stale.append("hi")
    if len(pts) >= 4 and pts[0][3] is not None and pts[0][3] == pts[1][3] and pts[0][3] != lo_t:
        pts = [[1, 0, "(표)", lo_t, pts[-1][4]]] + pts[1:]
        end_stale.append("lo")
    f = [(p[1] if p[1] else p[0]) / MAXR for p in pts]
    v = [p[3] for p in pts]
    units = [p[4] for p in pts]
    out = {"index": it["index"], "short": it["short"], "type": it["map"]["type"], "lo": it["map"]["lo"], "hi": it["map"]["hi"],
           "texts": [p[2] for p in pts], "stale": stale, "end_stale": end_stale, "ends": [v[0], v[-1]]}
    if any(x is None for x in v):
        return {**out, "verdict": "unreadable"}
    if not all(same_unit(units[0], u) for u in units):
        return {**out, "verdict": "unit_switch"}
    v0, v1 = v[0], v[-1]
    if v0 == v1:
        return {**out, "verdict": "flat"}
    span = abs(v1 - v0)
    out["ends_moved"] = max(abs(v0 - out["lo"]), abs(v1 - out["hi"])) / span > 0.02 and \
        max(abs(v0 - out["hi"]), abs(v1 - out["lo"])) / span > 0.02           # 표의 lo·hi와 이번 양 끝이 2 % 넘게 다름(뒤집힌 경우는 같다고 봄)
    inner = list(zip(f[1:-1], v[1:-1]))
    e_lin = max(abs((x - v0) / (v1 - v0) - fx) for fx, x in inner)
    e_log = None
    if v0 > 0 and v1 > 0 and all(x > 0 for _fx, x in inner):
        e_log = max(abs(math.log(x / v0) / math.log(v1 / v0) - fx) for fx, x in inner)
    out.update(e_lin=round(e_lin, 3), e_log=None if e_log is None else round(e_log, 3))
    cur = e_lin if out["type"] == "linear" else (e_log if e_log is not None else 9.0)
    other_name, other = ("log", e_log) if out["type"] == "linear" else ("linear", e_lin)
    out["e_cur"] = round(cur, 3)
    if cur <= FIT:
        out["verdict"] = "ok"
    elif other is not None and other <= FIT and cur >= MISS:
        out["verdict"] = f"retype:{other_name}"
    elif cur < MISS and (other is None or other >= cur):
        out["verdict"] = "close"                                               # 2~5 %: 표시 반올림일 수 있다
    else:
        out["verdict"] = "neither"
        fm, xm = inner[len(inner) // 2]
        r = (xm - v0) / (v1 - v0)
        if 0 < r < 1 and 0 < fm < 1:
            out["power"] = round(math.log(r) / math.log(fm), 2)                # 값 = lo + (hi-lo)·f^p 로 봤을 때의 p(가운데 점)
    return out


recs = [json.loads(ln) for ln in open(sys.argv[1])]
rows, errors = [], []
for r in recs:
    if r.get("error"):
        errors.append((r["plugin"], r["error"][:140]))
    for it in r.get("items", []):
        rows.append({"plugin": r["plugin"], **analyse(it)})
if "--json" in sys.argv:
    json.dump(rows, open(sys.argv[sys.argv.index("--json") + 1], "w"), ensure_ascii=False, indent=1)
if "--detail" in sys.argv:
    name = sys.argv[sys.argv.index("--detail") + 1]
    for x in rows:
        if x["plugin"] == name:
            print(x["index"], x["short"], x["type"], x["lo"], x["hi"], x["verdict"], "e_lin", x.get("e_lin"), "e_log", x.get("e_log"), x["texts"])
    sys.exit(0)
from collections import Counter
print(f"플러그인 {len(recs)}, 항목 {len(rows)}, 오류 {len(errors)}")
for p, e in errors[:20]:
    print(f"  오류 {p}: {e}")
print("판정:", dict(Counter(x["verdict"] for x in rows)))
for kind in ("linear", "log"):
    sub = [x for x in rows if x["type"] == kind]
    pos = [x for x in sub if min(x["lo"], x["hi"]) > 0]
    print(f"  표 종류 {kind}: {len(sub)}개(양수 범위 {len(pos)}) →", dict(Counter(x["verdict"] for x in sub)))
samp = [x for x in rows if x["type"] == "linear" and min(x["lo"], x["hi"]) <= 0]
print(f"  0·음수 범위 linear 표본 {len(samp)}개 →", dict(Counter(x["verdict"] for x in samp)))
for verdict in ("retype:log", "retype:linear", "neither", "unit_switch", "unreadable", "flat"):
    sel = [x for x in rows if x["verdict"] == verdict]
    if sel:
        print(f"-- {verdict} ({len(sel)})")
        for x in sel[:60]:
            print(f"  {x['plugin'][:20]:20} {x['index']:3} {x['short'][:9]:9} {x['type']:6} {x['lo']:g}~{x['hi']:g} "
                  f"e_lin {x.get('e_lin')} e_log {x.get('e_log')} p {x.get('power', '')} {x['texts'][1:4]}")
moved = [x for x in rows if x.get("ends_moved")]
print(f"-- 표의 lo·hi와 이번 양 끝이 다름 ({len(moved)})")
for x in moved[:30]:
    print(f"  {x['plugin'][:20]:20} {x['index']:3} {x['short'][:9]:9} 표 {x['lo']:g}~{x['hi']:g} 이번 {x['texts'][0]!r}~{x['texts'][-1]!r}")
