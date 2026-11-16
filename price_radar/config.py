# -*- coding: utf-8 -*-
"""配置层：一个 config.json 描述「监控哪些商品 + 阈值 + 推给谁」。

优先级：命令行参数 > 环境变量 > config.json > 内置默认值。
Webhook 不放配置文件也行，用环境变量 FEISHU_WEBHOOK（推荐，避免误提交到 git）。
"""
from __future__ import annotations

import json
import os

from . import rules, store

DEFAULT_PATH = os.environ.get("PRICE_CONFIG", "config.json")

SAMPLE = {
    "feishu": {"webhook": "", "secret": "", "dry_run": False},
    "rules": dict(rules.DEFAULT_CFG, dedupe_hours=24),
    "interval_seconds": 7200,
    "db": "data/price.sqlite",
    "products": [
        {"name": "竞品A·蓝牙耳机", "url": "fixtures/competitor_a.html",
         "selector": ".price", "our_price": 199, "enabled": True},
    ],
}


def load(path: str = "") -> dict:
    """读配置文件；文件不存在时返回内置样例（不写盘）。"""
    p = path or DEFAULT_PATH
    cfg = json.loads(json.dumps(SAMPLE))          # 深拷贝
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            user = json.load(fh)
        for k, v in user.items():
            if k in ("feishu", "rules") and isinstance(v, dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    env_hook = os.environ.get("FEISHU_WEBHOOK", "")
    if env_hook:
        cfg["feishu"]["webhook"] = env_hook
    env_secret = os.environ.get("FEISHU_SECRET", "")
    if env_secret:
        cfg["feishu"]["secret"] = env_secret
    return cfg


def products_of(cfg: dict) -> list[dict]:
    return [p for p in cfg.get("products", []) if p.get("enabled", True)]


def sync_products(conn, cfg: dict) -> int:
    """把配置里的商品写进库（按名字去重），返回新增数量。"""
    exists = {p.name for p in store.list_products(conn)}
    added = 0
    for p in products_of(cfg):
        if p["name"] in exists:
            continue
        store.add_product(conn, p["name"], p["url"], p.get("selector", ""), p.get("our_price"))
        added += 1
    return added


def flatten(cfg: dict) -> dict:
    """给 runner 用的扁平结构。"""
    return {
        "webhook": cfg.get("feishu", {}).get("webhook", ""),
        "secret": cfg.get("feishu", {}).get("secret", ""),
        "dry_run": bool(cfg.get("feishu", {}).get("dry_run")),
        "rules": cfg.get("rules", {}),
        "dedupe_hours": cfg.get("rules", {}).get("dedupe_hours", 24),
        "interval_seconds": int(cfg.get("interval_seconds", 7200)),
        "db": cfg.get("db", "data/price.sqlite"),
        "outdir": cfg.get("outdir", "out"),
    }
