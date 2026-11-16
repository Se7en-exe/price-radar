# -*- coding: utf-8 -*-
"""命令行入口：

  python -m price_radar init
  python -m price_radar add --name "竞品A" --url ./fixtures/competitor_a.html --selector ".price" --our-price 199
  python -m price_radar crawl            # 抓全部 -> 存快照 -> 判 -> 推
  python -m price_radar demo             # 用 fixtures 造两天数据跑通全链路
  python -m price_radar report           # 看最近变化
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import fetch, rules, store
from .notify import Feishu, build_card


def _cfg(args) -> dict:
    c = dict(rules.DEFAULT_CFG)
    for k in ("drop_pct", "rise_pct", "undercut_pct", "margin", "sustained_n"):
        v = getattr(args, k, None)
        if v is not None:
            c[k] = v
    return c


def cmd_init(args) -> int:
    conn = store.open_db()
    print("数据库就绪:", store.DB)
    conn.close()
    return 0


def cmd_add(args) -> int:
    conn = store.open_db()
    pid = store.add_product(conn, args.name, args.url, args.selector or "", args.our_price)
    print("已加入监控 #%d %s" % (pid, args.name))
    conn.close()
    return 0


def crawl_all(conn, cfg: dict, notifier: Feishu, use_browser: bool = False, outdir: str = "out") -> list:
    alerts = []
    ids = []
    for p in store.list_products(conn):
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
            aid = store.add_alert(conn, p.id, a.kind, a.title + " " + a.text())
            ids.append(aid)
        alerts.extend(got)
        print("  %-14s ￥%-9s 有货=%-5s 通过=%s" % (p.name, price, stock, how))
    if alerts:
        card = build_card(alerts)
        ok, info = notifier.send(card)
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "feishu_payload.json"), "w", encoding="utf-8") as fh:
            json.dump(card, fh, ensure_ascii=False, indent=2)
        print("推送:", "OK" if ok else "FAIL", "" if ok else info)
        if ok and not notifier.dry_run:
            store.mark_sent(conn, ids)
    else:
        print("无告警")
    return alerts


def cmd_crawl(args) -> int:
    conn = store.open_db()
    notifier = Feishu(args.webhook or "", args.secret or "", args.dry_run)
    crawl_all(conn, _cfg(args), notifier, args.browser)
    conn.close()
    return 0


def cmd_demo(args) -> int:
    """离线演示：造 3 天历史 + 今天降价 10% + 断货，验证 抓→判→推。"""
    db = "data/demo.sqlite"
    if os.path.exists(db):
        os.remove(db)
    os.environ["PRICE_DB"] = db
    store.DB = db
    conn = store.open_db(db)
    a = store.add_product(conn, "竞品A·蓝牙耳机", "fixtures/competitor_a.html", ".price", 199.0)
    b = store.add_product(conn, "竞品B·机械键盘", "fixtures/competitor_b.html", ".price", 999.0)
    now = int(time.time())
    for i, price in enumerate((219.0, 209.0, 199.0)):    # 三天前 -> 昨天
        conn.execute("INSERT INTO snapshot(product_id,price,stock,how,ts) VALUES(?,?,?,?,?)",
                     (a, price, 1, "seed", now - (3 - i) * 86400))
    conn.execute("INSERT INTO snapshot(product_id,price,stock,how,ts) VALUES(?,?,?,?,?)",
                 (b, 1288.0, 1, "seed", now - 86400))
    conn.commit()
    print("演示库:", db, " 商品:", 2)
    notifier = Feishu(args.webhook or "", args.secret or "", args.dry_run)
    got = crawl_all(conn, _cfg(args), notifier, False, "out")
    print("\n判定结果:")
    for x in got:
        print("  [%s] %s" % (x.kind, x.title))
        for line in x.lines:
            print("        " + line)
    conn.close()
    return 0


def cmd_report(args) -> int:
    conn = store.open_db()
    print("%-16s %-10s %-10s %-8s %s" % ("商品", "上次", "最新", "变化", "时间"))
    for p in store.list_products(conn):
        h = store.history(conn, p.id, 2)
        if not h:
            print("%-16s %-10s %-10s %-8s -" % (p.name, "-", "-", "-")); continue
        cur = h[0]
        prev = h[1] if len(h) > 1 else None
        delta = ""
        if prev and prev.price and cur.price:
            d = (cur.price - prev.price) / prev.price * 100
            delta = ("%+.1f%%" % d) if abs(d) > 1e-9 else "0%"    # + 是涨，- 是跌
        print("%-16s %-10s %-10s %-8s %s" % (
            p.name, ("￥%s" % prev.price) if prev else "-",
            ("￥%s" % cur.price) if cur.price else "抓取失败", delta,
            time.strftime("%m-%d %H:%M", time.localtime(cur.ts))))
    conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="price_radar", description="竞品价格监控 -> 飞书告警")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    p = sub.add_parser("add")
    p.add_argument("--name", required=True)
    p.add_argument("--url", required=True, help="http(s) 或本地 html 路径")
    p.add_argument("--selector", default="")
    p.add_argument("--our-price", type=float, default=None)
    p.set_defaults(func=cmd_add)

    for name, fn in (("crawl", cmd_crawl), ("demo", cmd_demo)):
        p = sub.add_parser(name)
        p.add_argument("--webhook", default="")
        p.add_argument("--secret", default="")
        p.add_argument("--dry-run", action="store_true", default=False,
                       help="只打印不发送（没给 webhook 时也会自动进入干跑）")
        p.add_argument("--drop-pct", type=float, default=None)
        p.add_argument("--rise-pct", type=float, default=None)
        p.add_argument("--undercut-pct", type=float, default=None)
        p.add_argument("--margin", type=float, default=None)
        if name == "crawl":
            p.add_argument("--browser", action="store_true", help="静态抓不到时用 Playwright 渲染")
        p.set_defaults(func=fn)

    p = sub.add_parser("report")
    p.set_defaults(func=cmd_report)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
