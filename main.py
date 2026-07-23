"""
AstrBot AI 日报插件 v2.0
- 聚合 10+ 国内外 AI 资讯来源（HN、ArXiv、OpenAI、HF、36Kr 等）
- 支持 HTML 渲染成精美图片（html_render）
- 使用 AstrBot KV 存储持久化缓存（put_kv_data / get_kv_data）
- 支持调用 AI 对当日资讯做智能摘要（context.llm_generate）
- 注册 LLM Tool，让 AI 主动拉取新闻（@filter.llm_tool）
"""

import asyncio
import re
from datetime import datetime, date
from xml.etree import ElementTree

import aiohttp

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

# ──────────────────────────────────────────────
# 新闻来源配置
# ──────────────────────────────────────────────

NEWS_SOURCES: dict[str, dict] = {
    "hacker_news": {
        "name": "Hacker News AI精选",
        "url": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "type": "hn_api",
        "emoji": "🔶",
        "color": "#ff6600",
    },
    "arxiv_ai": {
        "name": "ArXiv CS.AI",
        "url": "https://rss.arxiv.org/rss/cs.AI",
        "type": "rss",
        "emoji": "📄",
        "color": "#b31b1b",
    },
    "the_verge_ai": {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "type": "rss",
        "emoji": "🔷",
        "color": "#fa4b18",
    },
    "mit_tech_review": {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "type": "rss",
        "emoji": "🔬",
        "color": "#8a2be2",
    },
    "venturebeat_ai": {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "type": "rss",
        "emoji": "💼",
        "color": "#1a73e8",
    },
    "openai_blog": {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "type": "rss",
        "emoji": "🤖",
        "color": "#10a37f",
    },
    "google_ai_blog": {
        "name": "Google AI Blog",
        "url": "https://blog.research.google/feeds/posts/default",
        "type": "rss",
        "emoji": "🔴",
        "color": "#ea4335",
    },
    "hugging_face_blog": {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "type": "rss",
        "emoji": "🤗",
        "color": "#ff9d00",
    },
    "sspai": {
        "name": "少数派",
        "url": "https://sspai.com/feed",
        "type": "rss",
        "emoji": "📱",
        "color": "#d71a1b",
    },
    "36kr_ai": {
        "name": "36氪 AI",
        "url": "https://36kr.com/feed",
        "type": "rss",
        "emoji": "🚀",
        "color": "#0a66c2",
    },
}

# HN 过滤关键词（AI相关）
HN_AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "ml",
    "llm", "gpt", "claude", "gemini", "llama", "chatgpt",
    "neural", "deep learning", "transformer", "openai", "anthropic",
    "mistral", "stable diffusion", "midjourney", "diffusion",
    "agent", "rag", "embedding", "vector", "copilot", "model",
    "nvidia", "cuda", "inference", "training", "fine-tuning",
    "hugging face", "pytorch", "tensorflow", "model weights",
]

# KV 存储 Key 前缀
_KV_DAILY_PREFIX = "ai_daily_report_"
_KV_NEWS_PREFIX = "ai_daily_news_"

# ──────────────────────────────────────────────
# HTML 日报模板（Jinja2）
# ──────────────────────────────────────────────

DAILY_HTML_TMPL = """
<div style="
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
  color: #e8e8ff;
  padding: 32px 36px;
  min-width: 680px;
  max-width: 760px;
  border-radius: 18px;
  box-shadow: 0 8px 48px rgba(0,0,0,0.6);
">
  <!-- 标题栏 -->
  <div style="display:flex; align-items:center; margin-bottom:24px; border-bottom:1px solid rgba(255,255,255,0.12); padding-bottom:18px;">
    <div style="font-size:36px; margin-right:14px;">📰</div>
    <div>
      <div style="font-size:22px; font-weight:700; letter-spacing:1px; color:#c8b4ff;">AI 资讯日报</div>
      <div style="font-size:13px; color:#888bcc; margin-top:4px;">{{ date }} · 共 {{ total }} 条资讯 · {{ source_count }} 个来源</div>
    </div>
  </div>

  <!-- AI 摘要（可选） -->
  {% if summary %}
  <div style="
    background: rgba(138,43,226,0.18);
    border-left: 3px solid #8a5fff;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 22px;
    font-size: 14px;
    line-height: 1.7;
    color: #cdc7ff;
  ">
    <div style="font-size:12px; color:#8a5fff; font-weight:600; margin-bottom:6px; text-transform:uppercase; letter-spacing:1px;">✨ AI 摘要</div>
    {{ summary }}
  </div>
  {% endif %}

  <!-- 各来源新闻 -->
  {% for src in sources %}
  <div style="margin-bottom:20px;">
    <div style="
      display:flex; align-items:center;
      font-size:15px; font-weight:600;
      color: {{ src.color }};
      margin-bottom:10px;
      padding: 6px 0;
      border-bottom: 1px solid rgba(255,255,255,0.07);
    ">
      <span style="margin-right:8px;">{{ src.emoji }}</span>
      {{ src.name }}
    </div>
    {% for item in src.items %}
    <div style="
      padding: 10px 14px;
      margin-bottom: 8px;
      background: rgba(255,255,255,0.04);
      border-radius: 8px;
      border-left: 2px solid rgba(255,255,255,0.1);
      transition: all 0.2s;
    ">
      <div style="font-size:14px; line-height:1.5; color:#dddcf5; font-weight:500;">
        {{ loop.index }}. {{ item.title }}
      </div>
      {% if item.url %}
      <div style="font-size:11px; color:#5a6acb; margin-top:4px; word-break:break-all;">
        🔗 {{ item.url[:70] }}{% if item.url|length > 70 %}…{% endif %}
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  {% endfor %}

  <!-- 底部 -->
  <div style="
    margin-top:20px;
    padding-top:14px;
    border-top: 1px solid rgba(255,255,255,0.08);
    font-size:11px;
    color: #555880;
    text-align: center;
  ">
    由 AstrBot · AI 日报插件 生成 · {{ date }} {{ time }}
  </div>
</div>
"""

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _clean_html(text: str) -> str:
    """去除 HTML 标签"""
    clean = re.compile(r"<[^>]+>")
    text = clean.sub("", text)
    for entity, char in [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"'),
        ("&#x27;", "'"), ("&#x2F;", "/"),
    ]:
        text = text.replace(entity, char)
    return text.strip()


def _truncate(text: str, max_len: int = 80) -> str:
    text = text.strip()
    return text[:max_len] + "…" if len(text) > max_len else text


def _is_ai_related(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in HN_AI_KEYWORDS)


# ──────────────────────────────────────────────
# 新闻抓取器
# ──────────────────────────────────────────────

async def _fetch_rss(session: aiohttp.ClientSession, url: str, max_items: int = 5) -> list[dict]:
    """通用 RSS/Atom 抓取"""
    items: list[dict] = []
    headers = {"User-Agent": "Mozilla/5.0 AstrBot-AI-Daily/2.0"}
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning(f"[AI日报] RSS 请求失败 {url}: {resp.status}")
                return items
            text = await resp.text()

        root = ElementTree.fromstring(text)

        if "feed" in root.tag:
            # Atom 格式
            ns = "http://www.w3.org/2005/Atom"
            for entry in root.findall(f"{{{ns}}}entry")[:max_items]:
                title_el = entry.find(f"{{{ns}}}title")
                link_el = entry.find(f"{{{ns}}}link")
                title = title_el.text.strip() if title_el is not None and title_el.text else "无标题"
                link = ""
                if link_el is not None:
                    link = link_el.get("href", "") or (link_el.text or "")
                items.append({"title": _clean_html(title), "url": link})
        else:
            # RSS 2.0 格式
            channel = root.find("channel") or root
            for item in channel.findall("item")[:max_items]:
                title_el = item.find("title")
                link_el = item.find("link")
                title = title_el.text.strip() if title_el is not None and title_el.text else "无标题"
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                items.append({"title": _clean_html(title), "url": link})

    except Exception as e:
        logger.warning(f"[AI日报] 解析 RSS 失败 {url}: {e}")
    return items


async def _fetch_hn(session: aiohttp.ClientSession, max_items: int = 5) -> list[dict]:
    """抓取 Hacker News 并过滤 AI 相关"""
    items: list[dict] = []
    try:
        async with session.get(
            NEWS_SOURCES["hacker_news"]["url"],
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            story_ids: list[int] = await resp.json()

        ai_items: list[dict] = []
        batch = story_ids[:80]
        tasks = [
            session.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                timeout=aiohttp.ClientTimeout(total=8),
            )
            for sid in batch
        ]
        resps = await asyncio.gather(*tasks, return_exceptions=True)
        for r in resps:
            try:
                if isinstance(r, Exception):
                    continue
                async with r as resp:
                    data = await resp.json()
                if data and data.get("title") and _is_ai_related(data["title"]):
                    ai_items.append({
                        "title": data["title"],
                        "url": data.get("url", f"https://news.ycombinator.com/item?id={data['id']}"),
                    })
                    if len(ai_items) >= max_items:
                        break
            except Exception:
                continue
        items = ai_items[:max_items]
    except Exception as e:
        logger.warning(f"[AI日报] HN 抓取失败: {e}")
    return items


async def _fetch_all_news(
    enabled_sources: list[str],
    items_per_source: int = 3,
) -> dict[str, list[dict]]:
    """并发抓取所有来源"""
    result: dict[str, list[dict]] = {}
    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks: dict[str, object] = {}
        for key in enabled_sources:
            src = NEWS_SOURCES.get(key)
            if not src:
                continue
            if src["type"] == "hn_api":
                tasks[key] = _fetch_hn(session, items_per_source)
            elif src["type"] == "rss":
                tasks[key] = _fetch_rss(session, src["url"], items_per_source)

        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, res in zip(tasks.keys(), gathered):
            if isinstance(res, Exception):
                logger.warning(f"[AI日报] 来源 {key} 异常: {res}")
                result[key] = []
            else:
                result[key] = res  # type: ignore
    return result


# ──────────────────────────────────────────────
# 格式化 - 纯文本（发送消息用）
# ──────────────────────────────────────────────

def _format_text(news_data: dict[str, list[dict]], date_str: str, enabled_sources: list[str]) -> str:
    lines = [f"📰 AI 日报 · {date_str}", "=" * 32]
    total = 0
    for key in enabled_sources:
        src = NEWS_SOURCES.get(key)
        if not src:
            continue
        items = news_data.get(key, [])
        if not items:
            continue
        lines.append(f"\n{src['emoji']} 【{src['name']}】")
        for i, item in enumerate(items, 1):
            title = _truncate(item["title"], 70)
            url = item.get("url", "")
            lines.append(f"  {i}. {title}")
            if url:
                lines.append(f"     🔗 {url}")
        total += len(items)
    lines.append("\n" + "=" * 32)
    lines.append(f"📊 共 {total} 条资讯 | 发送 /ai日报帮助 查看更多指令")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 构建 html_render 数据
# ──────────────────────────────────────────────

def _build_render_data(
    news_data: dict[str, list[dict]],
    date_str: str,
    enabled_sources: list[str],
    summary: str = "",
) -> dict:
    sources_data = []
    total = 0
    for key in enabled_sources:
        src = NEWS_SOURCES.get(key)
        if not src:
            continue
        items = news_data.get(key, [])
        if not items:
            continue
        sources_data.append({
            "emoji": src["emoji"],
            "name": src["name"],
            "color": src["color"],
            "items": items,
        })
        total += len(items)
    return {
        "date": date_str,
        "time": datetime.now().strftime("%H:%M"),
        "total": total,
        "source_count": len(sources_data),
        "summary": summary,
        "sources": sources_data,
    }


# ──────────────────────────────────────────────
# 插件主类
# ──────────────────────────────────────────────

class AiDailyPlugin(Star):
    """AI 日报插件 v2 - 多源聚合 + 图片渲染 + AI 摘要 + KV 存储"""

    def __init__(self, context: Context):
        super().__init__(context)

    # ── 配置读取 ──────────────────────────────

    def _cfg(self, key: str, default=None):
        try:
            return self.context.get_config().get(key, default)
        except Exception:
            return default

    def _enabled_sources(self) -> list[str]:
        cfg = self._cfg("enabled_sources", None)
        if cfg and isinstance(cfg, list) and len(cfg) > 0:
            return [s for s in cfg if s in NEWS_SOURCES]
        return [
            "hacker_news", "arxiv_ai", "the_verge_ai",
            "openai_blog", "hugging_face_blog", "venturebeat_ai", "36kr_ai",
        ]

    def _items_per_source(self) -> int:
        return int(self._cfg("items_per_source", 3))

    def _render_image(self) -> bool:
        """是否渲染为图片（默认开启）"""
        return bool(self._cfg("render_image", True))

    def _ai_summary(self) -> bool:
        """是否启用 AI 摘要（默认关闭，需要配置 AI）"""
        return bool(self._cfg("ai_summary", False))

    # ── KV 缓存 ──────────────────────────────

    async def _get_cached_report(self, date_str: str) -> tuple[str | None, dict | None]:
        """从 KV 存储获取缓存（返回文本报告和新闻数据）"""
        try:
            text = await self.get_kv_data(f"{_KV_DAILY_PREFIX}{date_str}", None)
            news = await self.get_kv_data(f"{_KV_NEWS_PREFIX}{date_str}", None)
            return text, news
        except Exception as e:
            logger.warning(f"[AI日报] 读取 KV 缓存失败: {e}")
            return None, None

    async def _save_cache(self, date_str: str, text: str, news_data: dict) -> None:
        """保存今日报告到 KV 存储"""
        try:
            await self.put_kv_data(f"{_KV_DAILY_PREFIX}{date_str}", text)
            await self.put_kv_data(f"{_KV_NEWS_PREFIX}{date_str}", news_data)
        except Exception as e:
            logger.warning(f"[AI日报] 写入 KV 缓存失败: {e}")

    # ── AI 摘要 ──────────────────────────────

    async def _generate_summary(self, event: AstrMessageEvent, news_data: dict[str, list[dict]], enabled: list[str]) -> str:
        """调用 AstrBot 内置 LLM 接口生成 AI 摘要"""
        try:
            umo = event.unified_msg_origin
            provider_id = await self.context.get_current_chat_provider_id(umo=umo)
            if not provider_id:
                return ""

            # 构建新闻文本传给 AI
            headlines = []
            for key in enabled:
                items = news_data.get(key, [])
                for item in items[:2]:
                    headlines.append(f"- {item['title']}")
            if not headlines:
                return ""

            headlines_text = "\n".join(headlines[:20])
            prompt = (
                f"以下是今日 AI 领域的新闻标题列表，请用中文撰写一段 100-150 字的简短摘要，"
                f"提炼今日 AI 领域最重要的趋势和动态，语言简洁精练：\n\n{headlines_text}"
            )

            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )
            return llm_resp.completion_text.strip() if llm_resp else ""
        except Exception as e:
            logger.warning(f"[AI日报] AI 摘要生成失败: {e}")
            return ""

    # ── 核心逻辑 ──────────────────────────────

    async def _get_daily(
        self,
        event: AstrMessageEvent | None = None,
        force_refresh: bool = False,
    ) -> tuple[str, dict]:
        """获取日报文本和新闻数据（带 KV 缓存）"""
        today = date.today().strftime("%Y-%m-%d")

        if not force_refresh:
            cached_text, cached_news = await self._get_cached_report(today)
            if cached_text and cached_news:
                logger.info(f"[AI日报] 命中 KV 缓存 {today}")
                return cached_text, cached_news

        logger.info("[AI日报] 开始抓取新闻...")
        enabled = self._enabled_sources()
        items_n = self._items_per_source()
        news_data = await _fetch_all_news(enabled, items_n)
        report_text = _format_text(news_data, today, enabled)

        await self._save_cache(today, report_text, news_data)
        logger.info(f"[AI日报] 抓取完成，已缓存 {today}")
        return report_text, news_data

    async def _send_daily(
        self,
        event: AstrMessageEvent,
        force_refresh: bool = False,
    ):
        """发送日报（图片或文字，含 AI 摘要）"""
        today = date.today().strftime("%Y-%m-%d")
        enabled = self._enabled_sources()

        report_text, news_data = await self._get_daily(event, force_refresh)

        # AI 摘要（可选）
        summary = ""
        if self._ai_summary() and event is not None:
            yield event.plain_result("🤔 正在生成 AI 摘要...")
            summary = await self._generate_summary(event, news_data, enabled)

        # 渲染为图片或纯文本
        if self._render_image():
            try:
                render_data = _build_render_data(news_data, today, enabled, summary)
                url = await self.html_render(DAILY_HTML_TMPL, render_data)
                yield event.image_result(url)
                return
            except Exception as e:
                logger.warning(f"[AI日报] 图片渲染失败，降级为文字: {e}")

        # 降级：纯文字
        output = report_text
        if summary:
            output = f"✨ AI 摘要：{summary}\n\n{output}"
        yield event.plain_result(output)

    # ── 指令处理 ──────────────────────────────

    @filter.command("ai日报")
    async def cmd_ai_daily(self, event: AstrMessageEvent):
        """获取今日 AI 日报（图片格式）"""
        yield event.plain_result("⏳ 正在获取 AI 日报，请稍候...")
        try:
            async for result in self._send_daily(event):
                yield result
        except Exception as e:
            logger.error(f"[AI日报] 生成日报失败: {e}")
            yield event.plain_result(f"❌ 生成日报失败: {e}")

    @filter.command("ai日报刷新")
    async def cmd_ai_daily_refresh(self, event: AstrMessageEvent):
        """强制刷新今日 AI 日报（清除缓存并重新抓取）"""
        yield event.plain_result("🔄 正在刷新 AI 日报缓存...")
        try:
            async for result in self._send_daily(event, force_refresh=True):
                yield result
        except Exception as e:
            logger.error(f"[AI日报] 刷新失败: {e}")
            yield event.plain_result(f"❌ 刷新失败: {e}")

    @filter.command("ai日报文字")
    async def cmd_ai_daily_text(self, event: AstrMessageEvent):
        """以纯文字格式获取今日 AI 日报"""
        yield event.plain_result("⏳ 正在获取 AI 日报...")
        try:
            report_text, _ = await self._get_daily(event)
            yield event.plain_result(report_text)
        except Exception as e:
            yield event.plain_result(f"❌ 获取失败: {e}")

    @filter.command("ai日报来源")
    async def cmd_ai_daily_sources(self, event: AstrMessageEvent):
        """查看当前启用的新闻来源"""
        enabled = self._enabled_sources()
        lines = ["📡 当前启用的 AI 新闻来源：\n"]
        for i, key in enumerate(enabled, 1):
            src = NEWS_SOURCES.get(key, {})
            lines.append(f"  {i}. {src.get('emoji','📌')} {src.get('name', key)}")
        lines.append(f"\n共 {len(enabled)} 个来源")
        lines.append("💡 可在 WebUI 插件配置中调整来源")
        yield event.plain_result("\n".join(lines))

    @filter.command("ai新闻")
    async def cmd_ai_news_quick(self, event: AstrMessageEvent):
        """快速获取精选 AI 新闻（3源×2条）"""
        yield event.plain_result("⏳ 正在抓取精选 AI 新闻...")
        try:
            quick_sources = ["hacker_news", "the_verge_ai", "openai_blog"]
            news_data = await _fetch_all_news(quick_sources, items_per_source=2)
            today = date.today().strftime("%Y-%m-%d")
            if self._render_image():
                try:
                    render_data = _build_render_data(news_data, today, quick_sources)
                    url = await self.html_render(DAILY_HTML_TMPL, render_data)
                    yield event.image_result(url)
                    return
                except Exception as e:
                    logger.warning(f"[AI日报] 快讯图片渲染失败: {e}")
            yield event.plain_result(_format_text(news_data, today, quick_sources))
        except Exception as e:
            yield event.plain_result(f"❌ 获取失败: {e}")

    @filter.command("arxiv今日")
    async def cmd_arxiv_today(self, event: AstrMessageEvent):
        """获取今日 ArXiv CS.AI 最新论文"""
        yield event.plain_result("⏳ 正在从 ArXiv 获取最新 AI 论文...")
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                items = await _fetch_rss(session, NEWS_SOURCES["arxiv_ai"]["url"], max_items=8)
            if not items:
                yield event.plain_result("❌ 暂时无法获取 ArXiv 数据，请稍后重试")
                return
            today = date.today().strftime("%Y-%m-%d")
            if self._render_image():
                try:
                    news_data = {"arxiv_ai": items}
                    render_data = _build_render_data(news_data, today, ["arxiv_ai"])
                    url = await self.html_render(DAILY_HTML_TMPL, render_data)
                    yield event.image_result(url)
                    return
                except Exception as e:
                    logger.warning(f"[AI日报] ArXiv 图片渲染失败: {e}")
            lines = [f"📄 ArXiv CS.AI 论文 · {today}", "=" * 30]
            for i, item in enumerate(items, 1):
                lines.append(f"\n{i}. {_truncate(item['title'], 80)}")
                if item.get("url"):
                    lines.append(f"   🔗 {item['url']}")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"❌ 获取 ArXiv 数据失败: {e}")

    @filter.command("hn今日ai")
    async def cmd_hn_ai_today(self, event: AstrMessageEvent):
        """获取 Hacker News 今日 AI 热帖"""
        yield event.plain_result("⏳ 正在从 Hacker News 筛选 AI 内容...")
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                items = await _fetch_hn(session, max_items=8)
            if not items:
                yield event.plain_result("❌ 暂时未找到 AI 相关热帖，请稍后重试")
                return
            today = date.today().strftime("%Y-%m-%d")
            if self._render_image():
                try:
                    news_data = {"hacker_news": items}
                    render_data = _build_render_data(news_data, today, ["hacker_news"])
                    url = await self.html_render(DAILY_HTML_TMPL, render_data)
                    yield event.image_result(url)
                    return
                except Exception as e:
                    logger.warning(f"[AI日报] HN 图片渲染失败: {e}")
            lines = [f"🔶 Hacker News AI 精选 · {today}", "=" * 30]
            for i, item in enumerate(items, 1):
                lines.append(f"\n{i}. {_truncate(item['title'], 80)}")
                if item.get("url"):
                    lines.append(f"   🔗 {item['url']}")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"❌ 获取 HN 数据失败: {e}")

    @filter.command("ai日报帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        """显示 AI 日报插件帮助"""
        help_text = """📰 AI 日报插件 v2.0 · 指令列表

【主要指令】
/ai日报         - 获取今日完整 AI 日报（图片）
/ai日报文字     - 以文字格式获取日报
/ai日报刷新     - 强制刷新（重新抓取）
/ai日报来源     - 查看当前启用的来源
/ai日报帮助     - 显示本帮助

【快捷查询】
/ai新闻         - 快速获取精选 AI 新闻
/arxiv今日      - ArXiv 最新 AI 论文（8篇）
/hn今日ai       - Hacker News AI 热帖

【配置项（WebUI）】
• enabled_sources  - 启用的来源列表
• items_per_source - 每源显示条数（默认3）
• render_image     - 是否渲染图片（默认true）
• ai_summary       - 是否启用 AI 摘要（默认false）

📡 支持 10+ 来源：HN · ArXiv · The Verge · MIT TR
   VentureBeat · OpenAI · Google AI · HuggingFace
   少数派 · 36氪 AI"""
        yield event.plain_result(help_text)

    # ── LLM Tool 注册（让 AI 主动调用） ────────

    @filter.llm_tool(name="get_ai_news")
    async def tool_get_ai_news(self, event: AstrMessageEvent) -> str:
        """获取今日最新的 AI 人工智能领域资讯新闻。

        Args:
        """
        try:
            report_text, _ = await self._get_daily(event)
            return report_text
        except Exception as e:
            return f"获取 AI 新闻失败: {e}"

    # ── 卸载清理 ──────────────────────────────

    async def terminate(self):
        logger.info("[AI日报] 插件已卸载")
