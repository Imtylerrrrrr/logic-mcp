"""stdio 스모크: 서버를 띄워 initialize만 주고받는다(Logic에 명령을 보내지 않는다).

사용: uv run python scripts/smoke_stdio.py [명령…]   (기본: uv run logic-mcp)
"""
import json
import subprocess
import sys
import threading

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "smoke", "version": "0"}}}


def main() -> int:
    cmd = sys.argv[1:] or ["uv", "run", "logic-mcp"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    line: list[str] = []
    try:
        proc.stdin.write(json.dumps(INIT) + "\n")
        proc.stdin.flush()
        reader = threading.Thread(target=lambda: line.append(proc.stdout.readline()), daemon=True)
        reader.start()
        reader.join(30)
        if not line or not line[0]:
            print("fail: 30초 안에 응답 없음 또는 서버 종료")
            return 1
        info = json.loads(line[0]).get("result", {}).get("serverInfo", {})
        if not info.get("name"):
            print(f"fail: serverInfo 없음: {line[0][:200].strip()}")
            return 1
        print(f"ok name={info['name']} version={info.get('version')}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"fail: {e}")
        return 1
    finally:
        proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
