"""
AstrBot AI 日报插件 v2.1
- 默认新闻来源全部换为大陆可访问的 AI 媒体（量子位、机器之心、36氪、虎嗅等）
- 海外来源（HN、ArXiv、OpenAI Blog 等）移至可选列表
- 每个来源独立超时 8s，整体抓取上限 25s，避免卡死
- 支持 html_render 图片渲染、KV 持久化缓存、AI 智能摘要、LLM Tool 注册
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
# 分为两组：
#   CN_SOURCES  - 大陆可访问，作为默认来源
#   INT_SOURCES - 国际来源，需要良好网络，可选启用

NEWS_SOURCES: dict[str, dict] = {
    # ── 大陆优先来源 ──────────────────────────
    "qbitai": {
        "name": "量子位",
        "url": "https://www.qbitai.com/feed",
        "type": "rss",
        "emoji": "⚛️",
        "color": "#3b82f6",
        "region": "cn",
    },
    "jiqizhixin": {
        "name": "机器之心",
        "url": "https://www.jiqizhixin.com/rss",
        "type": "rss",
        "emoji": "🧠",
        "color": "#6366f1",
        "region": "cn",
    },
    "36kr_ai": {
        "name": "36氪（AI）",
        "url": "https://36kr.com/feed",
        "type": "rss",
        "emoji": "🚀",
        "color": "#0a66c2",
        "region": "cn",
    },
    "huxiu": {
        "name": "虎嗅",
        "url": "https://www.huxiu.com/rss/0.rss",
        "type": "rss",
        "emoji": "🐯",
        "color": "#f59e0b",
        "region": "cn",
    },
    "ifanr": {
        "name": "爱范儿",
        "url": "https://www.ifanr.com/feed",
        "type": "rss",
        "emoji": "💡",
        "color": "#10b981",
        "region": "cn",
    },
    "geekpark": {
        "name": "极客公园",
        "url": "http://www.geekpark.net/rss",
        "type": "rss",
        "emoji": "🎯",
        "color": "#ef4444",
        "region": "cn",
    },
    "infoq_cn": {
        "name": "InfoQ 中文",
        "url": "https://www.infoq.cn/feed",
        "type": "rss",
        "emoji": "📊",
        "color": "#8b5cf6",
        "region": "cn",
    },
    "solidot": {
        "name": "Solidot",
        "url": "https://solidot.org/index.rss",
        "type": "rss",
        "emoji": "🔩",
        "color": "#64748b",
        "region": "cn",
    },
    "sspai": {
        "name": "少数派",
        "url": "https://sspai.com/feed",
        "type": "rss",
        "emoji": "📱",
        "color": "#d71a1b",
        "region": "cn",
    },
    # ── 国际来源（需要良好网络）────────────────
    "hacker_news": {
        "name": "Hacker News AI精选",
        "url": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "type": "hn_api",
        "emoji": "🔶",
        "color": "#ff6600",
        "region": "intl",
    },
    "arxiv_ai": {
        "name": "ArXiv CS.AI",
        "url": "https://rss.arxiv.org/rss/cs.AI",
        "type": "rss",
        "emoji": "📄",
        "color": "#b31b1b",
        "region": "intl",
    },
    "the_verge_ai": {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "type": "rss",
        "emoji": "🔷",
        "color": "#fa4b18",
        "region": "intl",
    },
    "venturebeat_ai": {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "type": "rss",
        "emoji": "💼",
        "color": "#1a73e8",
        "region": "intl",
    },
    "openai_blog": {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "type": "rss",
        "emoji": "🤖",
        "color": "#10a37f",
        "region": "intl",
    },
    "hugging_face_blog": {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "type": "rss",
        "emoji": "🤗",
        "color": "#ff9d00",
        "region": "intl",
    },
    "mit_tech_review": {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "type": "rss",
        "emoji": "🔬",
        "color": "#8a2be2",
        "region": "intl",
    },
}

# 默认启用的来源（全部为大陆可访问）
DEFAULT_CN_SOURCES = [
    "qbitai",
    "jiqizhixin",
    "36kr_ai",
    "huxiu",
    "ifanr",
    "geekpark",
    "infoq_cn",
]

# HN 关键词过滤
HN_AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "ml",
    "llm", "gpt", "claude", "gemini", "llama", "chatgpt",
    "neural", "deep learning", "transformer", "openai", "anthropic",
    "mistral", "stable diffusion", "midjourney", "diffusion",
    "agent", "rag", "embedding", "vector", "copilot", "model",
    "nvidia", "cuda", "inference", "training", "fine-tuning",
    "hugging face", "pytorch", "tensorflow",
]

# KV 存储 Key 前缀
_KV_DAILY_PREFIX = "ai_daily_report_"
_KV_NEWS_PREFIX = "ai_daily_news_"

# 单源超时（秒）
_SOURCE_TIMEOUT = 8
# 整体抓取超时（秒）
_TOTAL_TIMEOUT = 25

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
    ">
      <div style="font-size:14px; line-height:1.5; color:#dddcf5; font-weight:500;">
        {{ loop.index }}. {{ item.title }}
      </div>
      {% if item.url %}
      <div style="font-size:11px; color:#5a6acb; margin-top:4px; word-break:break-all;">
        🔗 {{ item.url[:75] }}{% if item.url|length > 75 %}…{% endif %}
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
    """去除 HTML 标签及常见实体"""
    text = re.sub(r"<[^>]+>", "", text)
    for entity, char in [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"'),
        ("&#x27;", "'"), ("&#x2F;", "/"), ("&hellip;", "…"),
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

async def _fetch_rss(
    session: aiohttp.ClientSession,
    url: str,
    max_items: int = 5,
) -> list[dict]:
    """通用 RSS/Atom 抓取，单源超时 _SOURCE_TIMEOUT 秒"""
    items: list[dict] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AstrBot-AI-Daily/2.1)",
        "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
    }
    try:
        async with session.get(
            url, headers=headers,
            timeout=aiohttp.ClientTimeout(total=_SOURCE_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                logger.warning(f"[AI日报] HTTP {resp.status} <- {url}")
                return items
            text = await resp.text(errors="replace")

        root = ElementTree.fromstring(text)

        if "feed" in root.tag:
            # Atom 格式
            ns = "http://www.w3.org/2005/Atom"
            for entry in root.findall(f"{{{ns}}}entry")[:max_items]:
                title_el = entry.find(f"{{{ns}}}title")
                link_el = entry.find(f"{{{ns}}}link")
                title = (title_el.text or "无标题").strip() if title_el is not None else "无标题"
                link = ""
                if link_el is not None:
                    link = link_el.get("href", "") or (link_el.text or "")
                items.append({"title": _clean_html(title), "url": link.strip()})
        else:
            # RSS 2.0 格式
            channel = root.find("channel") or root
            for item in channel.findall("item")[:max_items]:
                title_el = item.find("title")
                link_el = item.find("link")
                title = (title_el.text or "无标题").strip() if title_el is not None else "无标题"
                link = (link_el.text or "").strip() if link_el is not None else ""
                items.append({"title": _clean_html(title), "url": link})

    except asyncio.TimeoutError:
        logger.warning(f"[AI日报] 超时 ({_SOURCE_TIMEOUT}s) <- {url}")
    except Exception as e:
        logger.warning(f"[AI日报] 解析失败 {url}: {type(e).__name__}: {e}")
    return items


async def _fetch_hn(
    session: aiohttp.ClientSession,
    max_items: int = 5,
) -> list[dict]:
    """Hacker News API 抓取并过滤 AI 相关"""
    items: list[dict] = []
    try:
        async with session.get(
            NEWS_SOURCES["hacker_news"]["url"],
            timeout=aiohttp.ClientTimeout(total=_SOURCE_TIMEOUT),
        ) as resp:
            story_ids: list[int] = await resp.json()

        ai_items: list[dict] = []
        # 并发取前 60 条详情
        tasks = [
            session.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                timeout=aiohttp.ClientTimeout(total=6),
            )
            for sid in story_ids[:60]
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
                        "url": data.get("url") or f"https://news.ycombinator.com/item?id={data['id']}",
                    })
                    if len(ai_items) >= max_items:
                        break
            except Exception:
                continue
        items = ai_items[:max_items]
    except asyncio.TimeoutError:
        logger.warning(f"[AI日报] HN 超时")
    except Exception as e:
        logger.warning(f"[AI日报] HN 抓取失败: {e}")
    return items


async def _fetch_one_source(
    session: aiohttp.ClientSession,
    key: str,
    items_per_source: int,
) -> tuple[str, list[dict]]:
    """抓取单个来源，出错返回空列表"""
    src = NEWS_SOURCES[key]
    try:
        if src["type"] == "hn_api":
            result = await _fetch_hn(session, items_per_source)
        else:
            result = await _fetch_rss(session, src["url"], items_per_source)
        return key, result
    except Exception as e:
        logger.warning(f"[AI日报] 来源 {key} 异常: {e}")
        return key, []


async def _fetch_all_news(
    enabled_sources: list[str],
    items_per_source: int = 3,
) -> dict[str, list[dict]]:
    """并发抓取所有来源，整体上限 _TOTAL_TIMEOUT 秒"""
    result: dict[str, list[dict]] = {k: [] for k in enabled_sources}
    connector = aiohttp.TCPConnector(limit=12, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            _fetch_one_source(session, key, items_per_source)
            for key in enabled_sources
            if key in NEWS_SOURCES
        ]
        try:
            gathered = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=_TOTAL_TIMEOUT,
            )
            for item in gathered:
                if isinstance(item, Exception):
                    continue
                key, data = item
                result[key] = data
        except asyncio.TimeoutError:
            logger.warning(f"[AI日报] 整体抓取超时 ({_TOTAL_TIMEOUT}s)，返回已有数据")
    return result


# ──────────────────────────────────────────────
# 格式化
# ──────────────────────────────────────────────

def _format_text(
    news_data: dict[str, list[dict]],
    date_str: str,
    enabled_sources: list[str],
) -> str:
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
            lines.append(f"  {i}. {_truncate(item['title'], 70)}")
            if item.get("url"):
                lines.append(f"     🔗 {item['url']}")
        total += len(items)
    lines.append("\n" + "=" * 32)
    lines.append(f"📊 共 {total} 条资讯 | /ai日报帮助 查看更多指令")
    return "\n".join(lines)


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
    """AI 日报插件 v2.1 - 大陆优先多源聚合"""

    def __init__(self, context: Context):
        super().__init__(context)

    # ── 配置 ──────────────────────────────────

    def _cfg(self, key: str, default=None):
        try:
            return self.context.get_config().get(key, default)
        except Exception:
            return default

    def _enabled_sources(self) -> list[str]:
        cfg = self._cfg("enabled_sources", None)
        if cfg and isinstance(cfg, list) and len(cfg) > 0:
            return [s for s in cfg if s in NEWS_SOURCES]
        return list(DEFAULT_CN_SOURCES)

    def _items_per_source(self) -> int:
        return max(1, min(10, int(self._cfg("items_per_source", 3))))

    def _render_image(self) -> bool:
        return bool(self._cfg("render_image", True))

    def _ai_summary(self) -> bool:
        return bool(self._cfg("ai_summary", False))

    # ── KV 缓存 ──────────────────────────────

    async def _get_cached(self, date_str: str) -> tuple[str | None, dict | None]:
        try:
            text = await self.get_kv_data(f"{_KV_DAILY_PREFIX}{date_str}", None)
            news = await self.get_kv_data(f"{_KV_NEWS_PREFIX}{date_str}", None)
            return text, news
        except Exception as e:
            logger.warning(f"[AI日报] KV 读取失败: {e}")
            return None, None

    async def _save_cached(self, date_str: str, text: str, news_data: dict) -> None:
        try:
            await self.put_kv_data(f"{_KV_DAILY_PREFIX}{date_str}", text)
            await self.put_kv_data(f"{_KV_NEWS_PREFIX}{date_str}", news_data)
        except Exception as e:
            logger.warning(f"[AI日报] KV 写入失败: {e}")

    # ── AI 摘要 ──────────────────────────────

    async def _generate_summary(
        self,
        event: AstrMessageEvent,
        news_data: dict[str, list[dict]],
        enabled: list[str],
    ) -> str:
        try:
            umo = event.unified_msg_origin
            provider_id = await self.context.get_current_chat_provider_id(umo=umo)
            if not provider_id:
                return ""
            headlines = []
            for key in enabled:
                for item in news_data.get(key, [])[:2]:
                    headlines.append(f"- {item['title']}")
            if not headlines:
                return ""
            prompt = (
                "以下是今日 AI 人工智能领域新闻标题，请用中文撰写 100-150 字的简短摘要，"
                "提炼今日最重要的趋势和动态，语言简洁：\n\n" + "\n".join(headlines[:20])
            )
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )
            return (llm_resp.completion_text or "").strip() if llm_resp else ""
        except Exception as e:
            logger.warning(f"[AI日报] AI 摘要生成失败: {e}")
            return ""

    # ── 核心逻辑 ──────────────────────────────

    async def _get_daily(
        self,
        event: AstrMessageEvent | None = None,
        force_refresh: bool = False,
    ) -> tuple[str, dict]:
        today = date.today().strftime("%Y-%m-%d")
        if not force_refresh:
            cached_text, cached_news = await self._get_cached(today)
            if cached_text and cached_news:
                logger.info(f"[AI日报] 命中 KV 缓存 {today}")
                return cached_text, cached_news

        logger.info("[AI日报] 开始抓取新闻...")
        enabled = self._enabled_sources()
        news_data = await _fetch_all_news(enabled, self._items_per_source())
        report_text = _format_text(news_data, today, enabled)
        await self._save_cached(today, report_text, news_data)
        logger.info(f"[AI日报] 抓取完成，已缓存 {today}")
        return report_text, news_data

    async def _send_daily(self, event: AstrMessageEvent, force_refresh: bool = False):
        today = date.today().strftime("%Y-%m-%d")
        enabled = self._enabled_sources()

        report_text, news_data = await self._get_daily(event, force_refresh)

        # 统计实际抓取到数据的来源数
        real_sources = sum(1 for k in enabled if news_data.get(k))
        if real_sources == 0:
            yield event.plain_result(
                "⚠️ 所有来源均未能获取到数据，可能是网络问题。\n"
                "请检查 AstrBot 所在服务器的网络连接是否正常，\n"
                "或在 WebUI 配置中调整 enabled_sources。"
            )
            return

        # AI 摘要（可选）
        summary = ""
        if self._ai_summary():
            yield event.plain_result("🤔 正在生成 AI 摘要...")
            summary = await self._generate_summary(event, news_data, enabled)

        # 图片渲染
        if self._render_image():
            try:
                render_data = _build_render_data(news_data, today, enabled, summary)
                url = await self.html_render(DAILY_HTML_TMPL, render_data)
                yield event.image_result(url)
                return
            except Exception as e:
                logger.warning(f"[AI日报] 图片渲染失败，降级为文字: {e}")

        # 纯文字降级
        output = report_text
        if summary:
            output = f"✨ AI 摘要：{summary}\n\n{output}"
        yield event.plain_result(output)

    # ── 指令 ──────────────────────────────────

    @filter.command("ai日报")
    async def cmd_ai_daily(self, event: AstrMessageEvent):
        """获取今日 AI 日报"""
        yield event.plain_result("⏳ 正在抓取今日 AI 日报（大陆来源），请稍候...")
        try:
            async for r in self._send_daily(event):
                yield r
        except Exception as e:
            logger.error(f"[AI日报] 生成日报失败: {e}")
            yield event.plain_result(f"❌ 生成日报失败: {e}")

    @filter.command("ai日报刷新")
    async def cmd_ai_daily_refresh(self, event: AstrMessageEvent):
        """强制刷新今日 AI 日报（清除缓存重新抓取）"""
        yield event.plain_result("🔄 正在清除缓存并重新抓取...")
        try:
            async for r in self._send_daily(event, force_refresh=True):
                yield r
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
            region = "🇨🇳" if src.get("region") == "cn" else "🌐"
            lines.append(f"  {i}. {region} {src.get('emoji','')} {src.get('name', key)}")
        lines.append(f"\n共 {len(enabled)} 个来源")
        lines.append("💡 可在 WebUI 插件配置中调整（支持的 key 见 README）")
        yield event.plain_result("\n".join(lines))

    @filter.command("ai新闻")
    async def cmd_ai_news_quick(self, event: AstrMessageEvent):
        """快速获取精选 AI 新闻（量子位+36氪+极客公园，每源2条）"""
        yield event.plain_result("⏳ 正在抓取精选 AI 新闻...")
        try:
            quick_sources = ["qbitai", "36kr_ai", "geekpark"]
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

    @filter.command("量子位")
    async def cmd_qbitai(self, event: AstrMessageEvent):
        """获取量子位最新 AI 资讯"""
        yield event.plain_result("⏳ 正在获取量子位最新资讯...")
        try:
            news_data = await _fetch_all_news(["qbitai"], items_per_source=8)
            today = date.today().strftime("%Y-%m-%d")
            if self._render_image():
                try:
                    render_data = _build_render_data(news_data, today, ["qbitai"])
                    url = await self.html_render(DAILY_HTML_TMPL, render_data)
                    yield event.image_result(url)
                    return
                except Exception:
                    pass
            yield event.plain_result(_format_text(news_data, today, ["qbitai"]))
        except Exception as e:
            yield event.plain_result(f"❌ 获取失败: {e}")

    @filter.command("机器之心")
    async def cmd_jiqizhixin(self, event: AstrMessageEvent):
        """获取机器之心最新 AI 资讯"""
        yield event.plain_result("⏳ 正在获取机器之心最新资讯...")
        try:
            news_data = await _fetch_all_news(["jiqizhixin"], items_per_source=8)
            today = date.today().strftime("%Y-%m-%d")
            if self._render_image():
                try:
                    render_data = _build_render_data(news_data, today, ["jiqizhixin"])
                    url = await self.html_render(DAILY_HTML_TMPL, render_data)
                    yield event.image_result(url)
                    return
                except Exception:
                    pass
            yield event.plain_result(_format_text(news_data, today, ["jiqizhixin"]))
        except Exception as e:
            yield event.plain_result(f"❌ 获取失败: {e}")

    @filter.command("hn今日ai")
    async def cmd_hn_ai_today(self, event: AstrMessageEvent):
        """获取 Hacker News AI 精选（需要良好网络）"""
        yield event.plain_result("⏳ 正在获取 HN AI 热帖（需要访问国际网络）...")
        try:
            news_data = await _fetch_all_news(["hacker_news"], items_per_source=8)
            today = date.today().strftime("%Y-%m-%d")
            items = news_data.get("hacker_news", [])
            if not items:
                yield event.plain_result("❌ 未能获取 HN 数据，请检查网络或稍后再试")
                return
            if self._render_image():
                try:
                    render_data = _build_render_data(news_data, today, ["hacker_news"])
                    url = await self.html_render(DAILY_HTML_TMPL, render_data)
                    yield event.image_result(url)
                    return
                except Exception:
                    pass
            yield event.plain_result(_format_text(news_data, today, ["hacker_news"]))
        except Exception as e:
            yield event.plain_result(f"❌ 获取失败: {e}")

    @filter.command("ai日报帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        """显示 AI 日报插件帮助"""
        help_text = """📰 AI 日报插件 v2.1 · 帮助

【主要指令】
/ai日报         - 获取今日完整 AI 日报（图片）
/ai日报文字     - 以文字格式获取日报
/ai日报刷新     - 强制刷新缓存重新抓取
/ai日报来源     - 查看当前启用的来源
/ai日报帮助     - 显示本帮助

【快捷查询】
/ai新闻         - 精选快讯（量子位+36氪+极客公园）
/量子位         - 量子位最新 AI 资讯
/机器之心       - 机器之心最新 AI 资讯
/hn今日ai       - HN AI 热帖（需国际网络）

【🇨🇳 大陆默认来源（9个）】
⚛️ 量子位 | 🧠 机器之心 | 🚀 36氪
🐯 虎嗅   | 💡 爱范儿   | 🎯 极客公园
📊 InfoQ  | 🔩 Solidot  | 📱 少数派

【🌐 可选国际来源（需配置启用）】
hacker_news / arxiv_ai / the_verge_ai
venturebeat_ai / openai_blog / hugging_face_blog / mit_tech_review

【WebUI 配置项】
• enabled_sources  - 来源 key 列表
• items_per_source - 每源条数（默认3）
• render_image     - 是否渲染图片（默认true）
• ai_summary       - 是否 AI 摘要（默认false）"""
        yield event.plain_result(help_text)

    # ── LLM Tool ──────────────────────────────

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

    async def terminate(self):
        logger.info("[AI日报] 插件已卸载")
