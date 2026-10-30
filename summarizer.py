"""Extractive text summarizer (no external ML models, no NLTK downloads).

Sentences are scored by the frequency of the meaningful words they contain
(with a small boost for the opening sentences, as news articles put the key
facts first). The top sentences are returned in their original order.
"""
import re
from collections import Counter

STOPWORDS = set(
    """a about above after again against all also am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have having he
    her here hers him his how i if in into is it its just me more most my no nor not now of off on once only or
    other our out over own same she should so some such than that the their them then there these they this those
    through to too under until up very was we were what when where which while who whom why will with would you
    your said says say one two new like get got""".split()
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z0-9\"'(])")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")


def split_sentences(text: str):
    text = re.sub(r"\s+", " ", text or "").strip()
    sentences = _SENTENCE_SPLIT.split(text)
    return [s.strip() for s in sentences if 40 <= len(s.strip()) <= 450]


def _tokens(sentence: str):
    return [w for w in (m.lower() for m in _WORD.findall(sentence)) if w not in STOPWORDS and len(w) > 2]


def summarize(text: str, max_sentences: int = 3, max_chars: int = 700) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return re.sub(r"\s+", " ", text or "").strip()[:max_chars]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)[:max_chars]

    freq = Counter(w for s in sentences for w in _tokens(s))
    scored = []
    for index, sentence in enumerate(sentences):
        tokens = _tokens(sentence)
        if not tokens:
            continue
        score = sum(freq[w] for w in tokens) / (len(tokens) ** 0.6)
        if index < 3:
            score *= 1.25  # lead bias for news articles
        scored.append((score, index))

    best = sorted(scored, reverse=True)[:max_sentences]
    chosen = [sentences[i] for _, i in sorted(best, key=lambda x: x[1])]
    summary = " ".join(chosen)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3].rsplit(" ", 1)[0] + "..."
    return summary
