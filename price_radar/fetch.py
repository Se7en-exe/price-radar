# -*- coding: utf-8 -*-
"""抓取层：给定 URL，取价格与库存状态。

三种取价方式，按可靠性排序自动降级：
  1) CSS 选择器（页面结构稳定时最划算）
  2) JSON-LD / meta itemprop（电商站常见，抗改版）
  3) 正则兜底（整页找 ¥/￥/$ 后面的数字）
纯静态抓不到时再开 Playwright 渲染（可选，需 playwright install chromium）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PRICE_RE = re.compile(r"(?:[¥￥$]|RMB|CNY)?\s*(\d[\d,]*(?:\.\d{1,2})?)")
OOS_WORDS = ("无货", "售罄", "缺货", "下架", "sold out", "out of stock", "暂时缺货")


def to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", "").strip())
    except Exception:
        return None


def load_html(target: str, timeout: int = 15) -> str:
    """target 可以是 http(s) URL，也可以是本地路径（方便离线演示与测试）。"""
    if target.startswith(("http://", "https://")):
        r = requests.get(target, headers={"User-Agent": UA,
                                          "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=timeout)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or r.encoding
        return r.text
    return Path(target).read_text(encoding="utf-8", errors="replace")


def _from_jsonld(soup: BeautifulSoup) -> float | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if k in ("price", "lowPrice", "highPrice") and not isinstance(v, (dict, list)):
                        got = to_float(str(v))
                        if got:
                            return got
                    else:
                        stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)
    return None


def extract_price(html: str, selector: str = "") -> tuple[float | None, str]:
    """返回 (价格, 取价方式)，取价方式用于排查。"""
    soup = BeautifulSoup(html, "lxml")
    if selector:
        node = soup.select_one(selector)
        if node is not None:
            m = PRICE_RE.search(node.get_text(" ", strip=True))
            if m:
                return to_float(m.group(1)), "css:" + selector
    for meta in soup.find_all("meta"):
        if meta.get("itemprop") == "price" and meta.get("content"):
            got = to_float(meta["content"])
            if got:
                return got, "meta[itemprop=price]"
    got = _from_jsonld(soup)
    if got:
        return got, "json-ld"
    text = soup.get_text(" ", strip=True)
    m = re.search(r"[¥￥]\s*(\d[\d,]*(?:\.\d{1,2})?)", text) or re.search(r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)", text)
    if m:
        return to_float(m.group(1)), "regex"
    return None, "miss"


def extract_stock(html: str) -> bool:
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True).lower()
    return not any(w in text for w in OOS_WORDS)


def fetch_price(url: str, selector: str = "", use_browser: bool = False) -> tuple[float | None, bool, str]:
    """返回 (价格, 是否有货, 取价方式)。"""
    html = load_html(url)
    price, how = extract_price(html, selector)
    stock = extract_stock(html)
    if price is None and use_browser:
        html = render_with_browser(url)
        price, how = extract_price(html, selector)
        stock = extract_stock(html)
        how += "+browser"
    return price, stock, how


def render_with_browser(url: str, wait_ms: int = 2500) -> str:
    """可选：真机渲染。需要先 python -m playwright install chromium。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(user_agent=UA)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(wait_ms)
        html = page.content()
        b.close()
        return html
