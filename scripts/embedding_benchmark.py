#!/usr/bin/env python3
"""Empirically benchmark local embedding models against the legal chunk corpus.

This script is intentionally throwaway benchmarking code and does not create a
retrieval pipeline or vector store. It reads the real chunk corpus from
output/chunks/*.chunks.json and compares 3 sentence-transformers models using a
hand-labeled evaluation file supplied by the user.

Usage:
    python scripts/embedding_benchmark.py --eval-file path/to/eval.json

The eval file should contain a list of items like:
    [{"query": "...", "expected_chunk_id": "CA1872_s12"}, ...]

It also accepts a dict with a "queries" key, or a dict with a single item.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "sentence-transformers is required. Install it with: pip install -r requirements.txt"
    ) from exc


MODEL_IDS = {
    "BAAI/bge-large-en-v1.5": "BAAI/bge-large-en-v1.5",
    "Snowflake/snowflake-arctic-embed-m": "Snowflake/snowflake-arctic-embed-m",
    "sentence-transformers/all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
}


def _load_chunks(chunk_dir: Path) -> list[dict[str, Any]]:
    chunk_records: list[dict[str, Any]] = []
    for chunk_file in sorted(chunk_dir.glob("*.chunks.json")):
        payload = json.loads(chunk_file.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            items = payload.get("chunks") or payload.get("items") or []
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError(f"Unsupported chunk file format in {chunk_file}")

        if not isinstance(items, list):
            raise ValueError(f"Chunk file did not contain a list payload: {chunk_file}")

        for item in items:
            if not isinstance(item, dict):
                continue
            chunk_id = str(item.get("chunk_id") or "").strip()
            text = item.get("text")
            if not chunk_id or not isinstance(text, str):
                continue
            chunk_records.append({"chunk_id": chunk_id, "text": text.strip()})

    if not chunk_records:
        raise ValueError(f"No valid chunks were found under {chunk_dir}")
    return chunk_records


def _load_eval_set(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Eval set file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("queries")
            or payload.get("items")
            or payload.get("eval_set")
            or payload.get("data")
            or [payload]
        )
    else:
        raise ValueError(f"Unsupported eval-set format in {path}")

    if not isinstance(items, list):
        raise ValueError(f"Eval set did not resolve to a list of items: {path}")

    result: list[dict[str, str]] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Eval item #{idx} is not an object: {path}")

        query = (
            item.get("query")
            or item.get("question")
            or item.get("text")
            or item.get("prompt")
        )
        expected_chunk_id = (
            item.get("expected_chunk_id")
            or item.get("chunk_id")
            or item.get("target_chunk_id")
            or item.get("expected_id")
            or item.get("id")
        )

        if query is None or expected_chunk_id is None:
            raise ValueError(
                f"Eval item #{idx} must include a query and an expected_chunk_id. "
                f"Found keys: {sorted(item.keys())}"
            )

        result.append(
            {
                "query": str(query).strip(),
                "expected_chunk_id": str(expected_chunk_id).strip(),
            }
        )

    if not result:
        raise ValueError(f"No evaluation items were loaded from {path}")

    return result


def _compute_cosine_scores(chunk_matrix: np.ndarray, query_vector: np.ndarray) -> np.ndarray:
    chunk_norms = np.linalg.norm(chunk_matrix, axis=1, keepdims=True)
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0 or np.any(chunk_norms == 0):
        safe_chunk_norms = np.where(chunk_norms == 0, 1.0, chunk_norms)
        chunk_scores = chunk_matrix @ query_vector / (safe_chunk_norms.squeeze() * query_norm)
        if query_norm == 0:
            return np.zeros(chunk_matrix.shape[0], dtype=np.float64)
        return chunk_scores
    return (chunk_matrix @ query_vector) / (chunk_norms.squeeze() * query_norm)


def _rank_expected_chunk(
    scores: np.ndarray,
    chunk_ids: list[str],
    expected_chunk_id: str,
    top_k: int = 5,
) -> tuple[bool, int | None]:
    ranked_indices = np.argsort(scores)[::-1][:top_k]
    top_ids = [chunk_ids[idx] for idx in ranked_indices]
    try:
        rank = top_ids.index(expected_chunk_id) + 1
        return True, rank
    except ValueError:
        return False, None


def _benchmark_model(
    model_name: str,
    corpus: list[dict[str, Any]],
    eval_set: list[dict[str, str]],
    top_k: int = 5,
) -> dict[str, Any]:
    model = SentenceTransformer(model_name)
    corpus_texts = [chunk["text"] for chunk in corpus]
    chunk_ids = [chunk["chunk_id"] for chunk in corpus]

    chunk_start = time.perf_counter()
    chunk_embeddings = model.encode(
        corpus_texts,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
        batch_size=32,
    )
    chunk_elapsed = time.perf_counter() - chunk_start
    chunk_embedding_time_per_chunk = chunk_elapsed / len(corpus) if corpus else 0.0

    hits = 0
    ranks: list[int] = []
    details: list[dict[str, Any]] = []

    query_start = time.perf_counter()
    for item in eval_set:
        query_vector = model.encode(
            [item["query"]],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=1,
        )[0]

        scores = _compute_cosine_scores(chunk_embeddings, query_vector)
        hit, rank = _rank_expected_chunk(scores, chunk_ids, item["expected_chunk_id"], top_k=top_k)
        if hit:
            hits += 1
            ranks.append(rank)
        details.append(
            {
                "query": item["query"],
                "expected_chunk_id": item["expected_chunk_id"],
                "hit": hit,
                "rank": rank,
            }
        )
    query_elapsed = time.perf_counter() - query_start

    hit_rate = (hits / len(eval_set)) if eval_set else 0.0
    average_rank = float(np.mean(ranks)) if ranks else None

    return {
        "model": model_name,
        "hit_rate": hit_rate,
        "average_rank": average_rank,
        "embedding_time_per_chunk": chunk_embedding_time_per_chunk,
        "query_embedding_time_total": query_elapsed,
        "hits": hits,
        "total_queries": len(eval_set),
        "details": details,
    }


def _format_table(results: list[dict[str, Any]]) -> str:
    headers = ["model", "hit_rate", "avg_rank_of_correct", "embed_time_per_chunk_s"]
    rows: list[list[str]] = []
    for result in results:
        hit_rate = f"{result['hit_rate'] * 100:.1f}% ({result['hits']}/{result['total_queries']})"
        avg_rank = "N/A" if result["average_rank"] is None else f"{result['average_rank']:.2f}"
        embed_time = f"{result['embedding_time_per_chunk']:.6f}"
        rows.append([result["model"], hit_rate, avg_rank, embed_time])

    widths = [max(len(str(header)), *(len(str(row[idx])) for row in rows)) for idx, header in enumerate(headers)]
    header_line = " | ".join(str(header).ljust(widths[idx]) for idx, header in enumerate(headers))
    sep_line = "-+-".join("-" * widths[idx] for idx in range(len(headers)))
    lines = [header_line, sep_line]
    for row in rows:
        lines.append(" | ".join(str(value).ljust(widths[idx]) for idx, value in enumerate(row)))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark local embedding models on the legal chunk corpus.")
    parser.add_argument(
        "--chunk-dir",
        type=Path,
        default=Path("output/chunks"),
        help="Directory containing *.chunks.json files (default: output/chunks)",
    )
    parser.add_argument(
        "--eval-file",
        type=Path,
        required=True,
        help="Path to the hand-labeled eval JSON file with query + expected_chunk_id entries.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(MODEL_IDS.keys()),
        choices=list(MODEL_IDS.keys()),
        help="Local sentence-transformers models to benchmark. Defaults to the three requested models.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of retrieved neighbors to consider when measuring hits (default: 5).",
    )

    args = parser.parse_args()

    corpus = _load_chunks(args.chunk_dir)
    eval_set = _load_eval_set(args.eval_file)
    print(f"Loaded {len(corpus)} chunks from {len(sorted(args.chunk_dir.glob('*.chunks.json')))} chunk files")
    print(f"Loaded {len(eval_set)} test queries from {args.eval_file}")
    print()

    results: list[dict[str, Any]] = []
    for model_name in args.models:
        model_result = _benchmark_model(model_name, corpus, eval_set, top_k=args.top_k)
        results.append(model_result)

    print(_format_table(results))
    print()
    for result in results:
        print(f"Model: {result['model']}")
        print(f"  Hits: {result['hits']} / {result['total_queries']} ({result['hit_rate'] * 100:.1f}%)")
        if result["average_rank"] is None:
            print("  Average rank of correct answer: N/A (no correct retrievals)")
        else:
            print(f"  Average rank of correct answer: {result['average_rank']:.2f}")
        print(f"  Chunk embedding time: {result['embedding_time_per_chunk']:.6f} s/chunk")
        print()


if __name__ == "__main__":
    main()
