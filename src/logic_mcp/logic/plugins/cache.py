"""플러그인 목록·축약·파라미터 캐시. 번들(known.json)과 사용자(~/.logic-mcp/plugins-<Logic 버전>.json)를 병합한다.
사용자 목록이 있으면 목록은 사용자 것을 쓰고(설치된 플러그인에 따라 순서가 다름), 축약·파라미터 표는 둘을 합친다."""
from __future__ import annotations

import json
import os
import plistlib
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

BUNDLED = Path(__file__).with_name("known.json")
USER_DIR = Path.home() / ".logic-mcp"
LOGIC_PLIST = Path("/Applications/Logic Pro.app/Contents/Info.plist")


def logic_version(plist: Path = LOGIC_PLIST) -> str:
    try:
        with plist.open("rb") as f:
            return str(plistlib.load(f).get("CFBundleShortVersionString", "unknown"))
    except (OSError, plistlib.InvalidFileException, ValueError):
        return "unknown"


@dataclass
class PluginCache:
    version: str
    bundled_list: list[str]
    user_list: list[str]
    abbrev: dict[str, str]          # LCD 6자 축약(strip) → 전체 이름
    params: dict[str, dict]         # 플러그인 이름 → {"pages": n, "items": [{"index","short","name","map"}]}
    scanned_at: str | None
    path: Path

    @property
    def items(self) -> list[str]:
        return self.user_list or self.bundled_list

    @property
    def source(self) -> str:
        return "scan" if self.user_list else "bundled"

    @classmethod
    def load(cls, version: str | None = None, user_dir: Path = USER_DIR, bundled: Path = BUNDLED) -> "PluginCache":
        version = version or logic_version()
        b = json.loads(bundled.read_text())
        path = user_dir / f"plugins-{version}.json"
        u = cls._read_user(path)
        return cls(version=version, bundled_list=list(b.get("list", [])), user_list=list(u.get("list", [])),
                   abbrev={**b.get("abbrev", {}), **u.get("abbrev", {})},
                   params={**b.get("params", {}), **u.get("params", {})},
                   scanned_at=u.get("scanned_at"), path=path)

    @staticmethod
    def _read_user(path: Path) -> dict:
        """사용자 파일 읽기. 깨졌으면 `.bad-<시각>`으로 옮기고 빈 dict(번들만으로 시작). 번들 파일 실패는 배포 결함이라 그대로 예외."""
        if not path.exists():
            return {}
        try:
            u = json.loads(path.read_text())
            if isinstance(u, dict):
                return u
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
        try:
            os.replace(path, path.with_name(f"{path.name}.bad-{datetime.now():%Y%m%d-%H%M%S}"))
        except OSError:
            pass
        return {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"logic_version": self.version, "scanned_at": self.scanned_at,
                                   "list": self.user_list, "abbrev": self.abbrev, "params": self.params},
                                  ensure_ascii=False, indent=1))
        os.replace(tmp, self.path)

    def learn_abbrev(self, abbrev: str, name: str) -> None:
        if abbrev.strip() and name:
            self.abbrev[abbrev.strip()] = name

    def param_table(self, name: str) -> dict | None:
        return self.params.get(name)

    def to_resource(self) -> dict:
        return {"logic_version": self.version, "source": self.source, "bundled_count": len(self.bundled_list),
                "scanned_count": len(self.user_list), "scanned_at": self.scanned_at, "path": str(self.path),
                "items": [{"index": i, "name": n} for i, n in enumerate(self.items)],
                "known_params": sorted(self.params)}
