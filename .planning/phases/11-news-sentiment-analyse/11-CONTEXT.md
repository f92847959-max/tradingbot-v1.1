# Phase 11: News-Sentiment-Analyse - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Echtzeit-Nachrichtenanalyse mit automatischer Sentiment-Bewertung als ML-Feature und MiroFish-Input.

Dieses Phase baut eine News-Sentiment-Pipeline, die Gold-relevante RSS-Feeds alle 5 Minuten pollt, jeden Artikel mit VADER NLP bewertet, Scores in rollierenden 1h/4h/24h-Fenstern mit Exponential-Decay aggregiert, persistiert in SQLite, und 6 ML-Features (`sent_1h`, `sent_4h`, `sent_24h`, `sent_momentum`, `sent_divergence`, `news_count_1h`) über das bestehende `FeatureEngineer`-Muster bereitstellt. Außerdem wird ein MiroFish-Seed-Dokument stündlich aktualisiert.

**Was existiert:**
- `ai_engine/features/technical_features.py` — FEATURE_NAMES Pattern
- `ai_engine/features/feature_engineer.py` — FeatureEngineer mit bestehenden Feature-Gruppen
- `database/models.py` — ORM-Modelle (Candle, Signal) als Vorlage
- `config/settings.py` — MiroFish settings als Vorlage (mirofish_enabled=False)
- `mirofish_seeds/` — Seed-Verzeichnis mit gold_market_overview.md Pattern
- `APScheduler` — bereits im venv installiert (3.11.2)

**Was diese Phase hinzufügt:**
- `sentiment/` Modul (news_fetcher, sentiment_analyzer, sentiment_aggregator, sentiment_repository)
- `ai_engine/features/sentiment_features.py` (SentimentFeatures Klasse)
- `NewsSentiment` ORM-Modell in `database/models.py`
- Sentiment settings in `config/settings.py`
- MiroFish Seed `mirofish_seeds/news_sentiment.md` (stündlich aktualisiert)
- Lifecycle-Integration in `trading/lifecycle.py`

</domain>

<decisions>
## Implementation Decisions

### NLP Model & Feed Configuration
- VADER als Standard-NLP-Modell (`vaderSentiment 3.3.2`) — Microseconds Inferenz, kein Download, nativer -1..+1 Bereich; FinBERT als opt-in via `sentiment_model: "finbert"` in settings
- 4 kostenlose RSS-Feeds: Kitco, Investing.com, MarketWatch, GoldBroker — Reuters/Bloomberg seit 2024 hinter Paywall
- Mindestens 1 Gold-Keyword-Treffer für Artikel-Aufnahme (`sentiment_min_keywords: 1`)
- Hierarchische Quellen-Gewichtung: kitco=1.0, investing=0.9, marketwatch=0.8, goldbroker=0.7

### ML Feature Integration
- `sentiment_enabled=False` als Default — entspricht MiroFish opt-in Pattern aus Phase 6
- Feature-Cache bypass: SentimentFeatures.calculate() fragt immer frisch beim Aggregator an — kein Einbetten in gecachtes DataFrame (Sentiment ändert sich alle 5min unabhängig von Candle-Timestamps)
- `sent_divergence` = `sent_1h - price_direction` (Divergenz zwischen Sentiment und Preis-Richtung); `sent_momentum` = `sent_1h - sent_4h`
- Fallback bei disabled oder fehlenden Daten: Alle 6 Features auf `0.0` setzen — neutral, kein künstliches Signal, Modell-Input-Shape bleibt konsistent

### Data Persistence & Backtesting
- Retention: 30 Tage (`sentiment_retention_days: 30`)
- Deduplizierungs-Key: `entry.id` (feedparser-normalisiert) — zuverlässiger als URL mit UTM-Parametern
- Kein historisches Backfill — frisch starten; Sentiment-Daten bauen sich organisch auf

### MiroFish Seed Integration
- Seed-Update: Alle 1h (nicht jede 5min-Abfrage) — verhindert MiroFish Context-Flooding
- Format: Deutsche Markdown-Prosa — entspricht `gold_market_overview.md` Pattern
- Inhalt: Aggregierter Überblick (1h/4h/24h Scores + Top-Headlines) — keine rohen Artikel-Dumps

### Claude's Discretion
- Genaue Keyword-Liste für Gold-Relevanz-Filterung (Erweiterung der Research-Empfehlung)
- Alembic-Migration Script für `news_sentiment` Tabelle
- Spezifische APScheduler Job-Konfiguration (Job-ID, Timeout, error_listener)
- FinBERT Windows HuggingFace Cache Path (`TRANSFORMERS_CACHE` Env-Var)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ai_engine/features/technical_features.py` — FEATURE_NAMES List + calculate(df) Interface — direktes Template für SentimentFeatures
- `ai_engine/features/feature_engineer.py` — FeatureEngineer.__init__() mit `self._micro = MicrostructureFeatures()` Pattern — zeigt wo SentimentFeatures eingehängt wird
- `database/models.py` — Candle/Signal ORM-Modelle als Template für NewsSentiment (mapped_column, Index, mapped_column Syntax)
- `database/repositories/signal_repo.py` — Repository Pattern für async SQLAlchemy CRUD
- `config/settings.py` — MiroFish settings Sektion als Template für sentiment_* settings
- `trading/lifecycle.py` — MiroFish start/stop Pattern für SentimentService Lifecycle-Integration
- `mirofish_seeds/` — Existierendes Verzeichnis; gold_market_overview.md zeigt deutschen Prosa-Seed-Stil
- APScheduler 3.11.2 — bereits im venv (asyncio_mode=true in pyproject.toml)

### Established Patterns
- Feature-Klassen folgen FEATURE_NAMES Pattern mit calculate(df) → df
- Settings: bool Opt-in Flag + zugehörige Config-Werte (wie mirofish_enabled + mirofish_*)
- Graceful Degradation: Service None = 0.0 Fallback (nicht Exception)
- Async ORM: SQLAlchemy 2.0 async Session Pattern aus signal_repo.py
- Stdlib calendar fixup in __init__.py bekannt (Phase 08) — bei neuen Modulen auf Import-Konflikte achten

### Integration Points
- `ai_engine/features/feature_engineer.py` — SentimentFeatures als 6. Feature-Gruppe hinzufügen (nach Microstructure)
- `database/models.py` — NewsSentiment ORM-Modell anhängen
- `config/settings.py` — sentiment_* Felder hinzufügen
- `trading/lifecycle.py` — SentimentService.start()/stop() neben MiroFish
- `mirofish_seeds/news_sentiment.md` — neuer Seed (stündlich per SentimentService geschrieben)

</code_context>

<specifics>
## Specific Ideas

- feedparser.parse() ist synchron und blockiert den Event-Loop — immer via `run_in_executor` aufrufen
- VADER over-scoring von Finanz-Boilerplate beachten: Gold-spezifische Adjustment-Liste aus Research verwenden
- URL-Normalisierung: UTM-Parameter vor Speicherung entfernen; `entry.id` als primären Dedup-Key
- FinBERT: `TRANSFORMERS_CACHE` auf pfad-sicheres Verzeichnis setzen (Windows-spezifisch)
- Research-Empfehlung: Investing.com Rate-Limiting in Wave 0 testen; Fallback auf fgmr.com bei 429

</specifics>

<deferred>
## Deferred Ideas

Keine — Diskussion blieb im Phase-Scope.

</deferred>
