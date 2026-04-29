from sentiment.sentiment_analyzer import SentimentAnalyzer


def test_vader_range():
    analyzer = SentimentAnalyzer()

    for text in ("gold surges", "dollar strengthens and gold crashes", ""):
        assert -1.0 <= analyzer.score(text) <= 1.0


def test_gold_headline_positive():
    assert SentimentAnalyzer().score("gold surges on Fed pause") > 0.1


def test_gold_headline_negative():
    assert SentimentAnalyzer().score("dollar strengthens, gold crashes on hawkish Fed") < 0.0


def test_html_tags_stripped_before_scoring():
    analyzer = SentimentAnalyzer()

    assert analyzer.score("<p>gold surges</p>") == analyzer.score("gold surges")
