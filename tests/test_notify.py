# -*- coding: utf-8 -*-
from price_radar import notify
from price_radar.rules import Alert


def test_sign_reference_vector():
    # 飞书签名：HMAC-SHA256(key="<ts>\n<secret>", msg="") 再 base64
    assert notify.sign("secret123", "1600000000") == "BdVlgDTCZ+awBHKqIx5uB+4K3io9ypcHaxVAUreNPUE="


def test_card_color_by_level():
    red = notify.build_card([Alert("drop", "t", [], "critical")])
    orange = notify.build_card([Alert("rise", "t", [], "warn")])
    blue = notify.build_card([Alert("first", "t", [], "info")])
    assert red["header"]["template"] == "red"
    assert orange["header"]["template"] == "orange"
    assert blue["header"]["template"] == "blue"


def test_card_carries_lines():
    card = notify.build_card([Alert("drop", "降价了", ["看这里"], "critical")])
    body = card["elements"][0]["text"]["content"]
    assert "降价了" in body and "看这里" in body


def test_dry_run_never_posts(monkeypatch):
    hits = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: hits.append(1))
    ok, _ = notify.Feishu("", "").send(notify.build_card([Alert("drop", "t")]))
    assert ok is True and hits == []


def test_real_send_success(monkeypatch):
    class R:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": 0}

    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: R())
    ok, info = notify.Feishu("https://example.com/hook").send(notify.build_card([Alert("drop", "t")]))
    assert ok is True and info == "ok"
