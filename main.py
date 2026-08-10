#!/usr/bin/env python3
"""
每日科技日报自动生成脚本 v2
- Round 0: DeepSeek 联网搜索（中英文混合）
- Round 1: Tavily 新闻搜索（6 query basic + days=2）
- Round 2: Tavily 视频搜索（5 新闻 × 2 变体 basic）
- 格式化: DeepSeek Chat（双层结构）
- 发送: Gmail SMTP
"""

import os, json, smtplib, time, re
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
    """周一覆盖周五~周日，周二~周五覆盖昨天。仅在周一触发时用到（workflow cron 1-5）"""
    today = date.today()
    if today.weekday() == 0:  # Monday
        return today - timedelta(days=3), today - timedelta(days=1)
    return today - timedelta(days=1), today - timedelta(days=1)

def fmt_date_range(start, end):
    if start == end:
        return start.strftime("%B %-d %Y")
    return f"{start.strftime('%B %-d')} – {end.strftime('%B %-d')} {start.year}"

def fmt_date_en(d):
    return d.strftime("%B %-d %Y")

def weekday_cn(d):
    return ["周一","周二","周三","周四","周五","周六","周日"][d.weekday()]

def date_title_cn(d):
    return f"{d.year}年{d.month}月{d.day}日"

# ── Round 0: DeepSeek 联网搜索 ────────────────────────────

DS_QUERIES = [
    "中文 AI 大模型 开源 技术突破 最新动态",
    "China AI startup funding regulation latest",
    "AI research paper breakthrough benchmark release",
    "科技行业 芯片 半导体 供应链 最新新闻",
    "AI agent multimodal reasoning open source framework",
]

def round0_deepseek():
    """Round 0: DeepSeek 联网搜索，补中文源 + 技术论文。失败静默降级。"""
    print("\n🧠 Round 0 · DeepSeek 联网搜索")
    client = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")
    all_results = []

    for q in DS_QUERIES:
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a web search assistant. Search the web and return results in JSON format with title, url, and content fields."},
                    {"role": "user", "content": f"Search for: {q}\n\nReturn the top 10 results as a JSON array with fields: title, url, content."},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            text = resp.choices[0].message.content or ""
            # Try to parse JSON from response
            try:
                items = json.loads(text)
                if isinstance(items, list):
                    for item in items:
                        item["query"] = q
                    all_results.append({"query": q, "results": items})
                    print(f"  ✓ DeepSeek: {q[:40]}... → {len(items)} 条")
                else:
                    raise ValueError("not a list")
            except (json.JSONDecodeError, ValueError):
                # Fallback: wrap as single result
                all_results.append({"query": q, "results": [{"title": q, "url": "", "content": text[:2000]}]})
                print(f"  ~ DeepSeek: {q[:40]}... → raw text ({len(text)} chars)")
        except Exception as e:
            print(f"  ✗ DeepSeek 失败 [{q[:40]}...]: {e}")
            # Silently skip this query
    return all_results

# ── Tavily 搜索 ────────────────────────────────────────────

ROUND1_QUERIES = [
    "AI artificial intelligence news breakthrough release {date_en}",
    "Nvidia TSMC Intel semiconductor chip hardware {date_en}",
    "AI startup funding investment IPO merger {date_en}",
    "AI regulation policy government executive order {date_en}",
    "open source LLM model release benchmark {date_en}",
    "tech industry Apple Google Microsoft Meta news {date_en}",
]

ROUND1_MONDAY_EXTRA = "tech news weekend recap roundup {date_en}"

def search_tavily(client, query, depth="basic", days=2):
    try:
        r = client.search(query, search_depth=depth, max_results=8, days=days)
        return {"query": query, "results": r.get("results", [])}
    except Exception as e:
        print(f"  ✗ Tavily 失败 [{query[:50]}...]: {e}")
        return {"query": query, "results": [], "error": str(e)}

def round1_tavily(client, start, end):
    """Round 1: Tavily 新闻搜索。6 query basic + days=2。周一 +1。"""
    date_en = fmt_date_en(end)
    queries = [q.format(date_en=date_en) for q in ROUND1_QUERIES]

    if start != end:  # Monday mode
        queries.append(ROUND1_MONDAY_EXTRA.format(date_en=fmt_date_range(start, end)))

    print(f"  Tavily Round 1: {len(queries)} query, basic, days=2")
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(search_tavily, client, q, "basic", 2): q for q in queries}
        for fut in as_completed(futures):
            results.append(fut.result())
    return results

def round2_tavily(client, all_news_results):
    """Round 2: 从合并素材中提取 Top 5 新闻关键词，每条搜双变体，共 10 query basic。"""
    # Collect candidate titles from all previous rounds
    seen, candidates = set(), []
    for group in all_news_results:
        for r in group.get("results", []):
            t = r.get("title", "")[:80]
            if t and t not in seen:
                seen.add(t)
                candidates.append(t)
                if len(candidates) >= 5:
                    break
        if len(candidates) >= 5:
            break

    queries = []
    for kw in candidates:
        queries.append(f"{kw} podcast analysis explained breakdown")
        queries.append(f"{kw} news update")

    print(f"  Tavily Round 2: {len(queries)} query, basic (5 新闻 × 2 变体)")
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(search_tavily, client, q, "basic"): q for q in queries}
        for fut in as_completed(futures):
            results.append(fut.result())
    return results

# ── 素材编译 ──────────────────────────────────────────────

def compile_items(all_results):
    items = []
    for group in all_results:
        for r in group.get("results", []):
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            })
    return items

# ── DeepSeek 格式化 Prompt ─────────────────────────────────

def build_prompt(ds_results, r1_results, r2_results, start, end):
    all_items = compile_items(ds_results + r1_results)
    yt_items = compile_items(r2_results)

    news_json = json.dumps(all_items, ensure_ascii=False, indent=2)
    yt_json = json.dumps(yt_items, ensure_ascii=False, indent=2)
    if len(news_json) > 35000: news_json = news_json[:35000] + "\n...[truncated]"
    if len(yt_json) > 12000: yt_json = yt_json[:12000] + "\n...[truncated]"

    wd = weekday_cn(start)
    dt = date_title_cn(start)
    if start != end:
        dr = f"{start.year}年{start.month}月{start.day}日-{end.month}月{end.day}日"
    else:
        dr = f"{start.year}年{start.month}月{start.day}日"

    system = f"""你是资深科技新闻编辑，读者关注 AI、半导体、科技政策和资本市场。

请基于下方搜索素材生成中文科技日报。当前日期：{dt}（{wd}），覆盖：{dr}

【输出格式（双层结构）】

# 🔥 科技日报 · {dt}（{wd}）

> **一句话摘要：** [1-2 句概括最重要的动态]

---
## 🔥 今日必读

**1. 标题（12–25 中文字符）**
[正文 150–220 字：发生了什么 + 为什么重要 + 行业影响 + 关键数字。必须从素材中提取具体日期（如"8月9日，据Reuters报道..."），禁止脑补日期。]

| 视频解读 | 来源 |
|---|---|
| [标题](完整 YouTube URL) | 频道名 |

**2. 标题**
...
**3. 标题**
...

---
## 🗣️ 大人物声音
...
## 🚀 模型 & 产品
...
## 💰 资本 & 政策
...
## 🏭 硬件 & 制造
...
## 📊 快讯速览

---
> 📌 以上新闻均来自 **{dr}** 的最新报道。

【规则】
1. 今日必读 3 条，不限板块，放当天最重要的新闻。后五板块各 1–2 条 + 快讯 1–2 条，总计 10–12 条（周一可 12–14 条）。
2. 内容优先级：AI 技术突破 ≈ 开源动态 ≈ 研究论文 > 行业重大事件 > 资本市场 > 政策监管。每日技术/研究类新闻应占总量一半以上。
3. 去重：同一事件合并为一条；今日必读不在后五板块重复；快讯不与前面任何板块重复。
4. 每段正文 150–220 字，必须包含具体日期（从素材中提取，如"8月9日"），无法提取则标注"据近日报道"。
5. 严禁旧闻：报道日期早于 {dr} 的新闻必须过滤掉。同一事件若超过 3 天且无新发展则跳过。
6. 财经数据保留美元并附人民币换算（1 USD ≈ 7.2 CNY）。英文术语首次附原文。
7. 中国大陆新闻客观中立。
8. 视频匹配优先级：优先选择独立播客/博主深度解读（podcast/analysis/explained），其次官方发布/学术演讲，最后新闻日报（Bloomberg/CNBC）仅作兜底。每条新闻 1–2 个视频；若无合适视频写「暂无相关视频报道」。
9. 搜索素材（Round 0 + Round 1）中可能含有 YouTube 链接，请逐一检查并优先匹配到对应新闻。
10. 不编造新闻、不重复 YouTube 链接、不确定时标注"据X报道"。只输出日报 Markdown，不要额外说明。"""

    user = f"""【新闻素材（Round 0 DeepSeek + Round 1 Tavily）】
{news_json}

【视频素材（Round 2 Tavily）】
{yt_json}

请严格按上述格式和规则生成日报。"""

    return system, user

def call_deepseek(system, user):
    client = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.3,
                max_tokens=8192,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"  DeepSeek 调用失败 (第 {attempt+1}/3 次): {e}")
            if attempt < 2: time.sleep(8)
            else: raise

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
    lines = md.split("\n")
    out, in_table = [], False
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
            l = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            out.append(f'<p style="margin:6px 0;line-height:1.8;">{l}</p>' if l.strip() else "<br>")
    if in_table: out.append("</table>")
    body = "".join(out)
    return f"""<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#333;">
{body}
</body></html>"""

# ── 入口 ──────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  每日科技日报 · 自动生成 v2")
    print("=" * 55)

    start, end = get_date_range()
    dr = f"{start} ~ {end}" if start != end else str(start)
    monday = start != end
    print(f"\n📅 覆盖: {dr}  ({weekday_cn(start)}){' [周一三合一]' if monday else ''}")

    # Round 0: DeepSeek
    ds_results = round0_deepseek()
    ds_count = sum(len(g.get("results", [])) for g in ds_results)
    print(f"  DeepSeek 共 {ds_count} 条")

    # Round 1: Tavily
    print("\n🔍 Round 1 · Tavily 新闻")
    tav = TavilyClient(api_key=TAVILY_KEY)
    r1 = round1_tavily(tav, start, end)
    r1_count = sum(len(g.get("results", [])) for g in r1)
    print(f"  Tavily R1 共 {r1_count} 条")

    # Round 2: Tavily 视频
    print("\n🎬 Round 2 · Tavily 视频")
    r2 = round2_tavily(tav, ds_results + r1)
    r2_count = sum(len(g.get("results", [])) for g in r2)
    print(f"  Tavily R2 共 {r2_count} 条")

    # Format
    print("\n🤖 DeepSeek 格式化 ...")
    sys_p, usr_p = build_prompt(ds_results, r1, r2, start, end)
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
