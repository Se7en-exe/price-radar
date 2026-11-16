# -*- coding: utf-8 -*-
"""用 n8n 的 REST 接口手动跑一次指定工作流（等价于在界面上点 Execute）。

用法: python tools/n8n_run.py --wf lXOttNp2370ic7Mt [--user admin@local.dev --pwd PriceRadar123]
"""
from __future__ import annotations

import argparse
import sys

import requests

BASE = "http://127.0.0.1:5678"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf", required=True)
    ap.add_argument("--user", default="admin@local.dev")
    ap.add_argument("--pwd", default="PriceRadar123")
    ap.add_argument("--base", default=BASE)
    a = ap.parse_args()

    s = requests.Session()
    r = s.post(a.base + "/rest/login", json={"emailOrLdapLoginId": a.user, "password": a.pwd}, timeout=20)
    if r.status_code != 200:
        print("login failed", r.status_code, r.text[:200])
        return 1

    r = s.get(a.base + "/rest/workflows/" + a.wf, timeout=20)
    wf = r.json()["data"]

    body = {
        "workflowData": {
            "id": wf["id"],
            "name": wf["name"],
            "nodes": wf["nodes"],
            "connections": wf["connections"],
            "settings": wf.get("settings", {}),
            "pinData": wf.get("pinData", {}),
            "versionId": wf.get("versionId"),
        },
        "runData": {},
        "triggerToStartFrom": {
            "name": next(n["name"] for n in wf["nodes"] if "trigger" in n["type"].lower()),
        },
        "executionMode": "manual",
    }
    r = s.post(a.base + "/rest/workflows/" + a.wf + "/run", json=body, timeout=120)
    print("run ->", r.status_code)
    txt = r.text
    print(txt[:1500])
    return 0 if r.status_code in (200, 201) else 1


if __name__ == "__main__":
    sys.exit(main())
