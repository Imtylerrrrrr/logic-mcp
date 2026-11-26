"""실기 기록 두 실행을 단계별로 견준다(ok·verified·note·after가 같은지, 걸린 시간은 참고). 사용: scripts/live_smoke_diff.py <jsonl> <label1> <label2>   (label = live_smoke.py에 준 이름)"""
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
a = [r for r in rows if r["label"] == sys.argv[2]]
b = [r for r in rows if r["label"] == sys.argv[3]]
same = diff = 0
if [r["step"] for r in a] != [r["step"] for r in b]:
    print("!! 단계 목록이 다름:", len(a), len(b))
for x, y in zip(a, b):
    keys = ("ok", "verified", "note", "after")
    if all(x[k] == y[k] for k in keys):
        same += 1
        continue
    diff += 1
    print(f"다름 [{x['step']}]")
    for k in keys:
        if x[k] != y[k]:
            print(f"   {k}: {json.dumps(x[k], ensure_ascii=False)[:200]}\n   {' ' * len(k)}  {json.dumps(y[k], ensure_ascii=False)[:200]}")
ta, tb = sum(r["ms"] for r in a) / 1000, sum(r["ms"] for r in b) / 1000
slow = [(x["step"], x["ms"], y["ms"]) for x, y in zip(a, b) if abs(x["ms"] - y["ms"]) > 700]
print(f"{sys.argv[2]} 대 {sys.argv[3]}: {len(a)}단계 중 같음 {same}, 다름 {diff} / 합계 {ta:.1f}s 대 {tb:.1f}s / 0.7초 넘게 차이 난 단계 {slow}")
