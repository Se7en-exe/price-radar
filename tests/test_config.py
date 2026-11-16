# -*- coding: utf-8 -*-
from price_radar import config, store


def test_defaults_when_file_missing(tmp_path):
    cfg = config.load(str(tmp_path / "nope.json"))
    assert cfg["interval_seconds"] == 7200
    assert cfg["rules"]["drop_pct"] == 5.0
    assert cfg["products"]


def test_env_webhook_overrides_file(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    p.write_text('{"feishu":{"webhook":"from-file"},"rules":{"drop_pct":3}}', encoding="utf-8")
    monkeypatch.setenv("FEISHU_WEBHOOK", "from-env")
    cfg = config.load(str(p))
    assert cfg["feishu"]["webhook"] == "from-env"
    assert cfg["rules"]["drop_pct"] == 3
    assert cfg["rules"]["undercut_pct"] == 8.0        # 其余默认值保留


def test_enabled_filter():
    cfg = {"products": [{"name": "a", "enabled": True}, {"name": "b", "enabled": False}]}
    assert [p["name"] for p in config.products_of(cfg)] == ["a"]


def test_sync_products_is_idempotent(tmp_path):
    conn = store.connect(str(tmp_path / "s.sqlite"))
    cfg = {"products": [{"name": "A", "url": "u", "selector": ".p", "our_price": 9}]}
    assert config.sync_products(conn, cfg) == 1
    assert config.sync_products(conn, cfg) == 0
    assert len(store.list_products(conn)) == 1
