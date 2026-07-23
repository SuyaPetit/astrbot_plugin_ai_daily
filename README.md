# AI 日报插件 v2.0 (astrbot_plugin_ai_daily)

聚合多个主流 AI 资讯平台，每日自动汇总或按需查询 AI 领域最新动态。
支持**精美图片渲染**、**KV 持久化缓存**、**AI 智能摘要**、**LLM Tool 注册**。

## ✨ 功能特性

| 特性 | 说明 |
|------|------|
| 🖼️ 图片日报 | 使用 `html_render` 将新闻渲染为精美暗色卡片图片 |
| 💾 持久化缓存 | 使用 AstrBot KV 存储（`put_kv_data`）跨重启保留当日缓存 |
| 🤖 AI 摘要 | 调用 `context.llm_generate` 对当日资讯生成 AI 摘要 |
| 🔧 LLM Tool | 注册 `get_ai_news` 工具，让 AI 对话时可主动调用获取新闻 |
| ⚡ 并发抓取 | `asyncio.gather` 并发请求所有来源，快速聚合 |
| 🔄 智能缓存 | 当日结果缓存，重复调用秒级响应 |

## 📡 新闻来源（10+）

| 来源 | 类型 | 说明 |
|------|------|------|
| 🔶 Hacker News | API | 关键词过滤 AI 相关热帖 |
| 📄 ArXiv CS.AI | RSS | 最新 AI 学术论文 |
| 🔷 The Verge AI | RSS | AI 行业新闻 |
| 🔬 MIT Technology Review | RSS | 技术趋势评论 |
| 💼 VentureBeat AI | RSS | AI 商业动态 |
| 🤖 OpenAI Blog | RSS | OpenAI 官方公告 |
| 🔴 Google AI Blog | Atom | Google AI 研究 |
| 🤗 Hugging Face Blog | Atom | AI 工具与模型 |
| 📱 少数派 | RSS | 国内科技资讯 |
| 🚀 36氪 AI | RSS | 国内 AI 创业动态 |

## 💬 指令列表

| 指令 | 功能 |
|------|------|
| `/ai日报` | 获取今日完整 AI 日报（默认图片格式） |
| `/ai日报文字` | 以纯文字格式获取日报 |
| `/ai日报刷新` | 强制刷新，清除缓存重新抓取 |
| `/ai日报来源` | 查看当前启用的来源 |
| `/ai新闻` | 快速获取精选 AI 新闻（3源×2条）|
| `/arxiv今日` | 获取 ArXiv 最新 AI 论文（8篇）|
| `/hn今日ai` | Hacker News AI 精选热帖 |
| `/ai日报帮助` | 查看帮助信息 |

## ⚙️ 配置说明

在 AstrBot WebUI → 插件 → AI 日报 → 配置 中可调整：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled_sources` | list | 7个来源 | 启用的新闻来源 key 列表 |
| `items_per_source` | int | 3 | 每来源显示条数 |
| `render_image` | bool | true | 是否渲染为图片 |
| `ai_summary` | bool | false | 是否启用 AI 智能摘要 |

> **注意**：启用 `ai_summary` 需要在 AstrBot 中已配置可用的 LLM 提供商。

## 🛠️ 技术实现

```
AstrBot API 使用：
  ├── Star.html_render()        → 将 Jinja2 HTML 模板渲染为图片
  ├── Star.put_kv_data()        → 持久化保存当日日报到 KV 存储
  ├── Star.get_kv_data()        → 读取当日 KV 缓存
  ├── context.llm_generate()   → 调用 LLM 生成 AI 摘要
  ├── context.get_current_chat_provider_id() → 获取当前 LLM ID
  └── @filter.llm_tool          → 注册 get_ai_news 为 AI 可调用工具

外部依赖：
  └── aiohttp                  → 异步 HTTP 请求（RSS/API 抓取）
```

## 📦 安装

将插件目录放入 AstrBot 的 `data/plugins/` 目录，重载插件即可：

```bash
cd AstrBot/data/plugins
git clone <仓库地址> astrbot_plugin_ai_daily
```

**AstrBot 版本要求：>= 4.9.2**（KV 存储 API 需要此版本）

## 🔑 版本历史

### v2.0.0
- ✅ 新增 `html_render` 精美图片渲染（暗色渐变卡片）
- ✅ 新增 KV 持久化缓存（`put_kv_data` / `get_kv_data`）
- ✅ 新增 AI 智能摘要（`context.llm_generate`）
- ✅ 新增 LLM Tool 注册（`@filter.llm_tool get_ai_news`）
- ✅ 新增 `/ai日报文字` 降级指令
- ✅ 图片渲染失败自动降级为文字

### v1.0.0
- 初始版本，纯文字日报，内存缓存

## 📄 许可证

MIT License
