"""번들 파라미터 표 만들기(스펙 §6.1). 테스트 프로젝트(저장 안 함)의 strip 빈 슬롯에 플러그인을 넣고 calibrate → 제거.
--write면 src/logic_mcp/logic/plugins/known.json에 합친다. --yes면 시작 확인(Enter)을 건너뛴다.
사용: uv run python scripts/calibrate_plugin.py "Channel EQ" [strip=1] [--write] [--yes]"""
import sys
from datetime import date

from logic_mcp.logic.plugins.cache import BUNDLED, merge_bundled
from logic_mcp.server.main import build

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    sys.exit(__doc__)
name = args[0]
strip = int(args[1]) if len(args) > 1 else 1
print(f"경고: 지금 열린 Logic 프로젝트의 스트립 {strip}에 {name}을 넣고 값을 되돌리지 않고 움직인다. "
      "테스트 프로젝트에서만 쓰고 끝난 뒤 저장하지 말 것.")
if "--yes" not in sys.argv:
    input("계속하려면 Enter, 그만두려면 Ctrl-C: ")
commands, surface = build()
surface.start()
try:
    print("ready:", commands.wait_ready(60).after["state"], "configure:", commands.configure().note)
    inv = commands.plugin.list(strip, None)
    row = next(iter(inv.after["tracks"].values())) if inv.ok and inv.after else None
    slot = next((int(s) for s, v in (row or {}).items() if v is None), None)
    if slot is None:
        sys.exit(f"스트립 {strip}에 빈 슬롯 없음: {inv.note}")
    r = commands.plugin.insert(strip, None, slot, name)
    print(f"insert {name} → 슬롯 {slot}:", r.verified, r.note)
    if not r.ok:
        sys.exit(1)
    full = r.after["plugin"]
    r = commands.plugin.calibrate(strip, None, slot)
    print("calibrate:", r.verified, r.note)
    for it in (r.after or {}).get("items", []):
        print(f"  {it['index']:3} {it['short']:7} {str(it.get('name')):28} {it.get('map')}")
    print("remove:", commands.plugin.remove(strip, None, slot).verified)
    if r.ok and "--write" in sys.argv:
        merge_bundled(BUNDLED, full, commands.plugin.cache.param_table(full), date.today().isoformat())
        print("known.json 갱신:", full)
finally:
    surface.stop()
