"""Graded retrieval metrics; missing-evidence cases reported separately."""
from math import log2


def metrics(retrieved, relevance, k):
    if k < 1:
        raise ValueError("k must be positive")
    ids = list(dict.fromkeys(retrieved))[:k]
    relevant = {key for key, grade in relevance.items() if grade > 0}
    if not relevant:
        return {"recall": None, "precision": None, "mrr": None, "hit_rate": None,
                "ndcg": None, "source_hit_accuracy": None, "empty_result_accuracy": float(not ids)}
    hits = [i + 1 for i, key in enumerate(ids) if key in relevant]
    dcg = sum((2 ** relevance.get(key, 0) - 1) / log2(i + 2) for i, key in enumerate(ids))
    ideal = sum((2 ** grade - 1) / log2(i + 2) for i, grade in enumerate(sorted(relevance.values(), reverse=True)[:k]))
    return {"recall": len(hits) / len(relevant), "precision": len(hits) / k,
            "mrr": 1 / hits[0] if hits else 0.0, "hit_rate": float(bool(hits)),
            "ndcg": dcg / ideal if ideal else 0.0, "source_hit_accuracy": float(bool(hits)), "empty_result_accuracy": None}


def aggregate(rows):
    names = set().union(*(row.keys() for row in rows))
    return {name: sum(values) / len(values) if (values := [r[name] for r in rows if r.get(name) is not None]) else None for name in sorted(names)}
