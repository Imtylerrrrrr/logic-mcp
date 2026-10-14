from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "mcu"


def test_package_imports():
    import logic_mcp  # noqa: F401


def test_fixtures_present():
    lines = (FIXTURES / "cap_raw6.log").read_text().splitlines()
    assert len(lines) > 4000
    assert lines[0].split()[1] in ("RX", "TX")
