# -*- coding: utf-8 -*-
"""执行层：一轮抓取 = 抓 → 存 → 判 → 推，以及常驻轮询循环。

和 cli 分开是为了能被定时任务、Docker、测试直接调用，不用经过 argparse。
"""
from __future__ import annotations

import json
import logging
import os
import random
import time

from . import fetch, rules, store
from .notify import Feishu, build_card

log = logging.getLogger("price_radar")


def setup_logging(logfile: str = os.path.join("out", "price_radar.log"), level: int = logging.INFO) -> None:
    """同时写文件和终端；重复调用不会叠加 handler。"""
    root = logging.getLogger("price_radar")
    if root.handlers:
        return
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    if logfile:
        os.makedirs(os.path.dirname(logfile) or ".", exist_ok=True)
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)


def crawl_all(conn, cfg: dict, notifier: Feishu, use_browser: bool = False,
              outdir: str = "out", logger=None) -> list:
    """跑一轮：每个商品独立 try，一个坏掉不影响其它；末尾合并成一张卡片推一次。"""
    lg = logger or log
    alerts, ids = [], []
    for p in store.list_products(conn):
        try:
            prev = store.last_snapshot(conn, p.id)
            price, stock, how = fetch.fetch_price(p.url, p.selector, use_browser)
            store.add_snapshot(conn, p.id, price, stock, how)
            cur = store.Snapshot(price, stock, int(time.time()), how)
            hist = store.history(conn, p.id, 5)
            got = rules.evaluate(p.name, prev, cur, p.our_price, hist, cfg)
            # 同类告警 24h 内只发一次（抓取失败除外，那个要每轮提醒）
            got = [a for a in got if a.kind == "miss"
                   or not store.has_recent_alert(conn, p.id, a.kind, cfg.get("dedupe_hours", 24))]
            for a in got:
                ids.append(store.add_alert(conn, p.id, a.kind, (a.title + " " + a.text()).strip()))
            alerts.extend(got)
            lg.info("%s price=%s stock=%s via=%s", p.name, price, stock, how)
            print("  %-14s ￥%-9s 有货=%-5s 通过=%s" % (p.name, price, stock, how))
        except Exception as exc:                     # noqa: BLE001 - 单商品失败不该中断整轮
            lg.exception("商品 %s 抓取失败", p.name)
            print("  %-14s 抓取异常: %s" % (p.name, exc))

    if not alerts:
        print("无告警")
        return []

    card = build_card(alerts)
    ok, info = notifier.send(card)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "feishu_payload.json"), "w", encoding="utf-8") as fh:
        json.dump(card, fh, ensure_ascii=False, indent=2)
    print("推送:", "OK" if ok else "FAIL", "" if ok else info)
    if ok and not notifier.dry_run:
        store.mark_sent(conn, ids)
    return alerts


def run_once(cfg: dict, db: str = "", dry_run: bool = False, use_browser: bool = False) -> list:
    conn = store.connect(db) if db else store.open_db()
    notifier = Feishu(cfg.get("webhook", ""), cfg.get("secret", ""), dry_run or bool(cfg.get("dry_run")))
    try:
        return crawl_all(conn, cfg.get("rules", {}) | {"dedupe_hours": cfg.get("dedupe_hours", 24)},
                         notifier, use_browser, cfg.get("outdir", "out"))
    finally:
        conn.close()


def run_forever(cfg: dict, interval: int = 7200, db: str = "", dry_run: bool = False,
                use_browser: bool = False, jitter: float = 0.1) -> None:
    """常驻：每 interval 秒跑一轮，带 ±jitter 抖动，Ctrl-C 干净退出。"""
    setup_logging()
    log.info("启动常驻轮询 interval=%ss jitter=±%d%%", interval, int(jitter * 100))
    while True:
        started = time.time()
        try:
            run_once(cfg, db=db, dry_run=dry_run, use_browser=use_browser)
        except KeyboardInterrupt:
            log.info("收到中断，退出")
            raise
        except Exception:                             # noqa: BLE001
            log.exception("本轮执行失败，%ss 后重试", 60)
            time.sleep(60)
            continue
        wait = max(30.0, interval * (1 + random.uniform(-jitter, jitter)) - (time.time() - started))
        log.info("本轮耗时 %.1fs，%.0fs 后进入下一轮", time.time() - started, wait)
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            log.info("收到中断，退出")
            raise
