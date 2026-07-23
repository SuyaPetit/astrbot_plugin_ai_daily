# AI 日报插件 v2.1 (astrbot_plugin_ai_daily)

聚合国内主流 AI 资讯平台，每日自动汇总或按需查询 AI 领域最新动态。
**默认来源全部为大陆可直接访问的媒体**，无需代理即可正常使用。

## ✨ 功能特性

| 特性 | 说明 |
|------|------|
| 🇨🇳 大陆优先 | 默认 7 个来源均为国内可访问媒体，开箱即用 |
| ⏱️ 快速响应 | 单源 8s 超时、整体 25s 上限，绝不卡死 |
| 🖼️ 图片日报 | 使用 `html_render` 渲染暗色渐变卡片图片 |
| 💾 持久化缓存 | 使用 AstrBot KV 存储跨重启保留当日缓存 |
| 🤖 AI 摘要 | 可选调用内置 LLM 对资讯生成每日摘要 |
| 🔧 LLM Tool | 注册 `get_ai_news`，AI 对话时可主动获取新闻 |
| 🌐 国际可选 | HN、ArXiv、OpenAI Blog 等保留为可选配置 |

---

## 📡 新闻来源

### 🇨🇳 大陆来源（默认启用）

| Key | 媒体 | RSS 地址 |
|-----|------|---------|
| `qbitai` | ⚛️ 量子位 | `qbitai.com/feed` |
| `jiqizhixin` | 🧠 机器之心 | `jiqizhixin.com/rss` |
| `36kr_ai` | 🚀 36氪 | `36kr.com/feed` |
| `huxiu` | 🐯 虎嗅 | `huxiu.com/rss/0.rss` |
| `ifanr` | 💡 爱范儿 | `ifanr.com/feed` |
| `geekpark` | 🎯 极客公园 | `geekpark.net/rss` |
| `infoq_cn` | 📊 InfoQ 中文 | `infoq.cn/feed` |
| `solidot` | 🔩 Solidot | `solidot.org/index.rss` |
| `sspai` | 📱 少数派 | `sspai.com/feed` |

### 🌐 国际来源（可选，需良好网络）

| Key | 媒体 |
|-----|------|
| `hacker_news` | 🔶 Hacker News AI 精选 |
| `arxiv_ai` | 📄 ArXiv CS.AI |
| `the_verge_ai` | 🔷 The Verge AI |
| `venturebeat_ai` | 💼 VentureBeat AI |
| `openai_blog` | 🤖 OpenAI Blog |
| `hugging_face_blog` | 🤗 Hugging Face Blog |
| `mit_tech_review` | 🔬 MIT Technology Review |

---

## 💬 指令列表

### 主要指令

| 指令 | 功能 |
|------|------|
| `/ai日报` | 获取今日完整 AI 日报（默认图片格式） |
| `/ai日报文字` | 以纯文字格式获取日报 |
| `/ai日报刷新` | 强制刷新，清除缓存重新抓取 |
| `/ai日报来源` | 查看当前启用的来源列表 |
| `/ai日报帮助` | 查看帮助信息 |

### 快捷查询

| 指令 | 功能 |
|------|------|
| `/ai新闻` | 精选快讯（量子位 + 36氪 + 极客公园，每源 2 条） |
| `/量子位` | 量子位最新 AI 资讯（8 条） |
| `/机器之心` | 机器之心最新 AI 资讯（8 条） |
| `/hn今日ai` | Hacker News AI 热帖（需国际网络） |

---

## ⚙️ 配置说明

在 **AstrBot WebUI → 插件 → AI 日报 → 配置** 中调整：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled_sources` | list | 7 个大陆来源 | 启用的来源 key 列表（见上表） |
| `items_per_source` | int | `3` | 每个来源显示的条数（建议 2-5） |
| `render_image` | bool | `true` | 是否渲染为图片，关闭则纯文字 |
| `ai_summary` | bool | `false` | 是否启用 AI 智能摘要（需配置 LLM） |

### 示例：加入国际来源

```json
{
  "enabled_sources": [
    "qbitai", "jiqizhixin", "36kr_ai", "huxiu",
    "hacker_news", "arxiv_ai"
  ],
  "items_per_source": 3,
  "render_image": true,
  "ai_summary": false
}
```

> ⚠️ 国际来源在大陆网络下会触发 8s 超时后自动跳过，不影响其他来源正常显示。

---

## 🛠️ 技术实现

```
网络层：
  └── aiohttp 并发抓取，单源 8s / 整体 25s 超时保护

AstrBot API：
  ├── Star.html_render()                      → Jinja2 HTML 渲染为图片
  ├── Star.put_kv_data() / get_kv_data()      → KV 持久化缓存当日日报
  ├── context.llm_generate()                  → 调用 LLM 生成 AI 摘要
  ├── context.get_current_chat_provider_id()  → 获取当前 LLM Provider
  └── @filter.llm_tool                        → 注册 get_ai_news AI 工具

数据格式支持：
  ├── RSS 2.0 (量子位、36氪、虎嗅等)
  ├── Atom (机器之心、Google AI Blog 等)
  └── HN JSON API (Hacker News)
```

---

## 📦 安装

将插件目录放入 AstrBot 的 `data/plugins/` 目录，重载插件即可：

```bash
cd AstrBot/data/plugins
git clone <仓库地址> astrbot_plugin_ai_daily
```

**AstrBot 版本要求：>= 4.9.2**（KV 存储 API 需要此版本）

**依赖：** `aiohttp>=3.8.0`（其余功能均为 AstrBot 内置）

---

## 📋 版本历史

### v2.1.0（当前）
- ✅ **默认来源全部替换为大陆可访问媒体**（量子位、机器之心、36氪、虎嗅、爱范儿、极客公园、InfoQ）
- ✅ 新增单源 **8s 超时** + 整体 **25s 硬上限**，彻底避免卡死
- ✅ 新增 `/量子位`、`/机器之心` 快捷指令
- ✅ 国际来源保留为可选配置，配置后可正常使用
- ✅ 超时来源静默跳过，有数据的来源正常显示

### v2.0.0
- ✅ 新增 `html_render` 精美图片渲染（暗色渐变卡片）
- ✅ 新增 KV 持久化缓存（`put_kv_data` / `get_kv_data`）
- ✅ 新增 AI 智能摘要（`context.llm_generate`）
- ✅ 新增 LLM Tool 注册（`@filter.llm_tool get_ai_news`）
- ✅ 图片渲染失败自动降级为文字

### v1.0.0
- 初始版本，纯文字日报，内存缓存，以海外来源为主

---

## 📄 许可证

MIT License
