# 日报质量优化 · 完整修改计划 v3

---

## 一、定时策略

| 项目 | 旧值 | 新值 |
|---|---|---|
| cron | `55 1 * * *` | `15 1 * * 1-5` |
| 运行日 | 每天 | 周一～周五 |
| 周一覆盖 | 昨天 | 上周五+周六+周日 |

`1-5` = 周一至周五，`15 1` = UTC 1:15 = 北京时间 9:15。

---

## 二、搜索架构

DeepSeek 补质量 + Tavily 做主力，不是叠加而是替代。

```
Round 0: DeepSeek 联网搜索  5 query（中文 + 研究论文）
    补 Tavily 中文盲区 + 长尾技术新闻
    失败/超时 → 静默降级

Round 1: Tavily 新闻搜索  6 query（全 basic, days=2）
    国际主流科技媒体覆盖

Round 2: Tavily 视频搜索  10 query（5 新闻 × 2 变体，全 basic）
    YouTube 播客 / 博主 / 日报
```

### 2.1 Round 0 — DeepSeek 联网搜索

不消耗 Tavily credit。query 设计原则：广泛、可泛化、长期有效。

```
"中文 AI 大模型 开源 技术突破 最新动态"
"China AI startup funding regulation latest"
"AI research paper breakthrough benchmark release"
"科技行业 芯片 半导体 供应链 最新新闻"
"AI agent multimodal reasoning open source framework"
```

### 2.2 Round 1 — Tavily 新闻搜索

全部 `search_depth="basic"` + `days=2` + 嵌入精确英文日期。

```
"AI artificial intelligence news breakthrough release {date_str}"
"Nvidia TSMC Intel semiconductor chip hardware {date_str}"
"AI startup funding investment IPO merger {date_str}"
"AI regulation policy government executive order {date_str}"
"open source LLM model release benchmark {date_str}"
"tech industry Apple Google Microsoft Meta news {date_str}"
```

周一额外 +1 query：
```
"tech news weekend recap roundup {weekend_date_range}"
```

### 2.3 Round 2 — Tavily 视频搜索

从 Round 0+1 合并素材提取 Top 5 新闻关键词，每条双变体：

```
变体 A: "{keywords} podcast analysis explained breakdown"
变体 B: "{keywords} news update"
```

全部 basic，共 10 query。

### 2.4 Credit 预算

| 搜索层 | query 数 | 深度 | 日均 credit |
|---|---|---|---|
| Round 0 DeepSeek | 5 | — | 0 |
| Round 1 Tavily | 6（周一 7）| basic | ~18（周一 ~21）|
| Round 2 Tavily | 10 | basic | ~30 |
| **Tavily 合计** | | | **~48（周一 ~51）** |

- 当前日均：~55 credit
- 优化后日均：**~48 credit**（降 13%）
- 本月剩余 15 天：48 × 15 ≈ **720 credit**，当前余额 584

> ⚠️ 仍超 ~136 credit（≈$1.36）。Tavily 超量自动按 $0.01/credit 扣费，8 月补差价不到 ¥10，可以接受。9 月起跑满一个月约需 960 credit，刚好卡在免费 1000 以内。

---

## 三、输出格式（双层结构）

```
# 🔥 科技日报 · YYYY年MM月DD日（周X）

> **一句话摘要：**

---
## 🔥 今日必读
**1. ...**
**2. ...**
**3. ...**

---
## 🗣️ 大人物声音
## 🚀 模型 & 产品
## 💰 资本 & 政策
## 🏭 硬件 & 制造
## 📊 快讯速览

---
> 📌 以上所有新闻均来自 [日期范围] 的最新报道。
```

- 今日必读：当天最重要的 3 条，不限板块
- 后五板块各 1-2 条 + 快讯 1-2 条
- 总计 10-12 条（周一可 12-14 条）

---

## 四、内容质量标准

### 4.1 正文
- 字数：150-220 字，包含「发生了什么 + 为什么重要 + 行业影响 + 关键数字」
- 日期锚点：从搜索素材中提取新闻发生的具体日期（如"8月9日，据 Reuters 报道..."），不得脑补
- 禁止旧闻：报道日期早于覆盖范围的新闻必须过滤
- 同事件超过 3 天且无新发展 → 跳过

### 4.2 视频优先级
| 优先级 | 类型 | 搜索变体标志 |
|---|---|---|
| A | 独立博主 / 科技播客录屏 | `podcast` `analysis` `explained` |
| B | 官方发布 / 学术演讲 | `official` `presentation` |
| D | 新闻日报（兜底） | `news` `update` |

优先 A/B，D 仅在没有 A/B 时使用。每条新闻匹配 1-2 个视频。

### 4.3 去重
- 同一事件不同报道合并为一条
- 今日必读中的新闻不在后五板块重复
- 快讯速览不与前五板块重复

### 4.4 内容优先级
AI 技术突破 ≈ 开源动态 ≈ 研究论文 > 行业重大事件 > 资本市场 > 政策监管

### 4.5 财经数据
保留美元并附人民币换算（1 USD ≈ 7.2 CNY）

---

## 五、执行流程

```
Step 0: 确定日期范围 + 判断周一
Step 1: DeepSeek 联网搜索（5 query）→ 失败静默降级
Step 2: Tavily Round 1（6-7 query basic, days=2）
Step 3: 素材合并 + 提取 Top 5 新闻关键词
Step 4: Tavily Round 2（10 query basic, 双变体搜视频）
Step 5: 整合所有素材 → DeepSeek 格式化（双层结构）
Step 6: 自检（日期校验、旧闻过滤、去重、视频匹配）
Step 7: Gmail SMTP 发送
```

---

## 六、GitHub Actions

```yaml
on:
  schedule:
    - cron: '15 1 * * 1-5'
  workflow_dispatch:
```

---

## 七、依赖

```
tavily-python>=0.3.0
openai>=1.0.0
```

---

## 八、成本估算（全月 22 工作日）

| 服务 | 用量 | 月费用 |
|---|---|---|
| Tavily | ~960 credit | ✅ 免费（<1000） |
| DeepSeek API | ~110 次 | ~¥5 |
| GitHub Actions | ~5 min/天 | 免费 |
| **合计** | | **~¥5/月** |

---

## 九、待确认

- [ ] 双层结构（今日必读 → 五大板块）
- [ ] 8 月超 ~136 credit，补差价 ~¥10 接受？
- [ ] 5 条新闻搜视频（=10 query）够不够？
- [ ] 确认后直接改代码、commit、push
