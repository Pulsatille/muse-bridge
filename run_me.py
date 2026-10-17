#!/usr/bin/env python3
# 一键装配/自检/打包脚本（muse-bridge 发布辅助）
# 用法:
#   python run_me.py          # 检查环境并打印状态
#   python run_me.py --check  # py_compile 全部核心模块 + MCP initialize 握手
#   python run_me.py --build  # 构建可安装 wheel
import sys, os, subprocess, json

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'src')

def _py():
    return sys.executable

def check():
    # cli.py 为脚本式模块，仅做语法检查（py_compile），避免 import 触发浏览器副作用
    mod_files = ['mcp_server.py', 'worker.py', 'accounts.py', 'cli.py']
    for m in mod_files:
        f = os.path.join(SRC, m)
        r = subprocess.run([_py(), '-m', 'py_compile', f], capture_output=True, text=True, encoding='utf-8')
        print('  py_compile %-24s %s' % (m, 'OK' if r.returncode == 0 else 'FAIL\n' + (r.stderr or '')[-500:]))
        if r.returncode != 0:
            return 1
    p = subprocess.run([_py(), '-X', 'utf8', '-m', 'muse_bridge.mcp_server'],
                       input=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}) + '\n',
                       capture_output=True, text=True, encoding='utf-8', timeout=30)
    out = p.stdout.strip().splitlines()
    ok = any('"serverInfo"' in ln and 'muse-bridge' in ln for ln in out)
    print('  MCP initialize 握手 %s' % ('OK' if ok else 'FAIL: ' + (p.stdout + p.stderr)[-300:]))
    return 0 if ok else 1

def build():
    r = subprocess.run([_py(), '-m', 'pip', 'install', '--quiet', 'build'], capture_output=True)
    r = subprocess.run([_py(), '-m', 'build', '--wheel', BASE], capture_output=True, text=True, encoding='utf-8')
    print(r.stdout[-1000:] if r.returncode == 0 else (r.stderr or '')[-1000:])
    return r.returncode

if __name__ == '__main__':
    args = sys.argv[1:]
    if '--build' in args:
        sys.exit(build())
    sys.exit(check())
