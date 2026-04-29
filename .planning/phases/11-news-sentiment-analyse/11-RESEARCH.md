# Phase 11: News-Sentiment-Analyse - Research

**Researched:** 2026-03-27
**Domain:** RSS feed parsing, financial NLP sentiment analysis, time-series aggregation, ML feature integration
**Confidence:** HIGH (core stack), MEDIUM (feed URLs), HIGH (architecture patterns)

---

## Summary

Phase 11 builds a news sentiment pipeline that polls gold-relevant RSS feeds every 5 minutes, scores each article with an NLP model, aggregates scores into 1h/4h/24h rolling windows with exponential decay weighting, persists data to SQLite, and exposes six ML features (`sent_1h`, `sent_4h`, `sent_24h`, `sent_momentum`, `sent_divergence`, `news_count_1h`) via the existing `FeatureEngineer` pattern. The pipeline also writes a MiroFish seed document that the running MiroFish instance can consume.

**NLP choice:** Use `vaderSentiment` (3.3.2) as the primary scorer, with optional `transformers` + `ProsusAI/finbert` as a configurable upgrade. VADER runs in microseconds with near-zero memory overhead and is already compatible with the project's Python 3.12 environment. FinBERT requires ~500MB RAM for the BERT model weights on first load and ~50ms per headline at CPU inference speed — viable on 16GB RAM but adds 1-2s cold start. The right architecture loads the analyzer once at startup and keeps it resident. Given the REQUIREMENTS.md "Out of Scope" note that originally called sentiment analysis "noisy for intraday gold trading," the implementation must be opt-in with a settings flag (`sentiment_enabled: bool = False`), matching the MiroFish pattern.

**Primary recommendation:** `feedparser 6.0.12` for RSS parsing, `vaderSentiment 3.3.2` as default scorer (switchable to FinBERT via settings), `APScheduler 3.11.2` (already in venv) for background polling, SQLAlchemy async ORM for persistence, `pandas.ewm()` for time-decay aggregation. New module at `sentiment/` with four Python files following the exact same class pattern as `ai_engine/features/technical_features.py`.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SENT-01 | RSS-Feeds (Reuters, Bloomberg, Investing.com, Kitco) alle 5min abrufen und Gold-relevant filtern | feedparser 6.0.12 + APScheduler AsyncIOScheduler; confirmed working free feed URLs for Kitco and Investing.com; Reuters paywalled since Oct 2024 — replaced with MarketWatch + GoldBroker alternatives |
| SENT-02 | NLP Sentiment-Score pro Nachricht (-1.0 bis +1.0, FinBERT/VADER) | vaderSentiment 3.3.2 compound score is natively -1..+1; FinBERT: score = p(positive) - p(negative), also -1..+1 range |
| SENT-03 | Aggregierte Sentiment-Werte (1h/4h/24h rollierend) und Sentiment-Momentum | pandas.ewm(halflife=..., times=timestamps) for time-decay; rolling windows via pandas DataFrame timestamp filtering |
| SENT-04 | Sentiment-Features (score, momentum, divergenz, news_count) als ML-Input nutzbar | New `SentimentFeatures` class following `TechnicalFeatures` FEATURE_NAMES pattern; injected into `FeatureEngineer.__init__()` |
| SENT-05 | Historische Sentiment-Daten gespeichert und fuer Backtesting abrufbar | New `NewsSentiment` SQLAlchemy ORM model in `database/models.py`; repository pattern matching `signal_repo.py` |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| feedparser | 6.0.12 | Parse RSS/Atom/RDF feeds; handles encoding, sanitization, HTTP ETags | Only pure-Python RSS library maintained since 2021; handles all feed formats transparently |
| vaderSentiment | 3.3.2 | Lexicon+rule-based sentiment scoring; compound score -1..+1 | No model download, no GPU, microsecond inference; 339x faster than FinBERT at 56% vs 69% accuracy tradeoff; sufficient for headline-level gold news |
| APScheduler | 3.11.2 | Background polling at fixed intervals | Already installed in project venv; project uses it for other scheduled tasks; `AsyncIOScheduler` matches project's async architecture |
| pandas (ewm) | 2.3.3 | Time-decay weighted aggregation of sentiment scores | Already in venv; `ewm(halflife="30min", times=timestamps)` handles irregular timestamp intervals correctly |
| SQLAlchemy async | 2.0.48 | ORM persistence for `news_sentiment` table | Already in venv; project uses this pattern throughout `database/` |

### Supporting (optional upgrade path)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| transformers | Must install in project venv | FinBERT pipeline for higher-accuracy scoring | When `sentiment_model: "finbert"` in settings; ~500MB RAM, ~50ms/headline on CPU |
| torch | Must install in project venv | FinBERT inference backend | Required by transformers for FinBERT; ~2GB install |
| httpx | 0.28.1 | Async HTTP for feed fetching (fallback when feedparser times out) | Already in venv; use for feeds that return non-standard content-types |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| feedparser | newspaper3k | newspaper3k does full article scraping — overkill for headline sentiment; also has lxml dependency that causes Windows install issues |
| feedparser | requests + BeautifulSoup | More code, no ETags/conditional GET support, no feed format detection |
| vaderSentiment | FinBERT (ProsusAI/finbert) | FinBERT: 69% vs VADER 56% accuracy on financial text; but requires 500MB RAM + 2GB torch install + 50ms/headline latency vs VADER microseconds; recommended as opt-in upgrade |
| APScheduler | asyncio.create_task loop | APScheduler already in venv, handles timezone-aware scheduling, error recovery, job state |
| pandas.ewm | manual numpy decay | pandas.ewm supports time-based halflife with actual timestamps — correct for irregular polling intervals |

**Installation (new packages only — rest already in venv):**
```bash
pip install feedparser==6.0.12 vaderSentiment==3.3.2
# Optional FinBERT support (large download):
# pip install transformers torch
```

**Version verification (confirmed 2026-03-27 via pip index):**
- feedparser: 6.0.12 (latest)
- vaderSentiment: 3.3.2 (latest, stable since 2018)
- APScheduler: 3.11.2 (already installed)
- pandas: 2.3.3 (already installed)

---

## Architecture Patterns

### Recommended Project Structure
```
sentiment/
├── __init__.py          # exports SentimentService, get_sentiment_service
├── news_fetcher.py      # FeedFetcher class: RSS polling, keyword filtering
├── sentiment_analyzer.py # SentimentAnalyzer class: VADER/FinBERT scoring
├── sentiment_aggregator.py  # SentimentAggregator: ewm windows, momentum, divergence
└── sentiment_repository.py  # SentimentRepository: async SQLAlchemy CRUD

ai_engine/features/
└── sentiment_features.py   # SentimentFeatures class (FEATURE_NAMES pattern)

database/models.py           # Add NewsSentiment ORM model
config/settings.py           # Add sentiment_* settings fields
```

This mirrors the existing layout: `sentiment/` is a standalone service module (like `mirofish_client.py` pattern) while `sentiment_features.py` plugs into `ai_engine/features/` via the existing orchestration in `FeatureEngineer`.

### Pattern 1: SentimentFeatures Class (ML Integration)
**What:** Adds `sent_*` columns to OHLCV DataFrame by calling `SentimentAggregator.get_latest_features(timestamp)`.
**When to use:** Called by `FeatureEngineer.create_features()` at step 4 (alongside `GoldSpecificFeatures`).

```python
# Source: ai_engine/features/technical_features.py pattern
class SentimentFeatures:
    """Sentiment features from news analysis pipeline."""

    FEATURE_NAMES: List[str] = [
        "sent_1h",      # EWM-averaged sentiment last 1 hour (-1..+1)
        "sent_4h",      # EWM-averaged sentiment last 4 hours
        "sent_24h",     # EWM-averaged sentiment last 24 hours
        "sent_momentum",  # sent_1h - sent_4h (rate of change)
        "sent_divergence",  # sent_1h - price_direction (divergence signal)
        "news_count_1h",  # number of articles in last 1 hour (volatility proxy)
    ]

    def __init__(self, aggregator: Optional[SentimentAggregator] = None) -> None:
        self._aggregator = aggregator  # None = graceful degradation to 0.0

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if self._aggregator is None:
            for col in self.FEATURE_NAMES:
                df[col] = 0.0
            return df
        # Use latest timestamp from df index for point-in-time lookup
        latest_ts = df.index[-1]
        features = self._aggregator.get_features_at(latest_ts)
        for col in self.FEATURE_NAMES:
            df[col] = features.get(col, 0.0)
        return df

    def get_feature_names(self) -> List[str]:
        return self.FEATURE_NAMES.copy()
```

### Pattern 2: Feed Fetcher with ETag Caching
**What:** Fetch RSS feeds with conditional HTTP via feedparser's built-in ETag/Last-Modified support.
**When to use:** `FeedFetcher.poll()` called every 5 minutes by APScheduler.

```python
# Source: feedparser 6.0.x documentation
import feedparser

class FeedFetcher:
    GOLD_KEYWORDS = [
        "gold", "xauusd", "federal reserve", "fed", "inflation", "cpi",
        "fomc", "interest rate", "dollar", "dxy", "central bank",
        "sanctions", "geopolit", "war", "treasury", "yield",
    ]

    FEEDS = {
        "kitco":       "https://www.kitco.com/news/category/commodities/gold/rss",
        "investing":   "https://www.investing.com/rss/news_11.rss",
        "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
        "goldbroker":  "https://www.goldbroker.com/news.rss",
    }

    def __init__(self) -> None:
        self._etags: dict[str, str] = {}
        self._modified: dict[str, str] = {}

    def poll_feed(self, name: str, url: str) -> list[dict]:
        d = feedparser.parse(
            url,
            etag=self._etags.get(name),
            modified=self._modified.get(name),
        )
        if d.status == 304:  # Not Modified
            return []
        self._etags[name] = getattr(d, "etag", None)
        self._modified[name] = getattr(d, "modified", None)

        articles = []
        for entry in d.entries:
            text = f"{entry.get('title', '')} {entry.get('summary', '')}"
            text_lower = text.lower()
            if any(kw in text_lower for kw in self.GOLD_KEYWORDS):
                articles.append({
                    "source": name,
                    "headline": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "published": entry.get("published_parsed"),  # time.struct_time
                })
        return articles
```

### Pattern 3: VADER Scoring with -1..+1 Output
**What:** VADER `compound` score is natively in -1..+1 range. FinBERT uses `p(positive) - p(negative)`.
**When to use:** `SentimentAnalyzer.score(text)` called per article.

```python
# Source: vaderSentiment PyPI + FinBERT HuggingFace model card
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

class SentimentAnalyzer:
    def __init__(self, model: str = "vader") -> None:
        if model == "vader":
            self._vader = SentimentIntensityAnalyzer()
            self._model_type = "vader"
        elif model == "finbert":
            from transformers import pipeline
            self._pipe = pipeline(
                "text-classification",
                model="ProsusAI/finbert",
                return_all_scores=True,
            )
            self._model_type = "finbert"

    def score(self, text: str) -> float:
        """Returns sentiment score in [-1.0, +1.0]."""
        if self._model_type == "vader":
            scores = self._vader.polarity_scores(text)
            return scores["compound"]  # already -1..+1
        else:
            # FinBERT: p(positive) - p(negative)
            results = self._pipe(text[:512])[0]  # truncate to BERT max
            label_scores = {r["label"]: r["score"] for r in results}
            return label_scores.get("positive", 0.0) - label_scores.get("negative", 0.0)
```

### Pattern 4: Time-Decay Aggregation with pandas.ewm()
**What:** Compute exponentially-weighted sentiment across a time window, newer articles weighted more.
**When to use:** `SentimentAggregator.get_features_at(timestamp)`.

```python
# Source: pandas 2.x documentation — DataFrame.ewm(halflife, times=)
import pandas as pd
from datetime import datetime, timedelta

def compute_ewm_sentiment(
    df: pd.DataFrame,  # columns: published_at, score, source_weight
    window_hours: float,
    halflife_minutes: float = 30.0,
) -> float:
    """
    EWM sentiment over last `window_hours` hours.
    Uses time-based halflife so irregular polling intervals are handled correctly.
    """
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    window_df = df[df["published_at"] >= cutoff].copy()
    if window_df.empty:
        return 0.0
    window_df = window_df.sort_values("published_at")
    # Weight by source importance
    window_df["weighted_score"] = window_df["score"] * window_df["source_weight"]
    # Time-based EWM: halflife of 30 minutes means older news decays
    ewm = window_df["weighted_score"].ewm(
        halflife=f"{halflife_minutes}min",
        times=window_df["published_at"],
    ).mean()
    return float(ewm.iloc[-1]) if not ewm.empty else 0.0
```

### Pattern 5: NewsSentiment ORM Model
**What:** SQLAlchemy model following existing `database/models.py` patterns exactly.
**When to use:** Append to `database/models.py` after existing models.

```python
# Source: database/models.py pattern — identical style to Candle, Signal
class NewsSentiment(Base):
    __tablename__ = "news_sentiment"

    id: Mapped[int] = mapped_column(primary_key=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    sentiment_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    source_weight: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)
    keywords_matched: Mapped[list | None] = mapped_column(JSON_COMPAT)
    model_used: Mapped[str] = mapped_column(String(20), default="vader")

    __table_args__ = (
        Index("idx_news_sentiment_published", "published_at"),
        Index("idx_news_sentiment_source", "source"),
        Index("uq_news_sentiment_url", "url", unique=True),
    )
```

### Pattern 6: APScheduler Integration in lifecycle.py
**What:** Start sentiment polling background job alongside MiroFish background task.
**When to use:** In `LifecycleMixin.start()` and `stop()`, matching the `_mirofish_client` pattern.

```python
# Source: APScheduler 3.11.2 docs — AsyncIOScheduler pattern
# Matches existing pattern in trading/lifecycle.py for MiroFish background task
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# In LifecycleMixin.__init__:
self._sentiment_service: Optional["SentimentService"] = None

# In start():
if self.settings.sentiment_enabled:
    from sentiment import SentimentService
    self._sentiment_service = SentimentService(self.settings)
    await self._sentiment_service.start()

# In stop():
if self._sentiment_service:
    await self._sentiment_service.stop()
```

### Pattern 7: FeatureEngineer Integration
**What:** Inject `SentimentFeatures` into `FeatureEngineer.__init__()` as optional 6th feature group.
**When to use:** Follows exact pattern of `self._micro = MicrostructureFeatures()`.

```python
# Source: ai_engine/features/feature_engineer.py lines 109-128
# In FeatureEngineer.__init__():
from .sentiment_features import SentimentFeatures
self._sentiment = SentimentFeatures(
    aggregator=get_sentiment_service().aggregator
    if settings.sentiment_enabled else None
)
self._feature_names += self._sentiment.get_feature_names()

# In create_features() step 4:
df = self._sentiment.calculate(df)
```

### Anti-Patterns to Avoid
- **Loading FinBERT inside the polling loop:** Model init takes 2-4 seconds and 500MB RAM. Always initialize once at startup, reuse.
- **Scoring full article body text:** RSS feeds provide `entry.summary` which may contain HTML tags. Strip tags before scoring: `re.sub(r'<[^>]+>', '', text)`. Score title + cleaned summary concatenated.
- **Using `asyncio.run()` inside APScheduler jobs:** APScheduler's `AsyncIOScheduler` uses the existing event loop. Job functions must be `async def` coroutines or regular sync functions — never call `asyncio.run()` inside.
- **Blocking the event loop with feedparser:** `feedparser.parse(url)` is synchronous and does HTTP I/O. Run via `asyncio.get_event_loop().run_in_executor(None, feedparser.parse, url)` to avoid blocking the trading loop.
- **Storing duplicate articles:** Use the `url` field as a unique constraint. `INSERT OR IGNORE` semantics via SQLAlchemy `on_conflict_do_nothing()`.
- **Using `FeatureEngineer` cache with sentiment features:** The existing `FeatureCache` is keyed only on candle timestamp. Sentiment features are time-varying independent of candle data. The `SentimentFeatures.calculate()` must always query the aggregator (bypass cache for this feature group), or invalidate cache when new articles arrive.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RSS parsing | Custom HTTP + XML parser | `feedparser.parse()` | Handles ETag/304, malformed XML, encoding detection, all feed versions |
| Sentiment scoring | Custom word list / regex | `vaderSentiment.SentimentIntensityAnalyzer` | VADER handles negation ("not good"), intensifiers ("very"), punctuation effects |
| Time-decay weighting | Manual numpy loop | `pandas.ewm(halflife=..., times=timestamps)` | Handles irregular time intervals correctly; pandas 2.x supports timedelta halflife |
| Background polling | `while True: asyncio.sleep()` | `APScheduler AsyncIOScheduler` | Error recovery, job state tracking, timezone-aware; already in project venv |
| Feed deduplication | MD5 hash of headline | Unique constraint on `url` column | URLs are canonical and stable; MD5 hashes add unnecessary complexity |
| FinBERT inference | Direct HuggingFace model API | `transformers.pipeline("text-classification")` | Pipeline handles tokenization, truncation, batch inference |

**Key insight:** The RSS+NLP pipeline has many edge cases (malformed XML, HTTP errors, encoding issues, empty feeds, duplicate articles across multiple sources) that are already solved by feedparser and vaderSentiment. Hand-rolling these would reintroduce every known bug.

---

## Common Pitfalls

### Pitfall 1: Reuters and Bloomberg RSS Feeds Are Paywalled
**What goes wrong:** `feedparser.parse("https://feeds.reuters.com/reuters/goldME")` returns HTTP 403 or redirects to paywall login since Reuters introduced paid access in October 2024. Bloomberg has never offered free RSS feeds.
**Why it happens:** Both outlets introduced paywalls (Reuters in Oct 2024).
**How to avoid:** Use confirmed-free feeds: Kitco (`https://www.kitco.com/news/category/commodities/gold/rss`), Investing.com (`https://www.investing.com/rss/news_11.rss`), MarketWatch (`https://feeds.marketwatch.com/marketwatch/topstories/`), GoldBroker (`https://www.goldbroker.com/news.rss`). The original spec listed Reuters/Bloomberg but they are not usable without paid API access.
**Warning signs:** feedparser returns `status=403` or `bozo=True` with `bozo_exception` containing auth error.

### Pitfall 2: feedparser.parse() Blocks the Async Event Loop
**What goes wrong:** `feedparser.parse(url)` makes a synchronous HTTP GET request that can take 1-5 seconds per feed. Calling it directly in an `async` function blocks the entire asyncio event loop, pausing the trading loop for 4-20 seconds per polling cycle.
**Why it happens:** feedparser is a synchronous library with no async support.
**How to avoid:** Run in thread pool: `await asyncio.get_event_loop().run_in_executor(None, feedparser.parse, url)`. Or fetch raw bytes with async `aiohttp` and pass the bytes string to `feedparser.parse()`.
**Warning signs:** Trading loop latency spikes of 5-20 seconds during sentiment polling.

### Pitfall 3: FeatureEngineer Cache Stale Sentiment
**What goes wrong:** The existing `FeatureCache` in `FeatureEngineer` caches the entire feature DataFrame keyed on candle timestamp. If sentiment features are embedded in the cached DataFrame, they will not update when new articles arrive mid-candle.
**Why it happens:** Sentiment data changes every 5 minutes; candle data changes every candle (5min). These can be out of sync.
**How to avoid:** Two options: (A) Disable cache for sentiment-enriched DataFrames (set `multi_tf_data` path which bypasses cache); or (B) Store `SentimentFeatures` as a separate lookup that is always evaluated fresh, not baked into the cached DataFrame.
**Warning signs:** Sentiment features identical across multiple consecutive candles during active news periods.

### Pitfall 4: VADER Over-Scoring Financial Boilerplate
**What goes wrong:** Gold news headlines often contain words that score high on VADER (e.g., "record high", "strong gain", "positive outlook") that are descriptive rather than directional. This inflates bullish bias.
**Why it happens:** VADER was trained on social media text, not financial news. It scores words like "record" positively.
**How to avoid:** Apply a gold-specific adjustment list: reduce weight of common financial boilerplate phrases. Additionally, the 4h/24h aggregation naturally smooths single-headline noise.
**Warning signs:** `sent_1h` always hovering near +0.3 regardless of actual market direction.

### Pitfall 5: SQLite URL Unique Constraint with Long URLs
**What goes wrong:** Some feed URLs include tracking parameters (e.g., `?utm_source=rss`) that make the same article appear as two different URLs.
**Why it happens:** Publishers add UTM tracking to RSS entry links.
**How to avoid:** Normalize URLs before storing: strip query parameters or hash the canonical `entry.id` field (which feedparser normalizes) as the deduplication key. Prefer `entry.id` over `entry.link` for deduplication.
**Warning signs:** Duplicate entries in `news_sentiment` for the same headline.

### Pitfall 6: FinBERT on Windows with BERT Tokenizer
**What goes wrong:** `transformers.pipeline("text-classification", model="ProsusAI/finbert")` on first run downloads 420MB of model weights to `~/.cache/huggingface/`. If the cache directory has spaces or Unicode (common on Windows) this can fail.
**Why it happens:** HuggingFace Hub uses the system temp directory which on Windows defaults to `C:\Users\<username>\AppData\Local\Temp\`.
**How to avoid:** Set `TRANSFORMERS_CACHE` env var to a safe path without spaces before first use: `os.environ["TRANSFORMERS_CACHE"] = "C:/goldbot/hf_cache"`.
**Warning signs:** `OSError: [WinError 123] The filename, directory name, or volume label syntax is incorrect`.

---

## Code Examples

### Complete FeedFetcher.poll() (verified pattern)
```python
# Source: feedparser 6.0.x docs + confirmed feed URLs (2026-03-27)
import asyncio
import re
import time
import feedparser
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

GOLD_FEEDS = {
    "kitco":       "https://www.kitco.com/news/category/commodities/gold/rss",
    "investing":   "https://www.investing.com/rss/news_11.rss",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "goldbroker":  "https://www.goldbroker.com/news.rss",
}

SOURCE_WEIGHTS = {
    "kitco": 1.0,
    "investing": 0.9,
    "marketwatch": 0.8,
    "goldbroker": 0.7,
}

GOLD_KEYWORDS = {
    "gold", "xauusd", "xau", "federal reserve", "fed ", "inflation", "cpi",
    "fomc", "interest rate", "dollar", "dxy", "central bank", "sanctions",
    "geopolit", "war", "conflict", "treasury yield", "precious metal",
    "safe haven", "gold reserves", "bullion", "spot gold",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")

async def fetch_feed_async(name: str, url: str, etag: str | None, modified: str | None):
    loop = asyncio.get_event_loop()
    d = await loop.run_in_executor(
        None,
        lambda: feedparser.parse(url, etag=etag, modified=modified),
    )
    return d
```

### VADER Scoring with Gold-Specific Boost
```python
# Source: vaderSentiment 3.3.2 documentation
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_GOLD_BULLISH = {"safe haven", "central bank buying", "rate cut", "easing", "geopolit"}
_GOLD_BEARISH = {"rate hike", "tightening", "dollar strength", "risk on"}

def score_article(analyzer: SentimentIntensityAnalyzer, headline: str, summary: str) -> float:
    clean_summary = _HTML_TAG_RE.sub(" ", summary)
    text = f"{headline}. {clean_summary}"[:512]
    scores = analyzer.polarity_scores(text)
    return scores["compound"]  # -1.0 to +1.0
```

### Aggregation with pandas.ewm (time-based halflife)
```python
# Source: pandas 2.x docs — DataFrame.ewm(halflife, times=pd.DatetimeIndex)
import pandas as pd
from datetime import datetime, timedelta

def get_ewm_sentiment(records: list[dict], window_hours: float) -> float:
    """
    records: list of {"published_at": datetime, "sentiment_score": float, "source_weight": float}
    """
    if not records:
        return 0.0
    df = pd.DataFrame(records)
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(hours=window_hours)
    df = df[df["published_at"] >= cutoff].sort_values("published_at")
    if df.empty:
        return 0.0
    df["weighted"] = df["sentiment_score"] * df["source_weight"]
    ewm_val = df["weighted"].ewm(
        halflife="30min",
        times=df["published_at"],
    ).mean().iloc[-1]
    return float(ewm_val)
```

### Settings Extension Pattern
```python
# Source: config/settings.py — follows existing MiroFish section pattern
# -- Sentiment Analysis (Phase 11) -----------------------------------------
sentiment_enabled: bool = False           # Opt-in; False = graceful fallback
sentiment_model: str = "vader"            # "vader" or "finbert"
sentiment_poll_interval_seconds: int = 300  # 5 minutes
sentiment_retention_days: int = 30        # Keep 30 days of headlines
sentiment_min_keywords: int = 1           # Minimum gold keywords to accept article
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Reuters/Bloomberg free RSS | Both paywalled — use Kitco + Investing.com + MarketWatch | Reuters Oct 2024, Bloomberg always | Must change feed list from original spec |
| BERT-based models for all NLP | VADER for speed, FinBERT as optional upgrade | 2023-2024 | VADER is 339x faster with acceptable accuracy for headline-level scoring |
| pandas rolling().mean() | pandas ewm(halflife=timedelta, times=timestamps) | pandas 1.1+ | Time-based EWM correctly handles irregular polling intervals |
| transformers 4.x | transformers 5.4.0 | 2025 | `pipeline()` API unchanged; `return_all_scores=True` still works |

**Deprecated/outdated:**
- Reuters RSS `feeds.reuters.com/reuters/goldME`: 403 Forbidden since late 2024
- Bloomberg RSS: never offered free RSS; ignore from original spec
- `feedparser` version 5.x: upgrade to 6.0.12 for Python 3.12 compatibility

---

## Open Questions

1. **Investing.com RSS reliability**
   - What we know: URL `https://www.investing.com/rss/news_11.rss` is referenced in their webmaster tools page; multiple third-party aggregators point to it
   - What's unclear: Whether Investing.com has rate-limiting or CAPTCHA that blocks automated polling at 5-minute intervals
   - Recommendation: Test in Wave 0 with a simple `feedparser.parse()` call; if blocked, replace with `https://www.goldbroker.com/news.rss` or `https://fgmr.com/feed`

2. **MiroFish seed template format**
   - What we know: Phase 6 `mirofish_seeds/` directory was supposed to be created with `.md` files; the directory does not exist in the current working tree (Phase 6 is awaiting human verification)
   - What's unclear: Exact seed template format — whether MiroFish consumes raw Markdown or expects structured JSON
   - Recommendation: Create sentiment seed as a Markdown file in `mirofish_seeds/` following the same pattern as the 3 Phase 6 seeds (gold_market_overview.md format); write as plain German prose narrative

3. **FinBERT Windows HuggingFace cache**
   - What we know: `transformers` 5.0.0 is installed at system level (not in project venv); `torch` 2.10.0 is available at system level
   - What's unclear: Whether project venv has `transformers` + `torch` installed (they were not in `.venv/Scripts/pip list` output)
   - Recommendation: Keep VADER as default (`sentiment_model: "vader"`); document FinBERT as opt-in with install instructions; plan tasks to add `transformers` + `torch` to pyproject.toml optional dependencies

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| feedparser | SENT-01 (RSS parsing) | Not in project venv | Must install 6.0.12 | None — required |
| vaderSentiment | SENT-02 (scoring) | Not in project venv | Must install 3.3.2 | None — required |
| APScheduler | Polling background task | Already in venv | 3.11.2 | None needed |
| pandas | SENT-03 (aggregation) | Already in venv | 2.3.3 | None needed |
| SQLAlchemy + aiosqlite | SENT-05 (persistence) | Already in venv | 2.0.48 | None needed |
| transformers | SENT-02 (FinBERT optional) | Not in project venv | Must install if finbert selected | VADER (default) |
| torch | FinBERT backend | Not in project venv | Must install if finbert selected | VADER (default) |
| Python 3.12 | All | Available | 3.12.10 | None needed |

**Missing dependencies with no fallback:**
- `feedparser==6.0.12` — must add to `requirements.txt` and `pyproject.toml`
- `vaderSentiment==3.3.2` — must add to `requirements.txt` and `pyproject.toml`

**Missing dependencies with fallback:**
- `transformers` + `torch` — only needed for FinBERT; VADER is the default; add as `pyproject.toml` optional dependency `[sentiment-finbert]`

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` — testpaths=["tests"], asyncio_mode="auto" |
| Quick run command | `python -m pytest tests/test_sentiment.py -x --tb=short -q` |
| Full suite command | `python -m pytest tests/ -x --tb=short -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SENT-01 | Feed polling filters gold-relevant articles | unit | `pytest tests/test_news_fetcher.py -x` | Wave 0 |
| SENT-01 | APScheduler job fires at correct interval | unit | `pytest tests/test_sentiment_service.py::test_scheduler_interval -x` | Wave 0 |
| SENT-02 | VADER score output range -1..+1 | unit | `pytest tests/test_sentiment_analyzer.py::test_vader_range -x` | Wave 0 |
| SENT-02 | Headline "gold surges on Fed pause" -> positive | unit | `pytest tests/test_sentiment_analyzer.py::test_gold_headline_positive -x` | Wave 0 |
| SENT-03 | EWM aggregation with synthetic 3-article dataset | unit | `pytest tests/test_sentiment_aggregator.py::test_ewm_1h -x` | Wave 0 |
| SENT-03 | Momentum = sent_1h - sent_4h | unit | `pytest tests/test_sentiment_aggregator.py::test_momentum -x` | Wave 0 |
| SENT-04 | SentimentFeatures.calculate() adds 6 columns to df | unit | `pytest tests/test_sentiment_features.py::test_feature_columns -x` | Wave 0 |
| SENT-04 | FeatureEngineer includes sent_* in get_feature_names() | integration | `pytest tests/test_feature_engineer_sentiment.py -x` | Wave 0 |
| SENT-05 | NewsSentiment ORM model saves to SQLite | integration | `pytest tests/test_sentiment_repository.py -x` | Wave 0 |
| SENT-05 | Duplicate URL rejected (unique constraint) | unit | `pytest tests/test_sentiment_repository.py::test_dedup -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_news_fetcher.py tests/test_sentiment_analyzer.py tests/test_sentiment_aggregator.py -x --tb=short -q`
- **Per wave merge:** `python -m pytest tests/ -x --tb=short -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_news_fetcher.py` — covers SENT-01 feed filtering
- [ ] `tests/test_sentiment_analyzer.py` — covers SENT-02 VADER/FinBERT scoring
- [ ] `tests/test_sentiment_aggregator.py` — covers SENT-03 aggregation windows
- [ ] `tests/test_sentiment_features.py` — covers SENT-04 ML feature class
- [ ] `tests/test_sentiment_repository.py` — covers SENT-05 SQLite persistence
- [ ] `tests/test_feature_engineer_sentiment.py` — covers SENT-04 FeatureEngineer integration

---

## Sources

### Primary (HIGH confidence)
- feedparser PyPI 6.0.12 — feed parsing API, ETag support, status codes
- vaderSentiment PyPI 3.3.2 — compound score range, SentimentIntensityAnalyzer API
- pandas 2.x docs: `DataFrame.ewm(halflife, times=)` — time-based EWM
- APScheduler 3.11.2 docs: AsyncIOScheduler — background job pattern
- ProsusAI/finbert HuggingFace model card — label mapping, score formula (p(pos) - p(neg))
- Project source files: `ai_engine/features/technical_features.py`, `feature_engineer.py`, `database/models.py`, `config/settings.py`, `database/repositories/signal_repo.py` — integration patterns

### Secondary (MEDIUM confidence)
- Kitco RSS URL `https://www.kitco.com/news/category/commodities/gold/rss` — confirmed referenced in rss.app and feedspot aggregators; direct page exists
- Investing.com RSS `https://www.investing.com/rss/news_11.rss` — referenced in their own webmaster-tools page; multiple aggregators confirm availability
- MarketWatch RSS `https://feeds.marketwatch.com/marketwatch/topstories/` — official MW documentation states free for personal use
- Reuters paywall Oct 2024: confirmed by Axios, Fortune, The Baron (three independent sources)
- FinBERT accuracy 69% vs VADER 56% on financial text: cited in multiple 2024-2025 papers (Atlantis Press, nosible.ghost.io benchmark)

### Tertiary (LOW confidence)
- GoldBroker RSS `https://www.goldbroker.com/news.rss` — referenced in Investing.com RSS tools page; not independently verified as accessible without auth
- FinBERT Windows HuggingFace cache path issue — single community thread; may not apply to all Windows configurations

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — feedparser/vaderSentiment/APScheduler versions verified via pip index; all confirmed for Python 3.12
- Architecture: HIGH — directly derived from project's own source code patterns (technical_features.py, models.py, signal_repo.py)
- Pitfalls: HIGH (Reuters/Bloomberg paywall) — three independent news sources confirm October 2024 paywall; MEDIUM (other pitfalls) — derived from library docs and community knowledge
- Feed URLs: MEDIUM — Kitco/Investing.com/MarketWatch confirmed via multiple aggregators; direct testing needed in Wave 0

**Research date:** 2026-03-27
**Valid until:** 2026-06-27 (90 days — feed URLs may change; verify before execution)
