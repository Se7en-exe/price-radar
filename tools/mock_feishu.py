# -*- coding: utf-8 -*-
"""本地假飞书 Webhook：验证「推」这一步真的发出去了。

跑：python tools/mock_feishu.py
然后 crawl 时用 --webhook http://127.0.0.1:8899/hook
收到的每条 payload 会打印并追加到 out/received.jsonl
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = os.path.join("out", "received.jsonl")


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(n).decode("utf-8", "replace")
        try:
            body = json.loads(raw)
            title = (body.get("card", {}).get("header", {}).get("title", {}) or {}).get("content", "")
            print("[feishu] 收到卡片:", title)
        except Exception:
            body, title = {"raw": raw}, ""
        os.makedirs("out", exist_ok=True)
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, ensure_ascii=False) + "\n")
        resp = json.dumps({"code": 0, "msg": "success"}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("mock feishu webhook -> http://127.0.0.1:8899/hook")
    HTTPServer(("127.0.0.1", 8899), H).serve_forever()
