"""pytest 플러그인(동작 보존 확인용): 테스트마다 보낸 MIDI(가짜 시계 시각 포함)와 만들어진 ToolResult를 전부 기록한다.
같은 테스트를 두 트리(예: 수정 전 커밋의 워크트리와 지금 트리)에서 돌려 scripts/trace_diff.py로 비교하면 동작이 그대로인지 알 수 있다.
사용(트리 루트에서):
  TRACE_TREE=$PWD TRACE_OUT=/tmp/new.jsonl PYTHONPATH=$PWD/src:$PWD/scripts PYTHONDONTWRITEBYTECODE=1 \
      python -m pytest -p trace_plugin -q -p no:cacheprovider tests
TRACE_TREE는 logic_mcp가 그 트리에서 import됐는지 확인하는 데 쓴다(다른 트리의 코드를 재면 곧바로 실패)."""
import json
import os
import re

import pytest

import logic_mcp
from logic_mcp.logic import commands as commands_mod
from logic_mcp.mcu import surface as surface_mod

TREE = os.path.realpath(os.environ["TRACE_TREE"])
assert os.path.realpath(logic_mcp.__file__).startswith(TREE + "/src/"), f"다른 트리의 코드가 import됨: {logic_mcp.__file__}"

LOG: list = []
_send = surface_mod.Surface.send
_init = commands_mod.ToolResult.__init__


def send(self, data):
    LOG.append(["tx", round(self.clock(), 4), bytes(data).hex()])
    return _send(self, data)


def init(self, **kw):
    _init(self, **kw)
    LOG.append(["result", json.loads(self.model_dump_json())])


surface_mod.Surface.send = send
commands_mod.ToolResult.__init__ = init
OUT = open(os.environ["TRACE_OUT"], "w")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    LOG.clear()
    outcome = yield
    line = json.dumps({"test": item.nodeid, "passed": outcome.excinfo is None, "log": list(LOG)}, ensure_ascii=False)
    line = re.sub(r"pytest-\d+", "pytest-N", line)                  # 임시 폴더 번호는 실행마다 다르다
    OUT.write(re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", "T", line) + "\n")   # 스캔 시각은 실제 시계


def pytest_sessionfinish(session):
    OUT.close()
