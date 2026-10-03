import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape

import feedparser
import requests
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Markets News Dashboard", page_icon="📈", layout="wide")

# ---------- CONFIG: edit freely ----------
REFRESH_MINUTES = 5

FEEDS = {
    "India": {
        "Economic Times": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "Moneycontrol": "https://www.moneycontrol.com/rss/marketreports.xml",
        "Mint": "https://www.livemint.com/rss/markets",
        "Business Standard": "https://www.business-standard.com/rss/markets-106.rss","NDTV Profit": "https://news.google.com/rss/search?q=site:ndtvprofit.com+economy&hl=en-IN&gl=IN&ceid=IN:en","Finshots Markets": "https://finshots.in/markets/rss/","Zerodha Pulse": "https://pulse.zerodha.com/feed.php",
        "BusinessLine": "https://www.thehindubusinessline.com/markets/feeder/default.rss",
    },
    "Global": {
        "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
        "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml","Bloomberg": "https://feeds.bloomberg.com/markets/news.rss","Bloomberg": "https://news.google.com/rss/search?q=site:bloomberg.com+markets&hl=en&gl=US&ceid=US:en", "WSJ Markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "Financial Times": "https://www.ft.com/rss/home",
        "The Economist (Finance)": "https://www.economist.com/finance-and-economics/rss.xml",
        "Investing.com": "https://www.investing.com/rss/news.rss",
        "Seeking Alpha": "https://seekingalpha.com/market_currents.xml",
        "Nikkei Asia": "https://asia.nikkei.com/rss/feed/nar",
        "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    },
}

TICKERS = {
    "Nifty 50": "^NSEI",
    "Sensex": "^BSESN",
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow": "^DJI",
    "FTSE 100": "^FTSE",
    "Nikkei 225": "^N225",
    "Gold": "GC=F",
    "Brent": "BZ=F",
    "USD/INR": "INR=X",
}
# ------------------------------------------

st_autorefresh(interval=REFRESH_MINUTES * 60 * 1000, key="auto_refresh")


def clean(text: str, limit: int = 220) -> str:
    text = unescape(re.sub(r"<[^>]+>", "", text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_feed(source: str, url: str):
    """Returns (source, items, error_message_or_None)."""
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if not parsed.entries:
            return source, items, "loaded, but no entries found (URL may not be an RSS feed)"
        for e in parsed.entries[:30]:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            published = (
                datetime.fromtimestamp(time.mktime(ts), tz=timezone.utc) if ts else None
            )
            items.append(
                {
                    "source": source,
                    "title": clean(e.get("title", ""), 200),
                    "summary": clean(e.get("summary", "")),
                    "link": e.get("link", ""),
                    "published": published,
                }
            )
    except Exception as ex:
        return source, items, f"{type(ex).__name__}: {str(ex)[:150]}"
    return source, items, None


@st.cache_data(ttl=REFRESH_MINUTES * 60, show_spinner="Fetching news…")
def load_news(region: str):
    feeds = FEEDS[region]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda kv: fetch_feed(*kv), feeds.items()))
    status = {src: err for src, items, err in results if err}
    articles = [a for _, items, _ in results for a in items]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    articles.sort(key=lambda a: a["published"] or epoch, reverse=True)
    return articles, status


@st.cache_data(ttl=120)
def load_quote(symbol: str):
    try:
        hist = yf.Ticker(symbol).history(period="5d")["Close"].dropna()
        if len(hist) < 2:
            return None
        last, prev = float(hist.iloc[-1]), float(hist.iloc[-2])
        return last, (last - prev) / prev * 100
    except Exception:
        return None


def time_ago(dt):
    if not dt:
        return ""
    mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins}m ago"
    if mins < 1440:
        return f"{mins // 60}h ago"
    return f"{mins // 1440}d ago"


# ---------- Header ----------
st.title("📈 Markets News Dashboard")
st.caption(
    f"Auto-refreshes every {REFRESH_MINUTES} min · Last loaded "
    f"{datetime.now().strftime('%d %b %Y, %H:%M:%S')}"
)

# ---------- Ticker strip ----------
with ThreadPoolExecutor(max_workers=10) as pool:
    quotes = list(pool.map(load_quote, TICKERS.values()))

for row_start in range(0, len(TICKERS), 5):
    cols = st.columns(5)
    for col, (name, _), q in zip(
        cols,
        list(TICKERS.items())[row_start : row_start + 5],
        quotes[row_start : row_start + 5],
    ):
        if q:
            col.metric(name, f"{q[0]:,.2f}", f"{q[1]:+.2f}%")
        else:
            col.metric(name, "n/a")

st.divider()

# ---------- Sidebar filters ----------
with st.sidebar:
    st.header("Filters")
    query = st.text_input("Search / watchlist keywords", placeholder="e.g. Reliance, RBI, Fed")
    st.caption("Separate multiple keywords with commas. Matches title or snippet.")
    max_items = st.slider("Max headlines per tab", 10, 100, 40, step=10)
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()

keywords = [k.strip().lower() for k in query.split(",") if k.strip()]

# ---------- News tabs ----------
tabs = st.tabs(["🇮🇳 India", "🌍 Global"])
for tab, region in zip(tabs, ["India", "Global"]):
    with tab:
        articles, status = load_news(region)

        sources = list(FEEDS[region].keys())
        chosen = st.multiselect(
            "Sources", sources, default=sources, key=f"src_{region}"
        )

        shown = [
            a
            for a in articles
            if a["source"] in chosen
            and (
                not keywords
                or any(k in (a["title"] + " " + a["summary"]).lower() for k in keywords)
            )
        ][:max_items]

        if status:
            details = "\n".join(f"- **{s}**: {err}" for s, err in status.items())
            st.warning(f"Some sources returned no news:\n{details}")

        if not shown:
            st.info("No headlines match your filters.")

        for a in shown:
            st.markdown(f"**[{a['title']}]({a['link']})**")
            st.caption(f"{a['source']} · {time_ago(a['published'])}")
            if a["summary"]:
                st.write(a["summary"])
            st.divider()

st.caption("Headlines and snippets link to the original publishers. Market data via Yahoo Finance and may be delayed.")
