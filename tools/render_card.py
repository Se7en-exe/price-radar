# -*- coding: utf-8 -*-
"""把 out/feishu_payload.json 渲染成一张近似飞书卡片的 HTML，用于 README 预览图。

用法: python tools/render_card.py && chrome --headless --screenshot docs/card_preview.png docs/card_preview.html
"""
from __future__ import annotations

import html
import json
import os

SRC = os.path.join("out", "feishu_payload.json")
OUT = os.path.join("docs", "card_preview.html")

COLORS = {"red": "#d83931", "orange": "#f5a623", "blue": "#3370ff", "green": "#34c724"}


def md_to_html(s: str) -> str:
    s = html.escape(s).replace("\n", "<br>")
    while "**" in s:                     # 极简 **粗体**
        s = s.replace("**", "<b>", 1).replace("**", "</b>", 1)
    return s


def main() -> None:
    data = json.load(open(SRC, encoding="utf-8"))
    card = data.get("card", data)        # crawl 落盘的是 card 本身；干跑落盘的是完整 payload
    color = COLORS.get(card.get("header", {}).get("template", "blue"), "#3370ff")
    title = html.escape(card.get("header", {}).get("title", {}).get("content", ""))
    body = []
    for el in card.get("elements", []):
        if el.get("tag") == "div":
            body.append('<div class="sec">%s</div>' % md_to_html(el["text"]["content"]))
        elif el.get("tag") == "hr":
            body.append('<hr>')
        elif el.get("tag") == "note":
            txt = " ".join(e.get("content", "") for e in el.get("elements", []))
            body.append('<div class="note">%s</div>' % html.escape(txt))

    page = """<!doctype html><html><head><meta charset="utf-8">
<style>
  body { margin:0; background:#f2f3f5; font-family:"Segoe UI","Microsoft YaHei",sans-serif; padding:28px; }
  .card { width:640px; background:#fff; border-radius:12px; box-shadow:0 4px 18px rgba(0,0,0,.08); overflow:hidden; }
  .hd { color:#fff; padding:14px 18px; font-size:17px; font-weight:600; }
  .bd { padding:16px 18px 6px; }
  .sec { font-size:14px; line-height:1.75; color:#1f2329; margin-bottom:12px; }
  hr { border:none; border-top:1px solid #e5e6eb; margin:6px 0 10px; }
  .note { font-size:12px; color:#8f959e; padding-bottom:12px; }
</style></head><body>
<div class="card"><div class="hd" style="background:%s">%s</div><div class="bd">%s</div></div>
</body></html>""" % (color, title, "\n".join(body))

    os.makedirs("docs", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("written", OUT)


if __name__ == "__main__":
    main()
