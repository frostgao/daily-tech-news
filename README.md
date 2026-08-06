# 每日科技日报 · Daily Tech News Report

每天自动生成一份中文科技日报，覆盖 AI、半导体、科技政策和资本市场。通过 GitHub Actions 定时运行，结果发送到指定邮箱。

## 工作原理

1. **Tavily** 多轮并行搜索全球科技新闻
2. **DeepSeek** 按六大板块（头条 / 大人物声音 / 模型产品 / 资本政策 / 硬件制造 / 快讯速览）整理成格式化日报
3. **Gmail SMTP** 发送 HTML 邮件到指定邮箱

## 使用方式

### 1. Fork 本仓库

### 2. 获取 API Key

- **[Tavily](https://tavily.com)** — 注册后在 Dashboard 获取，免费 1000 次/月
- **[DeepSeek](https://platform.deepseek.com)** — 注册后在 API Keys 页面获取

### 3. 获取 Gmail App Password

1. 确保 Google 账号已开启[两步验证](https://myaccount.google.com/signinoptions/twostepverification)
2. 进入 [App Passwords](https://myaccount.google.com/apppasswords)，输入名称 `DailyNews`，生成 16 位密码（**去掉空格**）

### 4. 设置 Secrets

仓库 → Settings → Secrets and variables → Actions，添加以下 5 个：

| Secret | 说明 |
|---|---|
| `TAVILY_API_KEY` | Tavily API key |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `GMAIL_ADDRESS` | 发件 Gmail 地址 |
| `GMAIL_APP_PASSWORD` | Gmail App Password（无空格） |
| `RECIPIENT_EMAIL` | 收件邮箱（可与发件相同） |

### 5. 启用 Actions

Actions 标签 → 点击 **Daily Tech News Report** → Enable workflow。

### 6. 测试

Actions → Daily Tech News Report → **Run workflow** 手动触发一次，检查邮箱是否收到。

## 定时

北京时间每天 **9:55 AM** 自动运行（UTC 1:55）。修改 `.github/workflows/daily_news.yml` 中的 `cron` 即可调整时间。

## 输出格式

日报包含 10 条新闻，分六大板块，每条含标题、正文（75-150 字）、YouTube 视频链接，底部注明信源日期。

```
# 🔥 科技日报 · 2026年8月5日（周三）

> **一句话摘要：** ...

## 🔥 头条
## 🗣️ 大人物声音
## 🚀 模型 & 产品
## 💰 资本 & 政策
## 🏭 硬件 & 制造
## 📊 快讯速览
```
