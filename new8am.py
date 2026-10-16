import os
import time
import feedparser
import requests
from datetime import datetime

# ===== 配置：从环境变量读取 =====
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# OpenRouter 模型（可换成任何 :free 模型）
MODEL = "openrouter/free"

# RSS 源
RSS_FEEDS = [
    # 美股 / 經濟
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://finance.yahoo.com/news/rssindex",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    # AI / 科技
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
]

# 每个源最多取几条
MAX_PER_FEED = 5

# 浏览器 UA，避免被 CNBC 等站点拒绝
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    )
}


def fetch_articles():
    """抓取所有 RSS 源，返回文章列表。"""
    articles = []
    for url in RSS_FEEDS:
        try:
            # feedparser 支持传 request_headers
            feed = feedparser.parse(url, request_headers=HEADERS)
            if not feed.entries:
                print(f"[警告] 无内容: {url}")
                continue
            for entry in feed.entries[:MAX_PER_FEED]:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "") or entry.get("description", "")
                # 去掉 HTML 标签（简单处理）
                summary = _strip_html(summary)[:500]
                if title:
                    articles.append({
                        "title": title,
                        "summary": summary,
                        "source": url,
                    })
            print(f"[OK] {url} -> {len(feed.entries[:MAX_PER_FEED])} 条")
        except Exception as e:
            print(f"[失败] {url}: {e}")
    return articles


def _strip_html(text):
    """极简去 HTML 标签。"""
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def summarize(articles):
    """调用 OpenRouter 生成中文摘要。"""
    if not articles:
        return "今日没有抓取到新闻。"

    # 拼接新闻内容
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. 【{a['title']}】{a['summary']}")
    news_text = "\n".join(lines)

    prompt = f"""你是一位專業的新聞編輯。以下是今日從多個來源抓取的新聞標題與摘要。
請用繁體中文總結今日重點，分成三個部分：

【美股 / 經濟】
【AI / 科技】
【其他值得關注】

要求：
- 每個部分用 bullet points 列出 2-4 條重點
- 只輸出總結內容，不要附任何原文連結、來源名稱或參考資料
- 語言簡潔，像早報一樣
- 如果某部分沒有相關新聞，就寫「今日無重大更新」

新聞內容：
{news_text}
"""

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def send_telegram(text):
    """发送消息到 Telegram。"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram 单条上限 4096 字符，超过就分段
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True,
        }, timeout=30)
        r.raise_for_status()
        time.sleep(1)  # 避免触发限流


def main():
    print(f"=== 開始抓取 {datetime.now()} ===")
    articles = fetch_articles()
    print(f"共抓取 {len(articles)} 條新聞")

    print("=== 調用 OpenRouter 生成摘要 ===")
    digest = summarize(articles)
    print("\n----- 摘要預覽 -----")
    print(digest)
    print("---------------------\n")

    print("=== 發送到 Telegram ===")
    header = f"📰 每日新聞摘要 {datetime.now().strftime('%Y-%m-%d')}\n\n"
    send_telegram(header + digest)
    print("=== 完成 ===")


if __name__ == "__main__":
    main()