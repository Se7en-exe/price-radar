# -*- coding: utf-8 -*-
"""存储层：SQLite 单文件。三张表——商品、快照、告警。"""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass

DB = os.environ.get("PRICE_DB", os.path.join("data", "price.sqlite"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS product (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  selector TEXT DEFAULT '',
  our_price REAL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  price REAL,
  stock INTEGER NOT NULL DEFAULT 1,
  how TEXT DEFAULT '',
  ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_pid_ts ON snapshot(product_id, ts DESC);
CREATE TABLE IF NOT EXISTS alert (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  detail TEXT NOT NULL,
  sent INTEGER NOT NULL DEFAULT 0,
  ts INTEGER NOT NULL
);
"""


@dataclass
class Snapshot:
    price: float | None
    stock: bool
    ts: int
    how: str = ""


@dataclass
class Product:
    id: int
    name: str
    url: str
    selector: str
    our_price: float | None


def connect(db: str = "") -> sqlite3.Connection:
    path = db or DB
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_product(conn, name: str, url: str, selector: str = "", our_price: float | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO product(name,url,selector,our_price,created_at) VALUES(?,?,?,?,?)",
        (name, url, selector, our_price, int(time.time())))
    conn.commit()
    return int(cur.lastrowid)


def list_products(conn) -> list[Product]:
    rows = conn.execute("SELECT * FROM product ORDER BY id").fetchall()
    return [Product(r["id"], r["name"], r["url"], r["selector"] or "", r["our_price"]) for r in rows]


def add_snapshot(conn, product_id: int, price: float | None, stock: bool, how: str = "") -> None:
    conn.execute("INSERT INTO snapshot(product_id,price,stock,how,ts) VALUES(?,?,?,?,?)",
                 (product_id, price, 1 if stock else 0, how, int(time.time())))
    conn.commit()


def last_snapshot(conn, product_id: int) -> Snapshot | None:
    r = conn.execute("SELECT * FROM snapshot WHERE product_id=? ORDER BY ts DESC, id DESC LIMIT 1",
                     (product_id,)).fetchone()
    return Snapshot(r["price"], bool(r["stock"]), r["ts"], r["how"]) if r else None


def history(conn, product_id: int, limit: int = 10) -> list[Snapshot]:
    rows = conn.execute("SELECT * FROM snapshot WHERE product_id=? ORDER BY ts DESC, id DESC LIMIT ?",
                        (product_id, limit)).fetchall()
    return [Snapshot(r["price"], bool(r["stock"]), r["ts"], r["how"]) for r in rows]


def add_alert(conn, product_id: int, kind: str, detail: str) -> int:
    cur = conn.execute("INSERT INTO alert(product_id,kind,detail,ts) VALUES(?,?,?,?)",
                       (product_id, kind, detail, int(time.time())))
    conn.commit()
    return int(cur.lastrowid)


def has_recent_alert(conn, product_id: int, kind: str, hours: int = 24) -> bool:
    """同一商品同一类告警，N 小时内只发一次，避免每轮都吵。"""
    cutoff = int(time.time()) - hours * 3600
    row = conn.execute(
        "SELECT 1 FROM alert WHERE product_id=? AND kind=? AND ts>? LIMIT 1",
        (product_id, kind, cutoff)).fetchone()
    return row is not None


def mark_sent(conn, alert_ids: list[int]) -> None:
    conn.executemany("UPDATE alert SET sent=1 WHERE id=?", [(i,) for i in alert_ids])
    conn.commit()


def open_db(path: str = "") -> sqlite3.Connection:
    with closing(connect(path)) as probe:   # 确保 schema 建好
        probe.commit()
    return connect(path)
