# -*- coding: utf-8 -*-
from price_radar.fetch import extract_price, extract_stock


def test_css_selector_wins():
    html = '<div class="price">￥199.00</div><div class="other">￥888</div>'
    assert extract_price(html, ".price") == (199.0, "css:.price")


def test_meta_itemprop():
    html = '<meta itemprop="price" content="1,288.50">'
    assert extract_price(html) == (1288.5, "meta[itemprop=price]")


def test_json_ld_offers():
    html = ('<script type="application/ld+json">'
            '{"@type":"Product","offers":{"@type":"Offer","price":"179.00"}}'
            '</script>')
    price, how = extract_price(html)
    assert price == 179.0 and how == "json-ld"


def test_regex_fallback():
    assert extract_price("<p>限时特价 ¥51.77 包邮</p>") == (51.77, "regex")


def test_miss_returns_none():
    assert extract_price("<p>暂无报价</p>") == (None, "miss")


def test_stock_detection():
    assert extract_stock("<div>有货，48 小时内发出</div>") is True
    assert extract_stock("<div>已售罄</div>") is False
    assert extract_stock("<div>Sold Out</div>") is False
