# 🔧 日报质量优化 · v2 迭代计划

## 问题汇总

### 1. 定时延迟
- **现象**：cron 设定 `55 1 * * *`（北京时间 9:55），近三日实际触发时间为 11:14 / 11:22 / 11:31
- **原因**：GitHub Actions 高峰期排队
- **方案**：cron 提前至 `15 1 * * *`（北京时间 9:15，留 45 分钟缓冲）

### 2. 新闻时效性差
- **现象**：出现 7 月旧闻、上周重复新闻
- **原因**：Tavily 搜索 query 中日期约束不够精确；提示词未强制要求日期标注
- **方案**：
  - query 中嵌入精确日期格式 `"August 9 2026"`
  - prompt 中新增要求「每条新闻正文必须包含具体日期（如"8月9日"），严禁出现上个月或上周已报道过的旧闻」
  - 在 prompt 中加自检步骤：「检查所有新闻的日期是否在覆盖范围内」

### 3. 新闻同质化严重
- **现象**：估值变化 / IPO / 巨头投资 / 收购 类新闻占比过高
- **缺失**：
  - DeepSeek API 价格调整
  - Kimi K3 开源 + MoE 架构细节
  - Anthropic 研究论文（mechanistic interpretability / alignment 等）
  - 模型技术突破（推理、多模态、Agent 框架）
  - 开源社区动态（HuggingFace、模型微调、benchmark 更新）
- **方案**：
  - 第一轮搜索增加技术向 query：
    - `"AI research paper breakthrough {date}"`
    - `"DeepSeek Kimi open source model {date}"`
    - `"Anthropic research alignment interpretability {date}"`
    - `"AI benchmark leaderboard update {date}"`
    - `"open source LLM fine-tuning release {date}"`
  - 调整 prompt 优先级：「AI 技术突破 / 开源模型 / 研究论文 > 融资估值 > 政策」

### 4. YouTube 视频同质化
- **现象**：大部分视频来自 Bloomberg 日报频道，缺乏多样性
- **缺失**：科技播客录屏、独立博主深度解读
- **方案**：
  - 第二轮搜索不再只搜 `"{title} YouTube"`，增加以下变体：
    - `"{topic} tech podcast"`
    - `"{topic} AI explained"`
    - `"{topic} analysis breakdown"`
  - 在 prompt 中要求优先匹配 podcasts 和独立创作者，Bloomberg/CNBC 仅作备选

### 5. 无国内消息源
- **现状**：全部依赖 Tavily（英文国际源），中文科技动态缺失
- **方案**（可选，复杂度较高）：
  - 增加一轮中文搜索（搜狗/百度/36氪 RSS 或直接爬取）
  - 或使用 DeepSeek 联网搜索能力补充中文新闻

---

## 具体改动清单

### A. workflow yaml
- [ ] cron: `55 1 * * *` → `15 1 * * *`

### B. main.py — 搜索 query 调整
- [ ] 新增 3-4 条技术向 query（AI 论文、开源模型、benchmark）
- [ ] 所有 query 内嵌精确英文日期格式

### C. main.py — round2 视频搜索
- [ ] 每条新闻搜 3 种变体：YouTube / tech podcast / analysis breakdown
- [ ] query 上限从 20 扩到 30

### D. main.py — DeepSeek 格式化 prompt
- [ ] 正文 120-200 字 → 150-220 字
- [ ] 强制要求每条新闻正文含具体日期（"据X月X日报道"）
- [ ] 新增规则：「禁止出现报道日期早于覆盖范围的新闻」
- [ ] 调整内容优先级：技术突破 > 开源动态 > 研究论文 > 资本市场 > 政策
- [ ] 视频匹配优先级：独立播客/博主 > 科技媒体频道 > Bloomberg/CNBC 新闻日报
- [ ] 新增自检步骤：Step 6 增加日期校验

---

## 讨论问题

1. **要不要加中文源**？如果加，最简单的方式是 Tavily 搜索时把一部分 query 改成中文（如 `"DeepSeek 涨价 2026年8月"`），或者另起一轮中文搜索。中文源能补上 DeepSeek/Kimi 等国内动态，但可能增加搜索耗时。

2. **国内视频平台要不要加**？Bilibili 上有很多高质量中文科技播客，但 GitHub Actions runner 在美国，访问 B 站可能需要额外处理。先优化 YouTube 多样性，还是直接考虑 B 站？

3. **日报长度**：目前 10-12 条。如果技术新闻密度增加，是否允许扩到 12-14 条？
