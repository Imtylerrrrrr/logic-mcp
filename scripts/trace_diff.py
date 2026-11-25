"""scripts/trace_plugin.py가 남긴 두 기록을 테스트별로 비교한다. 다른 테스트가 있거나 기준에만 있는 테스트가 있으면 종료 코드 1.
사용: scripts/trace_diff.py <base.jsonl> <new.jsonl> [--show N]"""
import json, sys

def load(p):
    return {r["test"]: r for r in map(json.loads, open(p))}

a, b = load(sys.argv[1]), load(sys.argv[2])
show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 3
only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
diff = [t for t in a if t in b and (a[t]["log"] != b[t]["log"] or a[t]["passed"] != b[t]["passed"])]
tx = sum(1 for r in a.values() for e in r["log"] if e[0] == "tx")
res = sum(1 for r in a.values() for e in r["log"] if e[0] == "result")
print(f"기준 {len(a)}개 테스트(MIDI {tx}건, 결과 {res}건) / 새 {len(b)}개 / 다른 테스트 {len(diff)}개 / 기준에만 {len(only_a)} / 새 쪽에만 {len(only_b)}")
for t in only_a[:5]: print("  기준에만:", t)
for t in only_b[:5]: print("  새 쪽에만:", t)
for t in diff[:show]:
    la, lb = a[t]["log"], b[t]["log"]
    i = next((k for k, (x, y) in enumerate(zip(la, lb)) if x != y), min(len(la), len(lb)))
    print(f"  다름: {t}\n    {i}번째(기준 {len(la)}건, 새 {len(lb)}건)\n    기준: {json.dumps(la[i], ensure_ascii=False)[:300] if i < len(la) else '-'}\n    새:   {json.dumps(lb[i], ensure_ascii=False)[:300] if i < len(lb) else '-'}")
sys.exit(1 if diff or only_a else 0)
