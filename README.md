# price-radar · 竞品价格监控 → 飞书告警

三步链路，一条命令跑通：**抓（requests / Playwright）→ 判（阈值 / 缺货 / 连跌 / 调价建议）→ 推（飞书机器人卡片）**。

对应岗位职责里那三条：**竞品价格监控**、**广告/商品调价逻辑**、**把异常推进业务群（飞书）**。

    [定时 2h] → [抓页面 CSS/meta/JSON-LD] → [SQLite 快照]

        判定：跌幅 / 涨幅 / 缺货 / 连跌 / 调价建议

    → [飞书机器人卡片] → 业务群

## 一分钟跑通（离线，不碰外网）

    pip install -r requirements.txt
    python tools/mock_feishu.py          # 另开一个窗口：本地假飞书
    python -m price_radar demo --webhook http://127.0.0.1:8899/hook

输出：

    竞品A·蓝牙耳机   ￥179.0   有货=True  通过=css:.price
    竞品B·机械键盘   ￥1288.0  有货=False 通过=css:.price
    推送: OK
    判定结果:
      [drop]      竞品A：降价 10.1%（￥199.0 → ￥179.0）
      [undercut]  竞品A：竞品比我们低 10.1%
                  我方 ￥199.0 / 竞品 ￥179.0
                  建议调价到 ￥182.58（竞品价 +2%，且不高于现价）
      [oos]       竞品B：竞品断货

卡片 JSON 落在 `out/feishu_payload.json`，可直接贴进飞书调试台预览。

## 接真站：三步

1）加监控（`--our-price` 给了才会算调价建议）

    python -m price_radar add --name "竞品X" --url "https://example.com/item/123" --selector ".price" --our-price 199
    python -m price_radar crawl --webhook "$FEISHU_WEBHOOK" --secret "$FEISHU_SECRET"

2）selector 抓不到就让它自己降级：脚本会依次尝试 **CSS 选择器 → meta itemprop → JSON-LD → 整页正则**，抓取结果里的 `通过=` 会告诉你这次走的是哪条路。

3）还是拿不到（页面是前端渲染的）就开渲染：

    python -m pip install playwright && python -m playwright install chromium
    python -m price_radar crawl --browser --webhook "$FEISHU_WEBHOOK"

## 判定规则（都能在命令行覆盖）

| 规则 | 默认值 | 触发条件 |
|---|---|---|
| 降价 | -5% | 比上次低 5% 以上 |
| 涨价 | +5% | 比上次高 5% 以上 |
| 断货 / 到货 | - | 有货→无货、无货→有货 |
| 连跌 | 3 次 | 连续 3 次采样逐次下降 |
| 调价建议 | 8% / +2% | 竞品低于我方 8%，建议价 = 竞品价×1.02 且不高于现价 |

    python -m price_radar crawl --drop-pct 3 --undercut-pct 5 --margin 0.05

## 定时跑

Windows 计划任务 / cron 每 2 小时一次即可：

    schtasks /create /tn "price-radar" /tr "python -m price_radar crawl --webhook %FEISHU_WEBHOOK%" /sc hourly /mo 2

或直接上 n8n（见下）。

## 用 n8n 拖出来（更贴 JD 的「AI 工作流 + 业务系统」）

    docker compose up -d          # n8n 在 http://127.0.0.1:5678
    # 导入 n8n/price-radar.workflow.json，把飞书 Webhook 换成你自己的

工作流就是四个节点：**定时触发 → HTTP 抓页面 → Code 取价 → IF 跌幅>5% → HTTP 推飞书**。
n8n 的价值不在功能，在于**别人能打开界面看一眼就知道你怎么串的**——面试时这张图比代码好讲。

## 代码结构

    price_radar/fetch.py    抓取：CSS / meta / JSON-LD / 正则四级降级 + 可选 Playwright
    price_radar/rules.py    判定：阈值、连跌、缺货、调价建议
    price_radar/store.py    SQLite：product / snapshot / alert 三张表
    price_radar/notify.py   飞书：签名（HMAC-SHA256 + base64）、卡片、指数退避重试
    price_radar/cli.py      init / add / crawl / demo / report
    tools/mock_feishu.py    本地假 Webhook，用来验证「推」真的发出去了
    fixtures/               两个离线页面（含 JSON-LD、千分位、缺货文案）

## 几个工程细节（面试可以讲）

- **抓不到不能静默**：`extract_price` 返回 `(None, "miss")`，会单独发一条 warn 卡片，避免「没告警＝没降价」的错觉。
- **重试有界**：飞书 5xx 或网络抖动退避 1s/2s/4s，三次后退化为失败并保留在 `alert` 表里（`sent=0`），下轮可补发。
- **去重靠存储**：告警落库后再发，发成功才 `sent=1`，所以进程被 kill 也不会丢告警。
- **抓取限频**：默认单进程串行 + 每个站点间隔，别把对端打挂；只抓公开商品页，不登录、不绕验证码。

## 边界（别吹过头）

- 需要登录、验证码、强反爬的站点，这套默认方案抓不到；要么加 Playwright + 代理，要么走官方 API。
- 没有分布式、没有任务队列；单机跑几十个 SKU 够用，上千 SKU 要上调度（Celery / n8n 并发）。
- 「调价建议」是规则，不是模型：它给的是参考价，最终要不要跟，是人决定的。
