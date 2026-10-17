# -*- coding: utf-8 -*-
# muse-bridge 核心测试（无需登录、无网络，仅结构/语法/协议层）
# 运行: python -m pytest tests/ 或 python tests/test_core.py
import json, os, subprocess, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
# 子进程也继承 PYTHONPATH=src，使 `-m muse_bridge` 可被找到
_ENV = dict(os.environ)
_ENV['PYTHONPATH'] = SRC + os.pathsep + _ENV.get('PYTHONPATH', '')


def test_tools_schema():
    from muse_bridge import mcp_server
    names = {t['name'] for t in mcp_server.TOOLS}
    assert names == {'muse_send', 'muse_poll', 'muse_status', 'muse_accounts', 'muse_export'}
    req = next(t for t in mcp_server.TOOLS if t['name'] == 'muse_send')
    assert 'prompt' in req['inputSchema']['required']


def test_initialize_handshake():
    p = subprocess.run(
        [sys.executable, '-X', 'utf8', '-m', 'muse_bridge.mcp_server'],
        input=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}) + '\n',
        capture_output=True, text=True, encoding='utf-8', timeout=30, env=_ENV)
    out = p.stdout.strip().splitlines()
    assert any('"serverInfo"' in ln and 'muse-bridge' in ln for ln in out), p.stdout + p.stderr


def test_accounts_list_no_crash():
    p = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'muse_bridge.accounts', 'list'],
                       capture_output=True, text=True, encoding='utf-8', timeout=60, env=_ENV)
    assert p.returncode == 0, p.stderr


if __name__ == '__main__':
    import traceback
    ok = 0
    for fn in [test_tools_schema, test_initialize_handshake, test_accounts_list_no_crash]:
        try:
            fn()
            print('PASS', fn.__name__)
            ok += 1
        except Exception:
            print('FAIL', fn.__name__)
            traceback.print_exc()
    print('%d/3 passed' % ok)
    sys.exit(0 if ok == 3 else 1)
