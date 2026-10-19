import json
from pathlib import Path

from logic_mcp.logic.plugins.cache import BUNDLED, PluginCache, logic_version
from logic_mcp.logic.plugins.match import find, normalize


def test_bundled_known_json_shape():
    data = json.loads(BUNDLED.read_text())
    assert data["list"][0] == "--" and "Channel EQ" in data["list"] and "Compressor" in data["list"]
    assert data["list"].index("Channel EQ") == 55 and data["list"].index("DeEsser") == 20   # 실측 인덱스
    assert data["abbrev"]["Cha EQ"] == "Channel EQ"
    assert data["params"]["Channel EQ"]["pages"] == 6
    assert data["params"]["Channel EQ"]["items"][0] == {"index": 1, "short": "LoCutS", "name": "Low Cut Slope",
                                                        "map": {"type": "enum", "options": ["6", "12", "18", "24", "36", "48"]}}
    assert data["complete"] is False


def test_logic_version_reads_plist(tmp_path):
    import plistlib
    p = tmp_path / "Info.plist"
    p.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "12.0.1"}))
    assert logic_version(p) == "12.0.1"
    assert logic_version(tmp_path / "missing.plist") == "unknown"


def test_cache_merges_bundled_and_user(tmp_path):
    c = PluginCache.load(version="12.0.1", user_dir=tmp_path)
    assert c.source == "bundled" and c.items[55] == "Channel EQ" and c.scanned_at is None
    assert c.path == tmp_path / "plugins-12.0.1.json"
    c.user_list = ["--", "Compressor", "Channel EQ", "FabFilter Pro-Q 3 (s/"]
    c.scanned_at = "2026-10-15T12:00:00"
    c.learn_abbrev("Compre", "Compressor")
    c.save()
    c2 = PluginCache.load(version="12.0.1", user_dir=tmp_path)
    assert c2.source == "scan" and c2.items[2] == "Channel EQ" and c2.abbrev["Compre"] == "Compressor"
    assert c2.abbrev["Cha EQ"] == "Channel EQ"                     # 번들 축약은 유지
    assert c2.param_table("Channel EQ")["pages"] == 6 and c2.param_table("Nope") is None
    res = c2.to_resource()
    assert res["source"] == "scan" and res["scanned_count"] == 4 and res["items"][1] == {"index": 1, "name": "Compressor"}


def test_normalize_strips_channel_suffix_and_truncation():
    assert normalize("Channel EQ (s/s)") == "channeleq"
    assert normalize("High Pass Filter (s/s") == "highpassfilter"
    assert normalize("  Space-Designer ") == "spacedesigner"
    assert normalize("EVOC 20 TrackOscillat") == "evoc20trackoscillat"


def test_find_exact_prefix_partial_and_ambiguous():
    items = ["--", "Parametric EQ", "Compressor", "Silver Compressor (s/", "Channel EQ", "EVOC 20 TrackOscillat"]
    assert find(items, "Compressor") == (2, ["Compressor"])
    assert find(items, "channel eq (s/s)") == (4, ["Channel EQ"])
    assert find(items, "EVOC 20 TrackOscillator") == (5, ["EVOC 20 TrackOscillat"])   # 21자 잘림
    idx, cands = find(items, "EQ")
    assert idx is None and set(cands) == {"Parametric EQ", "Channel EQ"}
    assert find(items, "Tuner") == (None, [])
    assert find(items, "--") == (None, [])


def test_load_moves_corrupt_user_file_aside(tmp_path):                  # 리뷰 I5
    (tmp_path / "plugins-12.0.1.json").write_text("{깨진 json")
    c = PluginCache.load(version="12.0.1", user_dir=tmp_path)
    assert c.user_list == [] and c.bundled_list
    assert not (tmp_path / "plugins-12.0.1.json").exists()
    assert len(list(tmp_path.glob("plugins-12.0.1.json.bad-*"))) == 1


def test_load_moves_non_dict_user_file_aside(tmp_path):                 # 리뷰 I5
    (tmp_path / "plugins-12.0.1.json").write_text("[1, 2]")
    c = PluginCache.load(version="12.0.1", user_dir=tmp_path)
    assert c.user_list == [] and len(list(tmp_path.glob("*.bad-*"))) == 1


def test_save_leaves_no_tmp_file(tmp_path):                             # 리뷰 I5
    c = PluginCache.load(version="12.0.1", user_dir=tmp_path)
    c.save()
    assert c.path.exists() and not list(tmp_path.glob("*.tmp"))


def test_save_writes_only_entries_that_differ_from_bundle(tmp_path):          # 리뷰 m4
    bundled = tmp_path / "known.json"
    bundled.write_text(json.dumps({"logic_version": "12.0.1", "generated": "2026-10-15", "list": ["--", "Compressor", "Channel EQ"],
                                   "abbrev": {"Cha EQ": "Channel EQ"}, "params": {"Channel EQ": {"pages": 6, "items": []}}}))
    c = PluginCache.load(version="12.0.1", user_dir=tmp_path, bundled=bundled)
    c.learn_abbrev("Comprs", "Compressor")
    c.params["Compressor"] = {"pages": 3, "items": [{"index": 2, "short": "Thrs", "name": None, "map": None}]}
    c.save()
    saved = json.loads(c.path.read_text())
    assert saved["abbrev"] == {"Comprs": "Compressor"} and list(saved["params"]) == ["Compressor"]
    assert saved["bundled_generated"] == "2026-10-15"
    bundled.write_text(bundled.read_text().replace('"pages": 6', '"pages": 7'))        # 번들이 갱신돼도
    c2 = PluginCache.load(version="12.0.1", user_dir=tmp_path, bundled=bundled)
    assert c2.param_table("Channel EQ")["pages"] == 7                                    # 사용자 파일이 가리지 않는다
    assert c2.param_table("Compressor")["pages"] == 3 and c2.abbrev["Cha EQ"] == "Channel EQ"
    c2.params["Channel EQ"]["pages"] = 9                                                 # 번들 항목을 고치면 그 항목만 사용자 파일에
    c2.save()
    assert set(json.loads(c2.path.read_text())["params"]) == {"Compressor", "Channel EQ"}
    c3 = PluginCache.load(version="12.0.1", user_dir=tmp_path, bundled=bundled)
    assert c3.bundled_params["Channel EQ"]["pages"] == 7 and c3.param_table("Channel EQ")["pages"] == 9


def test_merge_bundled_replaces_table_and_generated(tmp_path):
    from logic_mcp.logic.plugins.cache import merge_bundled
    bundled = tmp_path / "known.json"
    bundled.write_text(json.dumps({"logic_version": "12.0.1", "generated": "2026-10-15", "list": ["--"], "abbrev": {},
                                   "params": {"A": {"pages": 1, "items": []}}}))
    table = {"pages": 2, "items": [{"index": 1, "short": "X", "name": "X", "map": None}]}
    data = merge_bundled(bundled, "B", table, "2026-10-17")
    assert data["params"]["B"] == table and data["params"]["A"]["pages"] == 1 and data["generated"] == "2026-10-17"
    assert json.loads(bundled.read_text()) == data and not list(tmp_path.glob("*.tmp"))
    assert bundled.read_text().startswith('{\n  "logic_version"')         # 2칸 들여쓰기(리뷰 M3)


def _m2_setup(tmp_path, user_extra):
    bundled = tmp_path / "known.json"
    B = {"pages": 5, "items": []}
    U = {"pages": 2, "items": []}
    M = {"pages": 1, "items": []}
    bundled.write_text(json.dumps({"logic_version": "12.0.1", "generated": "2026-10-19", "list": ["--", "Compressor"],
                                   "abbrev": {}, "params": {"Compressor": B}}))
    (tmp_path / "plugins-12.0.1.json").write_text(json.dumps({"params": {"Compressor": U, "MyPlug": M}, **user_extra}))
    return PluginCache.load(version="12.0.1", user_dir=tmp_path, bundled=bundled), B, U, M


def test_load_drops_user_tables_for_bundled_keys_when_bundle_regenerated(tmp_path):      # 리뷰 M2
    c, B, _, M = _m2_setup(tmp_path, {"bundled_generated": "2026-10-01"})
    assert c.params["Compressor"] == B and c.params["MyPlug"] == M


def test_load_old_format_user_file_without_bundled_generated_yields_to_bundle(tmp_path):   # 리뷰 M2
    c, B, _, M = _m2_setup(tmp_path, {})
    assert c.params["Compressor"] == B and c.params["MyPlug"] == M


def test_load_keeps_user_tables_when_bundle_unchanged(tmp_path):                           # 리뷰 M2
    c, _, U, _ = _m2_setup(tmp_path, {"bundled_generated": "2026-10-19"})
    assert c.params["Compressor"] == U
