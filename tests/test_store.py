# -*- coding: utf-8 -*-
import time

from price_radar import store


def make(tmp_path):
    return store.connect(str(tmp_path / "t.sqlite"))


def test_last_snapshot_breaks_tie_by_id(tmp_path):
    conn = make(tmp_path)
    pid = store.add_product(conn, "A", "u")
    now = int(time.time())
    for price, how in ((100.0, "old"), (90.0, "new")):
        conn.execute("INSERT INTO snapshot(product_id,price,stock,how,ts) VALUES(?,?,?,?,?)",
                     (pid, price, 1, how, now))     # 同一秒插入两条
    conn.commit()
    assert store.last_snapshot(conn, pid).price == 90.0     # 取 id 更大的那条


def test_alert_dedupe_window(tmp_path):
    conn = make(tmp_path)
    pid = store.add_product(conn, "A", "u")
    store.add_alert(conn, pid, "drop", "x")
    assert store.has_recent_alert(conn, pid, "drop", 24) is True
    assert store.has_recent_alert(conn, pid, "rise", 24) is False
    assert store.has_recent_alert(conn, pid, "drop", 0) is False


def test_mark_sent(tmp_path):
    conn = make(tmp_path)
    pid = store.add_product(conn, "A", "u")
    aid = store.add_alert(conn, pid, "drop", "x")
    store.mark_sent(conn, [aid])
    sent = conn.execute("SELECT sent FROM alert WHERE id=?", (aid,)).fetchone()[0]
    assert sent == 1
