#!/usr/bin/env python3
"""
每日科技日报自动生成脚本 v3
- Round 1: Tavily 新闻搜索（topic=news + days 原生日期过滤）
- Round 2: Tavily 视频搜索（按新闻类型分路）
- 数据层: 日期确定性过滤（published_date + 正文日期）
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

def weekday_cn(d):
    return ["周一","周二","周三","周四","周五","周六","周日"][d.weekday()]

def date_title_cn(d):
    return f"{d.year}年{d.month}月{d.day}日"

# ── Tavily 搜索 ────────────────────────────────────────────

ROUND1_QUERIES = [
    "AI model release breakthrough OpenAI Google Anthropic",
    "Nvidia TSMC Intel semiconductor chip hardware",
    "open source LLM model benchmark release",
    "AI startup funding IPO investment merger",
    "AI regulation policy executive order",
    "AI research paper safety alignment interpretability",
    "tech industry Apple Google Microsoft Meta",
    "中国 AI 大模型 开源 技术突破",
    "芯片 半导体 供应链 最新动态",
    "China AI technology policy regulation",
]

ROUND1_MONDAY_EXTRA = "tech news weekend recap roundup"

def search_tavily(client, query, depth="basic", raw_content=True, days=None, topic="news"):
    params = {
        "query": query,
        "search_depth": depth,
        "topic": topic,
        "max_results": 10,
        "include_raw_content": raw_content,
    }
    if days:
        params["days"] = days
    try:
        r = client.search(**params)
        return {"query": query, "results": r.get("results", [])}
    except TypeError as e:
        # 旧版 SDK 可能不支持 days / topic 参数，逐级降级
        print(f"  ! Tavily 参数降级 [{query[:40]}...]: {e}")
        params.pop("days", None)
        try:
            r = client.search(**params)
            return {"query": query, "results": r.get("results", [])}
        except Exception as e2:
            print(f"  ✗ Tavily 降级后仍失败 [{query[:40]}...]: {e2}")
            return {"query": query, "results": [], "error": str(e2)}
    except Exception as e:
        print(f"  ✗ Tavily 失败 [{query[:50]}...]: {e}")
        return {"query": query, "results": [], "error": str(e)}

def round1_tavily(client, start, end):
    """Round 1: Tavily 新闻搜索。topic=news + days 原生日期过滤。"""
    queries = list(ROUND1_QUERIES)
    if start != end:  # Monday mode
        queries.append(ROUND1_MONDAY_EXTRA)

    days = (end - start).days + 1
    print(f"  Tavily Round 1: {len(queries)} query, topic=news, days={days}, raw_content=True")
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(search_tavily, client, q, "basic", True, days, "news"): q for q in queries}
        for fut in as_completed(futures):
            results.append(fut.result())
    return results

TECH_KW = ["model", "ai", "llm", "open source", "research", "chip", "semiconductor", "hardware", "gpu", "release", "launch", "benchmark"]
CAPITAL_KW = ["funding", "ipo", "investment", "acquisition", "merger", "valuation", "raises", "stock", "billion", "million"]
POLICY_KW = ["regulation", "policy", "government", "executive order", "law", "ban", "antitrust", "senate", "congress", "china"]

def classify_variant(title):
    t = title.lower()
    if any(k in t for k in TECH_KW):
        return "explained breakdown"
    if any(k in t for k in CAPITAL_KW):
        return "analysis impact"
    if any(k in t for k in POLICY_KW):
        return "explainer reaction"
    return "analysis"

def round2_tavily(client, all_news_results):
    """Round 2: 提取 Top 10 新闻关键词，按类型分路搜视频，raw_content 关闭。"""
    seen, candidates = set(), []
    for group in all_news_results:
        for r in group.get("results", []):
            t = r.get("title", "")[:80]
            if t and t not in seen:
                seen.add(t)
                candidates.append(t)
                if len(candidates) >= 10:
                    break
        if len(candidates) >= 10:
            break

    queries = []
    for kw in candidates:
        variant = classify_variant(kw)
        queries.append(f"{kw} {variant}")
        queries.append(f"{kw} news")

    print(f"  Tavily Round 2: {len(queries)} query, basic (10 新闻 × 2 变体, raw_content=False)")
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(search_tavily, client, q, "basic", False, None, "general"): q for q in queries}
        for fut in as_completed(futures):
            results.append(fut.result())
    return results


MONTH_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

EN_DATE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?",
    re.IGNORECASE,
)
CN_DATE = re.compile(r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})日?")

def extract_explicit_date(text, default_year):
    """从文本中提取明确日期；找不到返回 None。"""
    for m in EN_DATE.finditer(text or ""):
        month = MONTH_EN.get(m.group(1).lower())
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else default_year
        try:
            return date(year, month, day)
        except ValueError:
            continue
    for m in CN_DATE.finditer(text or ""):
        year = int(m.group(1)) if m.group(1) else default_year
        try:
            return date(year, int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
    return None

def filter_by_date(items, start, end):
    """确定性日期过滤：优先用 Tavily published_date，否则从文本提取明确日期。"""
    kept, dropped = [], 0
    for item in items:
        pub = item.get("published", "")
        if pub:
            try:
                pub_date = date.fromisoformat(str(pub)[:10])
            except ValueError:
                pub_date = None
            if pub_date and pub_date < start:
                dropped += 1
                continue
            if pub_date:
                kept.append(item)
                continue

        # published_date 缺失时，用标题和正文前段提取日期
        text = f"{item.get('title', '')} {item.get('content', '')[:600]}"
        found = extract_explicit_date(text, end.year)
        if found and found < start:
            dropped += 1
            continue
        kept.append(item)
    return kept, dropped

# ── 素材编译 ──────────────────────────────────────────────

def compile_items(all_results):
    items = []
    for group in all_results:
        for r in group.get("results", []):
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "published": r.get("published_date", ""),
            })
    return items

YOUTUBE_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{11})")

def video_id(url):
    """从 YouTube URL 中提取视频 ID；非 YouTube 或格式不符返回 None。"""
    m = YOUTUBE_ID_RE.search(url or "")
    return m.group(1) if m else None

def collect_allowed_video_ids(r1_items, r2_results):
    """只把素材中真实存在的 YouTube 视频 ID 设为允许值。"""
    ids = set()
    urls = [x.get("url", "") for x in r1_items]
    for group in r2_results:
        urls.extend(r.get("url", "") for r in group.get("results", []))
    for u in urls:
        vid = video_id(u)
        if vid:
            ids.add(vid)
    return ids

def sanitize_report_videos(report, allowed_ids):
    """把报告中所有不在素材里的 YouTube 链接替换为暂无视频。"""
    def fix(m):
        vid = video_id(m.group(2))
        if vid in allowed_ids:
            return m.group(0)
        return "暂无相关视频报道"
    pattern = re.compile(r"\[([^\]]*)\]\((https://www\.youtube\.com/watch\?v=[^)]+)\)")
    return pattern.sub(fix, report)

# ── DeepSeek 格式化 Prompt ─────────────────────────────────

def build_prompt(r1_items, r2_results, start, end):
    all_items = r1_items
    yt_items = [x for x in compile_items(r2_results) if video_id(x.get("url", ""))]

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
5. 严禁旧闻：仔细检查每条新闻内容的日期线索（如文中出现的"March""June""7月"等月份或具体日期）。只保留报道日期在 {dr} 范围内的新闻，任何明显更早（如上个月、半年前）的新闻必须立即排除。同一事件若超过 3 天且无新发展则跳过。如果对某条新闻的日期不确定，宁可跳过也不要收录。
6. 财经数据保留美元并附人民币换算（1 USD ≈ 7.2 CNY）。英文术语首次附原文。
7. 中国大陆新闻客观中立。
8. 视频匹配优先级：优先选择独立播客/博主深度解读（podcast/analysis/explained），其次官方发布/学术演讲，最后新闻日报（Bloomberg/CNBC）仅作兜底。每条新闻 1–2 个视频；若无合适视频写「暂无相关视频报道」。尽量为不同新闻匹配不同频道的视频，避免多条新闻都引用同一个短视频。
9. 只能使用【视频素材】中给出的真实 YouTube URL，严禁编造 example1、example2 或任何占位链接。若素材中没有与该新闻匹配的视频，必须写「暂无相关视频报道」。
10. 不编造新闻、不重复 YouTube 链接、不确定时标注"据X报道"。只输出日报 Markdown，不要额外说明。"""

    user = f"""【新闻素材（Tavily，已按日期过滤）】
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
    print("  每日科技日报 · 自动生成 v3")
    print("=" * 55)

    start, end = get_date_range()
    dr = f"{start} ~ {end}" if start != end else str(start)
    monday = start != end
    print(f"\n📅 覆盖: {dr}  ({weekday_cn(start)}){' [周一三合一]' if monday else ''}")

    # Round 1: Tavily
    print("\n🔍 Round 1 · Tavily 新闻")
    tav = TavilyClient(api_key=TAVILY_KEY)
    r1 = round1_tavily(tav, start, end)
    r1_items = compile_items(r1)
    print(f"  Tavily R1 共 {len(r1_items)} 条")

    print("\n🧹 日期过滤 ...")
    r1_items, dropped = filter_by_date(r1_items, start, end)
    print(f"  保留 {len(r1_items)} 条，丢弃 {dropped} 条旧闻")

    # Round 2: Tavily 视频
    print("\n🎬 Round 2 · Tavily 视频")
    r2 = round2_tavily(tav, [{"results": r1_items}])
    r2_count = sum(len(g.get("results", [])) for g in r2)
    print(f"  Tavily R2 共 {r2_count} 条")

    # Format
    print("\n🤖 DeepSeek 格式化 ...")
    allowed_video_ids = collect_allowed_video_ids(r1_items, r2)
    sys_p, usr_p = build_prompt(r1_items, r2, start, end)
    report = call_deepseek(sys_p, usr_p)
    before = len(re.findall(r"youtube\.com/watch\?v=", report))
    report = sanitize_report_videos(report, allowed_video_ids)
    after = len(re.findall(r"youtube\.com/watch\?v=", report))
    print(f"  视频链接校验：{before} → {after} 个（剔除 {before - after} 个无效链接）")
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
