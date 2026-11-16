"""竞品价格监控 → 飞书告警。

链路：抓（requests/Playwright）→ 判（与上次比，跌幅阈值/缺货/连跌）→ 推（飞书机器人 Webhook）。
"""
__version__ = "0.1.0"
