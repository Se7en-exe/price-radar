# -*- coding: utf-8 -*-
"""推送层：飞书自定义机器人 Webhook（支持签名校验、失败重试、干跑）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import requests


def sign(secret: str, timestamp: str) -> str:
    """飞书签名：以 "timestamp\nsecret" 为 key 对空串做 HMAC-SHA256，再 base64。"""
    key = (timestamp + "\n" + secret).encode("utf-8")
    return base64.b64encode(hmac.new(key, b"", digestmod=hashlib.sha256).digest()).decode()


def build_card(alerts, title: str = "") -> dict:
    """把若干条 Alert 拼成一张飞书卡片（interactive）。"""
    worst = "red" if any(a.level == "critical" for a in alerts) else (
        "orange" if any(a.level == "warn" for a in alerts) else "blue")
    head = title or ("竞品价格预警 · %d 条" % len(alerts))
    elements = []
    for a in alerts:
        body = "**%s**" % a.title
        if a.lines:
            body += "\n" + "\n".join(a.lines)
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": body}})
    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": "price-radar · " + time.strftime("%Y-%m-%d %H:%M:%S")}]})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": worst, "title": {"tag": "plain_text", "content": head}},
        "elements": elements,
    }


class Feishu:
    def __init__(self, webhook: str = "", secret: str = "", dry_run: bool = False, timeout: int = 10):
        self.webhook = webhook or os.environ.get("FEISHU_WEBHOOK", "")
        self.secret = secret or os.environ.get("FEISHU_SECRET", "")
        self.dry_run = dry_run or not self.webhook
        self.timeout = timeout

    def send(self, card: dict, retries: int = 3) -> tuple[bool, str]:
        payload = {"msg_type": "interactive", "card": card}
        if self.secret:
            ts = str(int(time.time()))
            payload.update({"timestamp": ts, "sign": sign(self.secret, ts)})
        if self.dry_run:
            return True, json.dumps(payload, ensure_ascii=False)
        last = ""
        for i in range(retries):
            try:
                r = requests.post(self.webhook, json=payload, timeout=self.timeout)
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                code = body.get("code", body.get("StatusCode", 0))
                if r.status_code == 200 and code in (0, None):
                    return True, "ok"
                last = "http=%s body=%s" % (r.status_code, json.dumps(body, ensure_ascii=False)[:300])
            except Exception as e:                     # 网络抖动 / 飞书 5xx
                last = repr(e)
            time.sleep(2 ** i)                          # 1s、2s、4s 退避
        return False, last
