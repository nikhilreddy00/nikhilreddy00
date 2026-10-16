"""Embed public repos by what they're about and find the clusters.

Pipeline: README + description + topics -> TF-IDF -> LSA (truncated SVD)
-> k-means with k picked by silhouette -> 2-D projection for the map.
Everything is deterministic, so the map only moves when the repos change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .metrics import Repo

STOPWORDS = set("""
a about above after again all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further
had has have having he her here hers him his how i if in into is it its itself just me more
most my no nor not now of off on once only or other our out over own same she should so some
such than that the their them then there these they this those through to too under until up
very was we were what when where which while who whom why will with you your yours via using
use used uses based built build builds simple new one two first get gets make makes into per
readme project projects repo repository code app application install installation pip npm
run running clone git github https http www com org license mit usage example examples setup
requirements python typescript notebook jupyter file files folder src env key api_key docs
demo screenshot image images png jpg md txt yes etc e g i e v1 v2 todo add added lets let
""".split())

TOKEN = re.compile(r"[a-z][a-z0-9+\-]{1,}")


def _clean(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return text


def _split_name(name: str) -> str:
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return re.sub(r"[-_.]+", " ", name)


def _tokens(repo: Repo) -> list[str]:
    head = " ".join([_split_name(repo.name)] * 2 + [repo.description] * 2 + repo.topics * 2)
    text = f"{head} {_clean(repo.readme)}".lower()
    return [t.strip("-") for t in TOKEN.findall(text) if t.strip("-") not in STOPWORDS and len(t.strip("-")) > 2]


@dataclass
class Point:
    repo: Repo
    x: float          # 0..1
    y: float          # 0..1
    cluster: int


@dataclass
class Cluster:
    label: str
    terms: list[str]
    members: list[int]


def _tfidf(docs: list[list[str]]) -> tuple[np.ndarray, list[str]]:
    vocab = sorted({t for d in docs for t in d})
    index = {t: i for i, t in enumerate(vocab)}
    tf = np.zeros((len(docs), len(vocab)))
    for i, d in enumerate(docs):
        for t in d:
            tf[i, index[t]] += 1
    df = (tf > 0).sum(axis=0)
    keep = df <= max(2, 0.6 * len(docs))
    tf, vocab = tf[:, keep], [v for v, k in zip(vocab, keep) if k]
    df = df[keep]
    idf = np.log((1 + len(docs)) / (1 + df)) + 1
    x = np.log1p(tf) * idf
    x /= np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    return x, vocab


def _kmeans(x: np.ndarray, k: int, seed: int = 7, restarts: int = 12) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    best_labels, best_inertia = None, np.inf
    for _ in range(restarts):
        centers = [x[rng.integers(len(x))]]
        for _ in range(k - 1):           # k-means++ seeding
            d2 = np.min([((x - c) ** 2).sum(1) for c in centers], axis=0)
            centers.append(x[rng.choice(len(x), p=d2 / d2.sum())] if d2.sum() else x[rng.integers(len(x))])
        centers = np.array(centers)
        for _ in range(100):
            labels = ((x[:, None, :] - centers[None]) ** 2).sum(-1).argmin(1)
            new = np.array([x[labels == j].mean(0) if (labels == j).any() else centers[j] for j in range(k)])
            if np.allclose(new, centers):
                break
            centers = new
        inertia = ((x - centers[labels]) ** 2).sum()
        if inertia < best_inertia:
            best_labels, best_inertia = labels, inertia
    return best_labels, best_inertia


def _silhouette(x: np.ndarray, labels: np.ndarray) -> float:
    d = np.sqrt(((x[:, None] - x[None]) ** 2).sum(-1))
    scores = []
    for i in range(len(x)):
        same = labels == labels[i]
        if same.sum() <= 1:
            scores.append(0.0)
            continue
        a = d[i, same].sum() / (same.sum() - 1)
        b = min(d[i, labels == j].mean() for j in set(labels) if j != labels[i])
        scores.append((b - a) / max(a, b))
    return float(np.mean(scores))


def _name_clusters(x, vocab, labels, k, label_rules: dict[str, list[str]]) -> list[Cluster]:
    clusters = []
    scores = np.zeros((k, len(label_rules)))
    names = list(label_rules)
    for j in range(k):
        centroid = np.round(x[labels == j].mean(0), 6)
        # Ties broken alphabetically so reruns list the same terms in the same order.
        order = sorted(range(len(vocab)), key=lambda i: (-centroid[i], vocab[i]))
        top = [vocab[i] for i in order[:12] if centroid[i] > 0]
        clusters.append(Cluster(label="", terms=top, members=list(np.where(labels == j)[0])))
        for n, name in enumerate(names):
            kws = label_rules[name]
            scores[j, n] = sum(centroid[i] for i, term in enumerate(vocab)
                               if any(term == kw or term.startswith(kw) for kw in kws))
    # Greedy one-to-one assignment, strongest match first.
    taken_c, taken_n = set(), set()
    for flat in np.argsort(scores, axis=None)[::-1]:
        j, n = divmod(int(flat), len(names))
        if j in taken_c or n in taken_n or scores[j, n] < 0.08:
            continue
        clusters[j].label = names[n]
        taken_c.add(j)
        taken_n.add(n)
    for c in clusters:
        if not c.label:
            c.label = " · ".join(t.replace("-", " ") for t in c.terms[:2]).title() or "Misc"
    return clusters


def embed(repos: list[Repo], label_rules: dict[str, list[str]]) -> tuple[list[Point], list[Cluster]]:
    x, vocab = _tfidf([_tokens(r) for r in repos]) if len(repos) >= 4 else (None, [])
    if len(repos) < 4 or x.shape[1] < 4:
        return _single_row(repos)

    # LSA: keep enough components to capture the topic structure.
    u, s, _ = np.linalg.svd(x - x.mean(0), full_matrices=False)
    dims = min(10, len(repos) - 1)
    z = u[:, :dims] * s[:dims]
    z /= np.linalg.norm(z, axis=1, keepdims=True) + 1e-12
    z = np.round(z, 6)   # drop BLAS-level noise so reruns give identical maps
    z = _fix_signs(z)

    best = None
    for k in range(3, min(7, len(repos) - 1) + 1):
        labels, _ = _kmeans(z, k)
        if len(set(labels)) < k:
            continue
        score = _silhouette(z, labels)
        if best is None or score > best[0] + 0.01:
            best = (score, k, labels)
    if best is None:   # no clean split; fall back to a single group
        return _single_row(repos)
    _, k, labels = best

    xy = _layout(z, labels, k)
    clusters = _name_clusters(x, vocab, labels, k, label_rules)
    points = [Point(r, float(xy[i, 0]), float(xy[i, 1]), int(labels[i])) for i, r in enumerate(repos)]
    return points, clusters


def _single_row(repos: list[Repo]) -> tuple[list[Point], list[Cluster]]:
    """Fallback when there is too little text to find structure."""
    pts = [Point(r, (i + 1) / (len(repos) + 1), 0.5, 0) for i, r in enumerate(repos)]
    return pts, [Cluster("Projects", [], list(range(len(repos))))]


def _fix_signs(a: np.ndarray) -> np.ndarray:
    """SVD/eigen axes have arbitrary sign; make each column's first clearly
    non-zero entry positive so the map doesn't mirror between runs."""
    for axis in range(a.shape[1]):
        nz = np.flatnonzero(np.abs(a[:, axis]) > 1e-6)
        if len(nz) and a[nz[0], axis] < 0:
            a[:, axis] *= -1
    return a


def _layout(z: np.ndarray, labels: np.ndarray, k: int, aspect: float = 2.4) -> np.ndarray:
    """Two-level map: clusters placed by how similar they are (MDS on centroids),
    members arranged around their centroid by their own offsets from it."""
    centroids = np.array([z[labels == j].mean(0) for j in range(k)])

    # Classical MDS on centroid distances.
    d2 = ((centroids[:, None] - centroids[None]) ** 2).sum(-1)
    j_ = np.eye(k) - 1 / k
    b = -0.5 * j_ @ d2 @ j_
    vals, vecs = np.linalg.eigh(b)
    order = np.argsort(vals)[::-1][:2]
    c2 = _fix_signs(vecs[:, order] * np.sqrt(np.maximum(vals[order], 1e-9)))
    c2 = (c2 - c2.min(0)) / (np.ptp(c2, 0) + 1e-12)
    c2[:, 0] *= aspect

    # Member offsets: project onto the global principal axes, scale to a radius.
    zc = z - z.mean(0)
    _, _, vt = np.linalg.svd(zc, full_matrices=False)
    axes = _fix_signs(vt[:2].T.copy())
    xy = np.zeros((len(z), 2))
    radius = {}
    for j in range(k):
        idx = np.where(labels == j)[0]
        radius[j] = 0.07 + 0.045 * np.sqrt(len(idx))
        off = (z[idx] - centroids[j]) @ axes
        scale = np.abs(off).max() or 1
        xy[idx] = off / scale * radius[j] * np.array([1.6, 1.0])

    # Push cluster centres apart until their discs don't touch.
    for _ in range(400):
        moved = False
        for a in range(k):
            for b_ in range(a + 1, k):
                d = c2[a] - c2[b_]
                dist = np.hypot(*(d / [1.6, 1.0]))
                need = (radius[a] + radius[b_]) * 1.6 + 0.12
                if dist < need:
                    step = (d / (np.hypot(*d) + 1e-9) if np.hypot(*d) > 1e-9 else np.array([1.0, 0.3])) * (need - dist) / 2
                    c2[a] += step
                    c2[b_] -= step
                    moved = True
        if not moved:
            break

    for j in range(k):
        xy[labels == j] += c2[j]
    xy = _separate(xy, min_gap=0.075)
    xy = (xy - xy.min(0)) / (np.ptp(xy, 0) + 1e-12)
    return xy


def _separate(xy: np.ndarray, min_gap: float, steps: int = 300) -> np.ndarray:
    """Nudge points apart so no two markers overlap."""
    xy = xy.copy()
    for _ in range(steps):
        moved = False
        for i in range(len(xy)):
            for j in range(i + 1, len(xy)):
                d = xy[i] - xy[j]
                dist = np.hypot(*d)
                if dist < min_gap:
                    push = (d / (dist + 1e-9) if dist > 1e-9 else np.array([1.0, 0.0])) * (min_gap - dist) / 2
                    xy[i] += push
                    xy[j] -= push
                    moved = True
        if not moved:
            break
    return xy
