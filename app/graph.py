"""Builds the knowledge graph: entries and shared tags as nodes, with edges
for shared tags and for text similarity between entries.

No vector database or embedding model needed -- TF-IDF cosine similarity
over each entry's title + summary + text is a fast, dependency-light proxy
for "these are about the same thing" at personal-knowledge-base scale.
"""

from __future__ import annotations

from app import db
from app.config import GRAPH_MAX_NEIGHBORS, GRAPH_SIMILARITY_THRESHOLD


def build_graph() -> dict:
    entries = db.list_entries(limit=100_000)

    nodes: list[dict] = []
    links: list[dict] = []

    tag_counts: dict[str, int] = {}
    for e in entries:
        for t in e.get("tags") or []:
            key = t.strip().lower()
            if key:
                tag_counts[key] = tag_counts.get(key, 0) + 1

    for e in entries:
        nodes.append(
            {
                "id": f"entry:{e['id']}",
                "entryId": e["id"],
                "label": e["title"] or "Untitled",
                "type": "entry",
                "sourceType": e["source_type"],
                "group": e["category"] or "Other",
                "val": 3,
            }
        )

    # Only tags shared by 2+ entries add real graph structure -- a tag used
    # once is just noise as a hub node.
    shared_tags = {tag for tag, count in tag_counts.items() if count >= 2}
    for tag in shared_tags:
        nodes.append(
            {
                "id": f"tag:{tag}",
                "label": tag,
                "type": "tag",
                "group": "tag",
                "val": min(2 + tag_counts[tag], 14),
            }
        )

    for e in entries:
        entry_tags = {t.strip().lower() for t in (e.get("tags") or [])}
        for tag in entry_tags & shared_tags:
            links.append(
                {"source": f"entry:{e['id']}", "target": f"tag:{tag}", "type": "tag", "value": 1}
            )

    links.extend(_similarity_links(entries))

    return {"nodes": nodes, "links": links}


def _similarity_links(entries: list[dict]) -> list[dict]:
    if len(entries) < 2:
        return []

    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import linear_kernel

    texts = []
    for e in entries:
        parts = [e.get("title") or "", e.get("summary") or "", (e.get("raw_text") or "")[:1500]]
        texts.append(" ".join(parts))

    try:
        vectorizer = TfidfVectorizer(max_features=4000, stop_words="english")
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return []  # e.g. everything was stopwords / empty vocabulary

    similarity = linear_kernel(matrix, matrix)
    n = len(entries)
    seen: set[tuple[int, int]] = set()
    links: list[dict] = []

    for i in range(n):
        neighbor_idx = np.argsort(-similarity[i])
        added = 0
        for j in neighbor_idx:
            if j == i:
                continue
            score = float(similarity[i][j])
            if score < GRAPH_SIMILARITY_THRESHOLD:
                break
            pair = tuple(sorted((entries[i]["id"], entries[j]["id"])))
            if pair in seen:
                continue
            seen.add(pair)
            links.append(
                {
                    "source": f"entry:{entries[i]['id']}",
                    "target": f"entry:{entries[j]['id']}",
                    "type": "similar",
                    "value": round(score, 3),
                }
            )
            added += 1
            if added >= GRAPH_MAX_NEIGHBORS:
                break

    return links
