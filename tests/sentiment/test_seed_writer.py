from sentiment.seed_writer import write_sentiment_seed


def test_write_sentiment_seed(tmp_path, sample_articles, reference_now):
    target = tmp_path / "news_sentiment.md"

    write_sentiment_seed(sample_articles[:2], target, reference_now)

    text = target.read_text(encoding="utf-8")
    assert "Sentiment-Ueberblick" in text
    assert "Gold rallies" in text
