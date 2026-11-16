# -*- coding: utf-8 -*-
from price_radar import rules
from price_radar.store import Snapshot


def snap(price, stock=True):
    return Snapshot(price, stock, 0, "test")


def kinds(alerts):
    return [a.kind for a in alerts]


def test_first_snapshot_does_not_alert_on_change():
    assert kinds(rules.evaluate("A", None, snap(100), None, [])) == ["first"]


def test_drop_threshold_boundary():
    assert kinds(rules.evaluate("A", snap(100), snap(90), None, [])) == ["drop"]
    assert kinds(rules.evaluate("A", snap(100), snap(96), None, [])) == []      # 4% 不够


def test_rise_alert():
    assert kinds(rules.evaluate("A", snap(100), snap(110), None, [])) == ["rise"]


def test_undercut_has_price_suggestion():
    got = rules.evaluate("A", snap(200), snap(150), 200, [])
    assert "undercut" in kinds(got)
    line = [ln for a in got if a.kind == "undercut" for ln in a.lines][-1]
    assert "153.0" in line          # min(150*1.02, 200) = 153.0


def test_oos_and_restock():
    assert "oos" in kinds(rules.evaluate("A", snap(100, True), snap(100, False), None, []))
    assert "restock" in kinds(rules.evaluate("A", snap(100, False), snap(100, True), None, []))


def test_miss_when_price_none():
    assert kinds(rules.evaluate("A", snap(100), Snapshot(None, True, 0, ""), None, [])) == ["miss"]


def test_sustained_downtrend():
    hist = [snap(90), snap(95), snap(100)]        # 最新在前，严格递减
    assert "sustained" in kinds(rules.evaluate("A", snap(95), snap(90), None, hist))