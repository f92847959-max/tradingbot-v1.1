# News-Sentiment-Analyse

## Status: Geplant

## Beschreibung
Echtzeit-Nachrichtenanalyse fuer Gold-relevante Events mit automatischer Sentiment-Bewertung als Input fuer das ML-Modell fuer die microfish intigration
.

## Features

### RSS-Feed Parser
- Reuters, Bloomberg, Investing.com, Kitco Gold News
- Gold-relevante Keywords filtern: Fed, Inflation, Zinsen, Krieg, Dollar, Sanctions, Central Bank, Gold Reserves
- Polling-Intervall: alle 5 Minuten

### Sentiment-Scoring
- Sentiment-Score pro Nachricht: -1.0 (sehr bearish) bis +1.0 (sehr bullish)
- NLP-basiert (z.B. FinBERT oder VADER mit Finance-Lexikon)
- Gewichtung nach Quelle (Reuters > random Blog)
- Gewichtung nach Aktualitaet (neuere News = mehr Gewicht)

### Aggregierter Sentiment-Index
- Zeitfenster: 1h, 4h, 24h rollierender Durchschnitt
- Sentiment-Momentum: Aenderungsrate des Sentiments
- Sentiment-Divergenz: Sentiment vs. Preisentwicklung

### Datenbank-Integration
- Historische Sentiment-Daten speichern (Tabelle: news_sentiment)
- Felder: timestamp, source, headline, sentiment_score, keywords, impact_level
- Fuer Backtesting nutzbar

### ML-Integration
- Sentiment-Score als Feature im XGBoost/LightGBM Modell
- Sentiment-Momentum als Feature
- Sentiment-Divergenz als Feature
- News-Count (Anzahl Nachrichten pro Stunde) als Volatilitaets-Indikator

## Technische Umsetzung
- Neues Modul: `sentiment/`
  - `news_fetcher.py` - RSS/API Feeds abrufen
  - `sentiment_analyzer.py` - NLP Sentiment-Scoring
  - `sentiment_aggregator.py` - Zeitfenster-Aggregation
  - `sentiment_repository.py` - DB-Speicherung
- Dependencies: feedparser, transformers (FinBERT), nltk

## Prioritaet: Hoch
