# -*- coding: utf-8 -*-
"""cred_bundle.py — 中转站式凭证包：一次登录 → 打包标准格式 → 任意机器/服务器一条命令加载 → 多账号池就绪。

格式（tar.gz，manifest 驱动，带校验）：
  manifest.json          # {version, created, generator, accounts:{id:{label,days_left,cookies,localStorage,auth_sha256,profile_bundled}}}
  registry.json          # 路径已改写为相对（accounts/<id>/auth.json），到新机由 _resolve 自愈
  auth/<id>.json         # Playwright storage_state（cookies+localStorage）
  profiles/<id>.tar.gz   # 仅 --with-profiles 时包含（运行态浏览器 profile，体积大默认不带）

子命令:
  pack <out.tar.gz> [--accounts id1,id2] [--with-profiles]
  unpack <in.tar.gz> [--dest DIR] [--merge] [--verify] [--force]
  inspect <in.tar.gz>                    # 只读包内容，不落盘
"""
import sys, os, json, time, hashlib, tarfile, tempfile, argparse, io
from pathlib import Path

from muse_bridge.accounts import (BASE, ACC_ROOT, REG, load_reg, save_reg, _resolve,
                                  sess_days_left)

BUNDLE_VERSION = 1


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def chosen_ids(csv):
    r = load_reg()
    if csv:
        return [x.strip() for x in csv.split(",") if x.strip()]
    return list(r.get("accounts", {}).keys())


def cmd_pack(a):
    ids = chosen_ids(a.accounts)
    if not ids:
        print(json.dumps({"ok": False, "error": "no accounts to pack"})); return 1
    r = load_reg()
    manifest = {"version": BUNDLE_VERSION,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "generator": "muse-bridge/cred_bundle",
                "default": r.get("default"),
                "accounts": {}}
    out_reg = {"default": r.get("default"), "accounts": {}}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for aid in ids:
            cfg = r.get("accounts", {}).get(aid, {})
            apath = _resolve(cfg.get("auth"))
            if not apath or not Path(apath).exists():
                manifest["accounts"][aid] = {"skipped": "auth missing", "auth": apath}
                continue
            raw = Path(apath).read_bytes()
            sd = json.loads(raw.decode("utf-8"))
            cookies = sd.get("cookies", [])
            localst = sum(len(o.get("localStorage", [])) for o in sd.get("origins", []))
            # 规范化存储（历史文件缩进/键序不一），校验和必须对**存入包的字节**计算，
            # 否则 unpack 端对不上（跨机实测抓出的真 bug）。
            blob = json.dumps(sd, ensure_ascii=False, indent=2).encode("utf-8")
            arc_auth = "auth/%s.json" % aid
            _add(tf, arc_auth, blob)
            rel_auth = "accounts/%s/auth.json" % aid
            rel_prof = "accounts/%s/profile" % aid
            out_reg["accounts"][aid] = {"profile": rel_prof, "auth": rel_auth,
                                       "proxy": cfg.get("proxy"),
                                       "label": cfg.get("label", aid),
                                       "quota_note": cfg.get("quota_note", "")}
            ent = {"label": cfg.get("label", aid),
                   "days_left": sess_days_left(apath),
                   "cookies": len(cookies),
                   "localStorage": localst,
                   "auth_sha256": sha256_bytes(blob),
                   "profile_bundled": False}
            if a.with_profiles:
                prof = _resolve(cfg.get("profile"))
                if prof and Path(prof).exists():
                    arc_prof = "profiles/%s.tar.gz" % aid
                    pbuf = io.BytesIO()
                    with tarfile.open(fileobj=pbuf, mode="w:gz") as pt:
                        pt.add(prof, arcname="profile")
                    _add(tf, arc_prof, pbuf.getvalue())
                    ent["profile_bundled"] = True
            manifest["accounts"][aid] = ent
        _add(tf, "registry.json", json.dumps(out_reg, ensure_ascii=False, indent=2).encode("utf-8"))
        _add(tf, "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    data = buf.getvalue()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    loaded = {k: v for k, v in manifest["accounts"].items() if "auth_sha256" in v}
    print(json.dumps({"ok": True, "out": str(out), "bytes": len(data),
                      "accounts": len(loaded),
                      "skipped": [k for k, v in manifest["accounts"].items() if "skipped" in v],
                      "with_profiles": bool(a.with_profiles)}, ensure_ascii=False))
    return 0


def _add(tf, arcname, data):
    ti = tarfile.TarInfo(arcname)
    ti.size = len(data)
    ti.mtime = int(time.time())
    tf.addfile(ti, io.BytesIO(data))


def _read_tar(path):
    files = {}
    with tarfile.open(path, mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile() and m.size < 200 * 1024 * 1024:
                files[m.name] = tf.extractfile(m).read()
    return files


def cmd_inspect(a):
    files = _read_tar(a.src)
    mf = json.loads(files.get("manifest.json", b"{}").decode("utf-8"))
    print(json.dumps({"ok": True, "src": a.src, "manifest": mf,
                      "files": sorted(files.keys())}, ensure_ascii=False, indent=1))
    return 0


def cmd_unpack(a):
    dest = Path(a.dest) if a.dest else BASE
    files = _read_tar(a.src)
    if "manifest.json" not in files:
        print(json.dumps({"ok": False, "error": "not a cred_bundle (no manifest.json)"})); return 1
    mf = json.loads(files["manifest.json"].decode("utf-8"))
    if int(mf.get("version", 0)) != BUNDLE_VERSION:
        print(json.dumps({"ok": False, "error": "bundle version mismatch: %s != %s" % (mf.get("version"), BUNDLE_VERSION)})); return 1
    src_reg = json.loads(files.get("registry.json", b"{}").decode("utf-8"))
    results, bad = [], []
    for aid, ent in mf.get("accounts", {}).items():
        arc = "auth/%s.json" % aid
        if arc not in files:
            bad.append({"id": aid, "reason": ent.get("skipped", "no auth in bundle")}); continue
        raw = files[arc]
        if sha256_bytes(raw) != ent.get("auth_sha256"):
            bad.append({"id": aid, "reason": "checksum mismatch"}); continue
        adir = dest / "accounts" / aid
        apath = adir / "auth.json"
        pdir = adir / "profile"
        if apath.exists() and not a.force and not a.merge:
            bad.append({"id": aid, "reason": "exists (use --force to overwrite)"}); continue
        adir.mkdir(parents=True, exist_ok=True)
        apath.write_bytes(raw)
        # profile 包（可选）：解到 accounts/<id>/profile
        p_arc = "profiles/%s.tar.gz" % aid
        if ent.get("profile_bundled") and p_arc in files:
            pdir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=io.BytesIO(files[p_arc]), mode="r:gz") as pt:
                for m in pt.getmembers():
                    rel = os.path.relpath(m.name, "profile")
                    if rel.startswith(".."):
                        continue
                    tgt = pdir / rel
                    if m.isdir():
                        tgt.mkdir(parents=True, exist_ok=True)
                    else:
                        tgt.parent.mkdir(parents=True, exist_ok=True)
                        with open(tgt, "wb") as fh:
                            fh.write(pt.extractfile(m).read())
        results.append({"id": aid, "auth": str(apath), "days_left": ent.get("days_left"),
                        "cookies": ent.get("cookies"), "profile_bundled": ent.get("profile_bundled", False)})
    # registry 合并：路径写相对（_resolve 按各自 BASE 展开）
    r = load_reg() if REG.exists() else {"default": None, "accounts": {}}
    if dest != BASE:
        r = {"default": None, "accounts": {}}
    for x in results:
        aid = x["id"]
        e = r.setdefault("accounts", {}).setdefault(aid, {})
        e["auth"] = "accounts/%s/auth.json" % aid
        if not e.get("profile"):
            e["profile"] = "accounts/%s/profile" % aid
        src_e = src_reg.get("accounts", {}).get(aid, {})
        e.setdefault("label", src_e.get("label", aid))
        e.setdefault("proxy", src_e.get("proxy"))
        e.setdefault("quota_note", src_e.get("quota_note", ""))
        e["imported_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if not r.get("default"):
        r["default"] = src_reg.get("default") or (results[0]["id"] if results else None)
    if dest == BASE:
        save_reg(r)
        reg_path = str(REG)
    else:
        (dest / "accounts").mkdir(parents=True, exist_ok=True)
        reg_path = str(dest / "accounts" / "registry.json")
        Path(reg_path).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    verify = []
    if a.verify:
        for x in results:
            ok = _verify_one(x["id"])
            verify.append({"id": x["id"], "credential_valid": ok})
    print(json.dumps({"ok": bool(results), "dest": str(dest), "loaded": len(results),
                      "accounts": results, "rejected": bad, "registry": reg_path,
                      "verify": verify or None}, ensure_ascii=False, indent=1))
    return 0 if results and not bad else (0 if results else 1)


def _verify_one(aid):
    """纯凭证验证（不依赖 profile）：auth.json → 一次性 context → composer 出现即真。"""
    try:
        from muse_bridge.cred_extract import cmd_verify
        class _A:
            pass
        va = _A(); va.id = aid; va.timeout = 60
        rc = cmd_verify(va)
        return rc == 0
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("pack"); x.add_argument("out"); x.add_argument("--accounts"); x.add_argument("--with-profiles", action="store_true")
    x = sub.add_parser("unpack"); x.add_argument("src"); x.add_argument("--dest"); x.add_argument("--merge", action="store_true"); x.add_argument("--verify", action="store_true"); x.add_argument("--force", action="store_true")
    x = sub.add_parser("inspect"); x.add_argument("src")
    a = ap.parse_args()
    return {"pack": cmd_pack, "unpack": cmd_unpack, "inspect": cmd_inspect}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
