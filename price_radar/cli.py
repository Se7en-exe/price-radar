# -*- coding: utf-8 -*-
"""命令行入口。

  python -m price_radar init                    建库
  python -m price_radar add --name 竞品A --url <url> --selector .price --our-price 199
  python -m price_radar crawl [--webhook ...]   抓全部 -> 存快照 -> 判 -> 推
  python -m price_radar run                     按 config.json 跑一轮（推荐）
  python -m price_radar watch --interval 7200   常驻，每 2 小时一轮（推荐）
  python -m price_radar demo                    离线演示全链路（不联网）
  python -m price_radar report                  看最近变化
  python -m price_radar config                  打印生效中的配置
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import config as cfgmod
from . import rules, store
from .notify import Feishu
from .runner import crawl_all, run_forever, run_once, setup_logging


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


def cmd_crawl(args) -> int:
    conn = store.open_db()
    notifier = Feishu(args.webhook or "", args.secret or "", args.dry_run)
    crawl_all(conn, _cfg(args), notifier, args.browser)
    conn.close()
    return 0


def cmd_run(args) -> int:
    """按 config.json 跑一轮。没配 webhook 自动干跑。"""
    raw = cfgmod.load(args.config)
    cfg = cfgmod.flatten(raw)
    conn = store.connect(cfg["db"])
    added = cfgmod.sync_products(conn, raw)
    conn.close()
    if added:
        print("从配置新增 %d 个商品" % added)
    run_once(cfg, db=cfg["db"], dry_run=args.dry_run or cfg["dry_run"], use_browser=args.browser)
    return 0


def cmd_watch(args) -> int:
    raw = cfgmod.load(args.config)
    cfg = cfgmod.flatten(raw)
    conn = store.connect(cfg["db"])
    added = cfgmod.sync_products(conn, raw)
    conn.close()
    if added:
        print("从配置新增 %d 个商品" % added)
    interval = args.interval or cfg["interval_seconds"]
    try:
        run_forever(cfg, interval=interval, db=cfg["db"],
                    dry_run=args.dry_run or cfg["dry_run"], use_browser=args.browser)
    except KeyboardInterrupt:
        print("已停止")
    return 0


def cmd_config(args) -> int:
    raw = cfgmod.load(args.config)
    flat = cfgmod.flatten(raw)
    hook = flat.pop("webhook", "") or ""
    flat.pop("secret", None)
    flat["webhook"] = (hook[:42] + "…") if hook else "（未配置，将干跑）"
    flat["products"] = [p.get("name") for p in cfgmod.products_of(raw)]
    print(json.dumps(flat, ensure_ascii=False, indent=2))
    return 0


def cmd_demo(args) -> int:
    """离线演示：造 3 天历史 + 今天降价 + 断货，验证 抓→判→推 全链路，不联网。"""
    db = "data/demo.sqlite"
    if os.path.exists(db):
        os.remove(db)
    os.environ["PRICE_DB"] = db
    store.DB = db
    conn = store.connect(db)
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
            print("%-16s %-10s %-10s %-8s -" % (p.name, "-", "-", "-"))
            continue
        cur = h[0]
        prev = h[1] if len(h) > 1 else None
        delta = ""
        if prev and prev.price and cur.price:
            d = (cur.price - prev.price) / prev.price * 100
            delta = ("%+.1f%%" % d) if abs(d) > 1e-9 else "0.0%"
        print("%-16s %-10s %-10s %-8s %s" % (
            p.name,
            ("￥%s" % prev.price) if prev and prev.price else "-",
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

    for name, fn in (("run", cmd_run), ("watch", cmd_watch)):
        p = sub.add_parser(name)
        p.add_argument("--config", default="", help="配置文件路径，默认 config.json")
        p.add_argument("--dry-run", action="store_true", default=False)
        p.add_argument("--browser", action="store_true")
        if name == "watch":
            p.add_argument("--interval", type=int, default=0, help="秒；默认取配置里的 interval_seconds")
        p.set_defaults(func=fn)

    p = sub.add_parser("config")
    p.add_argument("--config", default="")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("report")
    p.set_defaults(func=cmd_report)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())