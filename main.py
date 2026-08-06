#!/usr/bin/env python3
"""
每日科技日报自动生成脚本
- 搜索: Tavily (多轮并行)
- 格式化: DeepSeek Chat
- 发送: Gmail SMTP
"""

import os
import json
import smtplib
import time
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from tavily import TavilyClient
from openai import OpenAI

# ── 环境变量 ──────────────────────────────────────────────
TAVILY_KEY = os.environ["TAVILY_API_KEY"]
DEEPSEEK_KEY = os.environ["DEEPSEEK_API_KEY"]
GMAIL_ADDR = os.environ["GMAIL_ADDRESS"].strip()
RECIPIENT = os.environ.get("RECIPIENT_EMAIL", os.environ["GMAIL_ADDRESS"])
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"].strip()

DEEPSEEK_MODEL = "deepseek-chat"

# ── 日期计算 ──────────────────────────────────────────────

def get_date_range():
    """确定覆盖日期：昨天（每天运行，无需周一特殊处理）"""
    yesterday = date.today() - timedelta(days=1)
    return yesterday, yesterday

def fmt_date_range(start, end):
    """格式化日期用于搜索, e.g. 'August 5 2026'"""
    if start == end:
        return start.strftime("%B %-d %Y")
    return f"{start.strftime('%B %-d')} – {end.strftime('%B %-d')} {start.year}"

def weekday_cn(d):
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()]

def date_title_cn(d):
    return f"{d.year}年{d.month}月{d.day}日"

# ── 搜索 ──────────────────────────────────────────────────

ROUND1_QUERIES = [
    "AI artificial intelligence news OpenAI Google Anthropic {date}",
    "Sam Altman Elon Musk AI regulation policy {date}",
    "Nvidia TSMC chip semiconductor news {date}",
    "AI startup funding IPO investment {date}",
    "Trump AI executive order regulation policy {date}",
    "China AI technology policy news {date}",
    "AI model release product launch breakthrough {date}",
    "technology industry major news {date}",
]

def search_one(client, query, topic="general"):
    try:
        r = client.search(query, search_depth="advanced", topic=topic, max_results=10)
        return {"query": query, "results": r.get("results", [])}
    except Exception as e:
        print(f"  ✗ 搜索失败 [{query[:50]}...]: {e}")
        return {"query": query, "results": [], "error": str(e)}

def round1(client, start, end):
    """第一轮：8 个并行搜索"""
    ds = fmt_date_range(start, end)
    queries = [q.format(date=ds) for q in ROUND1_QUERIES]
    # 追加一条财经向搜索
    queries.append(f"AI semiconductor stock market funding IPO {ds}")
    print(f"  发起 {len(queries)} 个并行查询 ...")

    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(search_one, client, q, "finance" if "funding" in q.lower() or "stock" in q.lower() else "general"): q for q in queries}
        for fut in as_completed(futs):
            results.append(fut.result())
    return results

def round2(client, round1_results):
    """第二轮：为 Top 新闻搜索 YouTube 视频"""
    seen = set()
    queries = []
    for group in round1_results:
        for r in group.get("results", [])[:3]:
            t = r.get("title", "")
            if t and t not in seen:
                seen.add(t)
                # 取标题前 80 字作为搜索词
                short = t[:80] if len(t) > 80 else t
                queries.append(f"{short} YouTube")
                if len(queries) >= 12:
                    break
        if len(queries) >= 12:
            break

    print(f"  发起 {len(queries)} 个 YouTube 搜索 ...")
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(search_one, client, q): q for q in queries}
        for fut in as_completed(futs):
            results.append(fut.result())
    return results

# ── DeepSeek 格式化 ───────────────────────────────────────

def build_prompt(round1_data, round2_data, start, end):
    """构建发送给 DeepSeek 的系统提示词"""

    # 编译新闻素材
    news_items = []
    for group in round1_data:
        for r in group.get("results", []):
            news_items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            })

    yt_items = []
    for group in round2_data:
        for r in group.get("results", []):
            yt_items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            })

    # 截断防止过长
    news_json = json.dumps(news_items, ensure_ascii=False, indent=2)
    yt_json = json.dumps(yt_items, ensure_ascii=False, indent=2)
    if len(news_json) > 35000:
        news_json = news_json[:35000] + "\n...[truncated]"
    if len(yt_json) > 12000:
        yt_json = yt_json[:12000] + "\n...[truncated]"

    wd = weekday_cn(start)
    dt = date_title_cn(start)
    if start != end:
        dr = f"{start.year}年{start.month}月{start.day}日-{end.month}月{end.day}日"
    else:
        dr = f"{start.year}年{start.month}月{start.day}日"

    system = f"""你是一位资深科技新闻编辑，读者是关注AI、半导体、科技政策和资本市场的专业人士。

请基于下方提供的搜索素材，生成一份中文科技日报。

当前日期：{dt}（{wd}）
覆盖日期范围：{dr}

【强制格式】

# 🔥 科技日报 · {dt}（{wd}）

> **一句话摘要：** [1-2句话概括当天最重要的科技动态，涵盖2-3个关键事件]

---

## 🔥 头条

**1. 标题（12-25中文字符）**
[正文75-150字：5W1H + 关键数字 + 影响]

| 视频解读 | 来源 |
|---|---|
| [视频标题](完整YouTube链接) | 频道名 |

**2. 标题**
...

## 🗣️ 大人物声音
**3. 标题**
...

## 🚀 模型 & 产品
**4. 标题**
...

## 💰 资本 & 政策
**5. 标题**
...

## 🏭 硬件 & 制造
**6. 标题**
...

## 📊 快讯速览
**7. 标题**
...

---

> 📌 以上所有新闻均来自 **{dr}** 的最新报道。

【规则】
1. 共 10 条新闻（重大突发可增至 12 条），六大板块各至少 1 条，按 头条 → 大人物声音 → 模型产品 → 资本政策 → 硬件制造 → 快讯速览 顺序
2. 头条放当天最重要的 1-2 条；快讯速览放值得记录但无需长篇展开的短消息
3. 去重：同一事件的不同报道合并为一条
4. 标题 12-25 中文字符；正文 75-150 字
5. 财经数据保留美元原文并附人民币换算，汇率取 1 USD ≈ 7.2 CNY
6. 英文专业术语首次出现标注原文，如：「高带宽存储器（HBM）」
7. 中国大陆新闻客观中立，不夹带政治评判
8. 不确定时标注「据X报道」
9. 每条新闻尽量匹配 YouTube 视频（URL 必须是 youtube.com/watch?v= 格式）；若无合适视频，表格写「暂无相关视频报道」
10. 不编造新闻；不重复使用同一 YouTube 链接
11. 只输出日报 Markdown，不要任何额外说明"""

    user = f"""【新闻素材】
{news_json}

【YouTube 视频素材】
{yt_json}

请严格按照上述格式和规则生成日报。"""

    return system, user

def call_deepseek(system, user):
    client = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=8192,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"  DeepSeek 调用失败 (第 {attempt+1}/3 次): {e}")
            if attempt < 2:
                time.sleep(8)
            else:
                raise

# ── 发邮件 ────────────────────────────────────────────────

def send_email(md_text, start, end):
    wd = weekday_cn(start)
    if start != end:
        subj = f"🔥 科技日报 · {start.month}月{start.day}日-{end.month}月{end.day}日（{wd}）"
    else:
        subj = f"🔥 科技日报 · {start.month}月{start.day}日（{wd}）"

    html = md_to_email_html(md_text)

    msg = MIMEMultipart("alternative")
    msg["From"] = GMAIL_ADDR
    msg["To"] = RECIPIENT
    msg["Subject"] = subj
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(GMAIL_ADDR, GMAIL_PASS)
        s.sendmail(GMAIL_ADDR, RECIPIENT, msg.as_string())
    print("  ✓ 邮件已发送")

def md_to_email_html(md):
    """简易 Markdown → HTML（适合 Gmail 渲染）"""
    lines = md.split("\n")
    out = []
    in_table = False

    for line in lines:
        if line.startswith("### "):
            out.append(f'<h3 style="margin:16px 0 8px;color:#222;">{line[4:]}</h3>')
        elif line.startswith("## "):
            out.append(f'<h2 style="margin:20px 0 10px;color:#111;border-bottom:1px solid #eee;padding-bottom:6px;">{line[3:]}</h2>')
        elif line.startswith("# "):
            out.append(f'<h1 style="margin:0 0 12px;color:#000;font-size:22px;">{line[2:]}</h1>')
        elif line.startswith("> "):
            out.append(f'<blockquote style="border-left:3px solid #e65100;margin:10px 0;padding:6px 14px;background:#fafafa;color:#555;">{line[2:]}</blockquote>')
        elif line.startswith("---"):
            out.append('<hr style="border:none;border-top:1px solid #eee;margin:18px 0;">')
        elif line.startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if not in_table:
                in_table = True
                out.append('<table style="border-collapse:collapse;width:100%;margin:8px 0;font-size:14px;">')
            out.append("<tr>" + "".join(f'<td style="border:1px solid #ddd;padding:5px 10px;">{c}</td>' for c in cells) + "</tr>")
        else:
            if in_table:
                out.append("</table>")
                in_table = False
            # 粗体
            l = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            out.append(f'<p style="margin:6px 0;line-height:1.8;">{l}</p>' if l.strip() else "<br>")

    if in_table:
        out.append("</table>")

    body = "".join(out)
    return f"""<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#333;">
{body}
</body></html>"""

# ── 入口 ──────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  每日科技日报 · 自动生成")
    print("=" * 55)

    start, end = get_date_range()
    dr = f"{start} ~ {end}" if start != end else str(start)
    print(f"\n📅 覆盖日期: {dr}  ({weekday_cn(start)})")

    tav = TavilyClient(api_key=TAVILY_KEY)

    # Round 1
    print("\n🔍 第一轮 · 新闻搜索")
    r1 = round1(tav, start, end)
    n1 = sum(len(g.get("results", [])) for g in r1)
    print(f"  获取 {n1} 条结果")

    # Round 2
    print("\n🎬 第二轮 · YouTube 搜索")
    r2 = round2(tav, r1)
    n2 = sum(len(g.get("results", [])) for g in r2)
    print(f"  获取 {n2} 条结果")

    # Format
    print("\n🤖 DeepSeek 格式化中 ...")
    sys_p, usr_p = build_prompt(r1, r2, start, end)
    report = call_deepseek(sys_p, usr_p)
    print(f"  日报 {len(report)} 字符")

    # Email
    print("\n📧 发送邮件 ...")
    send_email(report, start, end)

    print("\n" + "=" * 55)
    print(report)
    print("=" * 55)
    print("\n✅ 完成！")

if __name__ == "__main__":
    main()
