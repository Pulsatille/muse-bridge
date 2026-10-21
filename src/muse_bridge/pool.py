# -*- coding: utf-8 -*-
"""pool.py — 中转站式凭证池：多账号健康度评分 + 自动选路（round-robin + 额度/失效避让）。

用法（CLI）:
  pool status            # 各号：days_left / 连续失败 / 今日用量 / 可用?
  pool next [--task T]   # 按策略选下一个可用账号（输出 id）
  pool use <id> [--ok|--fail]  # 上报一次使用结果（维护失败计数与冷却）
  pool reset <id>        # 清零失败计数（重登/保鲜后调用）

策略（默认）:
  1. 候选 = registry 全部账号且 auth 存在
  2. 剔除：days_left < POOL_MIN_DAYS(默认3) 或 连续失败 >= POOL_MAX_FAILS(默认2)（冷却中）
  3. 排序：连续失败升序 → days_left 降序 → 最近使用时间升序（轮询感）
  4. 返回第一名；全不可用则回退 default（仍返回，但标记 degraded）

worker/MCP 集成：account="pool"（或 POOL=1）即走自动选路。
"""
import sys, os, json, time, argparse
from pathlib import Path

from muse_bridge.accounts import BASE, ACC_ROOT, load_reg, save_reg, _resolve, sess_days_left

POOL_STATE = ACC_ROOT / "pool_state.json"
MIN_DAYS = float(os.environ.get("POOL_MIN_DAYS", "3"))
MAX_FAILS = int(os.environ.get("POOL_MAX_FAILS", "2"))
COOLDOWN_S = int(os.environ.get("POOL_COOLDOWN_S", "3600"))  # 连续失败后的冷却


def _load_state():
    try:
        return json.loads(POOL_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(s):
    POOL_STATE.parent.mkdir(parents=True, exist_ok=True)
    POOL_STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def _today():
    return time.strftime("%Y-%m-%d")


def pool_view():
    r = load_reg()
    st = _load_state()
    out = []
    for aid, cfg in r.get("accounts", {}).items():
        apath = _resolve(cfg.get("auth"))
        exists = bool(apath and Path(apath).exists())
        d = sess_days_left(apath) if exists else None
        u = st.get(aid, {})
        fails = u.get("fails", 0)
        last_fail = u.get("last_fail", 0)
        cooling = fails >= MAX_FAILS and (time.time() - last_fail) < COOLDOWN_S
        usable = exists and d is not None and d >= MIN_DAYS and not cooling
        out.append({"id": aid, "label": cfg.get("label", ""), "default": aid == r.get("default"),
                    "auth": bool(exists), "days_left": d, "fails": fails,
                    "cooling": cooling, "usable": usable,
                    "last_used": u.get("last_used"), "today_uses": u.get("day", {}).get(_today(), 0)})
    return out, r.get("default")


def pick():
    view, default = pool_view()
    usable = [v for v in view if v["usable"]]
    if not usable:
        return {"account": default, "degraded": True, "reason": "no usable account, fallback default"}
    # 失败少 → 剩余天数多 → 最久未用（轮询）
    usable.sort(key=lambda v: (v["fails"], -(v["days_left"] or 0), v.get("last_used") or 0))
    return {"account": usable[0]["id"], "degraded": False, "reason": "pool best", "usable": len(usable)}


def record(aid, ok):
    st = _load_state()
    u = st.setdefault(aid, {"fails": 0, "last_used": 0, "day": {}})
    now = time.time()
    if ok:
        u["fails"] = 0
        u["last_used"] = now
        d = _today()
        u.setdefault("day", {})
        u["day"][d] = u["day"].get(d, 0) + 1
    else:
        u["fails"] = u.get("fails", 0) + 1
        u["last_fail"] = now
    _save_state(st)
    return u


def cmd_status(a):
    view, default = pool_view()
    print(json.dumps({"ok": True, "default": default, "pool": view}, ensure_ascii=False, indent=1))
    return 0


def cmd_next(a):
    p = pick()
    print(json.dumps(p, ensure_ascii=False))
    return 0 if not p.get("degraded") else 1


def cmd_use(a):
    u = record(a.id, a.ok)
    print(json.dumps({"ok": True, "account": a.id, **u}, ensure_ascii=False))
    return 0


def cmd_reset(a):
    st = _load_state()
    st[a.id] = {"fails": 0, "last_used": st.get(a.id, {}).get("last_used", 0), "day": {}}
    _save_state(st)
    print(json.dumps({"ok": True, "reset": a.id}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("next")
    x = sub.add_parser("use"); x.add_argument("id"); g = x.add_mutually_exclusive_group(required=True); g.add_argument("--ok", dest="ok", action="store_true"); g.add_argument("--fail", dest="ok", action="store_false")
    x = sub.add_parser("reset"); x.add_argument("id")
    a = ap.parse_args()
    return {"status": cmd_status, "next": cmd_next, "use": cmd_use, "reset": cmd_reset}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
