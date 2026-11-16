# -*- coding: utf-8 -*-
"""给真飞书发一张测试卡片，确认 Webhook 通不通。

用法：
  python tools/send_test.py --webhook "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
  python tools/send_test.py --webhook ... --secret "签名校验的密钥"
  python tools/send_test.py --webhook ... --text "纯文本也支持"

成功会打印 "OK"，失败会打印飞书返回的错误码（常见 19021 = 签名校验失败，19001 = 参数错）。
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

sys.path.insert(0, ".")
from price_radar.notify import Feishu, build_card, sign  # noqa: E402
from price_radar.rules import Alert  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook", required=True)
    ap.add_argument("--secret", default="")
    ap.add_argument("--text", default="", help="给了就发纯文本，不给就发卡片")
    args = ap.parse_args()

    if args.text:
        payload = {"msg_type": "text", "content": {"text": args.text}}
        if args.secret:
            import time
            ts = str(int(time.time()))
            payload.update({"timestamp": ts, "sign": sign(args.secret, ts)})
        r = requests.post(args.webhook, json=payload, timeout=10)
        print(r.status_code, r.text[:300])
        return 0 if r.json().get("code") == 0 else 1

    alerts = [Alert("drop", "测试：竞品A 降价 10.1%（￥199.0 → ￥179.0）",
                    ["这条来自 price-radar 的连通性测试", "看到它就说明抓取/判定/推送链路已经通了"], "critical")]
    card = build_card(alerts, "price-radar 连通性测试")
    ok, info = Feishu(args.webhook, args.secret).send(card)
    print("OK" if ok else "FAIL: " + info)
    print(json.dumps(card, ensure_ascii=False)[:200])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
