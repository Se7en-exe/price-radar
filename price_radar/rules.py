# -*- coding: utf-8 -*-
"""判定层：拿「上次」和「这次」比，决定要不要吵醒人。"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CFG = {
    "drop_pct": 5.0,      # 跌幅超过这个数就告警
    "rise_pct": 5.0,      # 涨幅同理
    "undercut_pct": 8.0,  # 竞品价低于我方这么多 → 给调价建议
    "margin": 0.02,       # 建议价 = 竞品价 * (1 + margin)
    "sustained_n": 3,     # 连续 N 次下跌也算信号
}


@dataclass
class Alert:
    kind: str
    title: str
    lines: list[str] = field(default_factory=list)
    level: str = "info"     # info / warn / critical

    def text(self) -> str:
        return "\n".join(self.lines)


def _pct(a: float, b: float) -> float:
    return (a - b) / a * 100.0 if a else 0.0


def suggest_price(competitor: float, our_price: float | None, margin: float) -> float:
    target = competitor * (1 + margin)
    if our_price:
        target = min(target, our_price)
    return round(target, 2)


def evaluate(name: str, prev, cur, our_price: float | None, history: list, cfg: dict | None = None) -> list[Alert]:
    c = {**DEFAULT_CFG, **(cfg or {})}
    out: list[Alert] = []
    if cur is None or cur.price is None:
        return [Alert("miss", f"{name}：这次没抓到价格", ["检查选择器或页面改版"], "warn")]
    if prev is None or prev.price is None:
        return [Alert("first", f"{name}：首次采集 ￥{cur.price}", [], "info")]

    change = _pct(prev.price, cur.price)          # 正数=跌
    if change >= c["drop_pct"]:
        out.append(Alert("drop", f"{name}：降价 {change:.1f}%（￥{prev.price} → ￥{cur.price}）",
                         ["竞品价格下探，留意是否需要跟价"], "critical"))
    elif -change >= c["rise_pct"]:
        out.append(Alert("rise", f"{name}：涨价 {-change:.1f}%（￥{prev.price} → ￥{cur.price}）",
                         ["竞品上调，我方有提价空间"], "warn"))

    if prev.stock and not cur.stock:
        out.append(Alert("oos", f"{name}：竞品断货", ["可能是备货周期，2 小时内复查"], "critical"))
    elif not prev.stock and cur.stock:
        out.append(Alert("restock", f"{name}：竞品恢复有货", ["关注是否伴随降价冲量"], "info"))

    if our_price and cur.price and _pct(our_price, cur.price) >= c["undercut_pct"]:
        sug = suggest_price(cur.price, our_price, c["margin"])
        out.append(Alert("undercut", f"{name}：竞品比我们低 {_pct(our_price, cur.price):.1f}%",
                         [f"我方 ￥{our_price} / 竞品 ￥{cur.price}",
                          f"建议调价到 ￥{sug}（竞品价 +{c['margin']*100:.0f}%，且不高于现价）"], "critical"))

    n = int(c["sustained_n"])
    prices = [s.price for s in history[:n] if s.price]
    if len(prices) >= n and all(prices[i] > prices[i + 1] for i in range(len(prices) - 1)):
        total = _pct(prices[0], prices[-1])
        out.append(Alert("sustained", f"{name}：连续 {n} 次下跌，累计 {total:.1f}%",
                         ["这是趋势不是波动，按调价流程走"], "critical"))
    return out
