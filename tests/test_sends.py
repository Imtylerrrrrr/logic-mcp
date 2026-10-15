import math

from logic_mcp.logic.sends import bus_number, col_of, dest_query, page_of, parse_send, pos_of_text, se_page_of
from logic_mcp.mcu.state import View, lcd_columns


def cols(r1: str, r2: str):
    return lcd_columns((r1.ljust(56), r2.ljust(56)))


def test_column_and_page_math():
    assert [col_of(1, f) for f in ("dest", "level", "pos", "mute")] == [0, 1, 2, 3]
    assert col_of(2, "dest") == 4 and col_of(8, "mute") == 7
    assert [page_of(s) for s in range(1, 9)] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert se_page_of(View(columns=cols("Sen3In -      -      -      Sen4In -      -      -      ", ""))) == 2
    assert se_page_of(View(columns=cols("Sen1De 1      Sen1Po Sen1Mu Sen2De -      -      -      ", ""))) == 1
    assert se_page_of(View(columns=cols("Sen9In -      -      -      Sen10I -      -      -      ", ""))) == 5
    assert se_page_of(View(columns=cols("Send 1 Destination   -      Sen2In -      -      -      ", ""))) is None


def test_bus_number_pos_and_dest_query():
    assert bus_number("Bus 2") == 2 and bus_number("*Bus 12 ") == 12 and bus_number("--") == 0
    assert bus_number("1") is None and bus_number("") is None and bus_number("Aux 1") is None
    assert [pos_of_text(t) for t in ("Pre", "Post", "PosPan", "Post Pa", "Post Pan", "")] == ["pre", "post", "post_pan", "post_pan", "post_pan", None]
    assert dest_query("Bus 3") == 3 and dest_query("3") == 3 and dest_query(3) == 3 and dest_query("bus 12") == 12
    assert dest_query("--") == 0 and dest_query("") == 0 and dest_query(0) == 0
    assert dest_query("Aux 1") is None and dest_query(257) is None and dest_query(True) is None and dest_query(None) is None


def test_parse_send_by_position_only():                                             # 실측 S2·S9
    c = cols("Sen1De 1      Sen1Po Sen1Mu Sen2In -      -      -      ",
             "*Bus 2 -29.2 dPosPan muted  --                          ")
    s1 = parse_send(c, 1)
    assert s1 == {"send": 1, "present": True, "dest": "Bus 2", "bus": 2, "level_db": -29.2, "pos": "post_pan", "muted": True,
                  "text": ["*Bus 2", "-29.2 d", "PosPan", "muted"]}
    assert parse_send(c, 2) == {"send": 2, "present": False, "dest": None, "bus": None, "level_db": None, "pos": None,
                                "muted": None, "text": ["--", "", "", ""]}
    c = cols("Sen3In 1  Aux 1      Sen3Mu Sen4In -      -      -      ", "Bus 2  -oodB  Pre    active --")
    s3 = parse_send(c, 3)
    assert s3["level_db"] == -math.inf and s3["pos"] == "pre" and s3["muted"] is False and s3["bus"] == 2
