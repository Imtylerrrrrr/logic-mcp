"""플러그인 목록·축약·파라미터 캐시. 번들(known.json)과 사용자(~/.logic-mcp/plugins-<Logic 버전>.json)를 병합한다.
사용자 목록이 있으면 목록은 사용자 것을 쓰고(설치된 플러그인에 따라 순서가 다름), 축약·파라미터 표는 둘을 합친다.
번들 `generated`가 사용자 파일의 `bundled_generated`와 다르면 번들에 있는 이름의 표는 번들을 쓴다(리뷰 M2)."""
from __future__ import annotations

import copy
import json
import os
import plistlib
from datetime import datetime
from dataclasses import dataclass, field
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
    bundled_abbrev: dict[str, str] = field(default_factory=dict)     # 저장 때 번들과 같은 항목을 빼기 위한 기준(리뷰 m4)
    bundled_params: dict[str, dict] = field(default_factory=dict)
    bundled_generated: str | None = None

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
        b_abbrev, b_params = dict(b.get("abbrev", {})), copy.deepcopy(b.get("params", {}))
        u_params = u.get("params", {})
        if u.get("bundled_generated") != b.get("generated"):          # 번들이 재생성됨 → 번들에 있는 이름은 번들 우선(리뷰 M2)
            u_params = {k: v for k, v in u_params.items() if k not in b_params}
        return cls(version=version, bundled_list=list(b.get("list", [])), user_list=list(u.get("list", [])),
                   abbrev={**b_abbrev, **u.get("abbrev", {})},
                   params={**copy.deepcopy(b_params), **u_params},
                   scanned_at=u.get("scanned_at"), path=path,
                   bundled_abbrev=b_abbrev, bundled_params=b_params, bundled_generated=b.get("generated"))

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
        abbrev = {k: v for k, v in self.abbrev.items() if self.bundled_abbrev.get(k) != v}
        params = {k: v for k, v in self.params.items() if self.bundled_params.get(k) != v}
        tmp.write_text(json.dumps({"logic_version": self.version, "bundled_generated": self.bundled_generated,
                                   "scanned_at": self.scanned_at, "list": self.user_list, "abbrev": abbrev, "params": params},
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


def merge_bundled(bundled: Path, name: str, table: dict, generated: str) -> dict:
    """calibrate 결과 표를 번들 known.json에 넣고(같은 이름은 교체) generated를 갱신해 저장한다. 저장한 전체 dict를 돌려준다."""
    data = json.loads(bundled.read_text())
    data.setdefault("params", {})[name] = table
    data["generated"] = generated
    tmp = bundled.with_name(bundled.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, bundled)
    return data
