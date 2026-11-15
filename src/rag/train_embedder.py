"""Fine-tune the SentenceTransformer embedding model on Temporal Hard Negatives.

Constructs (query, positive_chunk, hard_negative_outdated_chunk) triplets directly
from verified Markdown chunks in ChronoReg without touching the held-out benchmark.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict
from pathlib import Path

from torch.utils.data import DataLoader
from sentence_transformers import InputExample, SentenceTransformer, losses

from .chunker import Chunk, load_chunks
from .config import load_config, resolve


def build_temporal_triplets(chunks: list[Chunk], seed: int = 42) -> list[InputExample]:
    """Generate contrastive training examples with same-topic cross-year hard negatives."""
    rng = random.Random(seed)
    by_topic: dict[str, list[Chunk]] = defaultdict(list)

    for c in chunks:
        topic = c.metadata.get("topic_hint") or "general"
        if c.metadata.get("start_year", 0) > 0 and len(c.document.strip()) >= 80:
            by_topic[topic].append(c)

    examples: list[InputExample] = []
    for topic, topic_chunks in by_topic.items():
        for pos in topic_chunks:
            ay = pos.metadata["academic_year"]
            sy = pos.metadata["start_year"]
            dieu = pos.metadata.get("dieu_so", "")
            title = pos.metadata.get("dieu_title", "") or pos.metadata.get("scope", "")

            # Synthesize diverse temporal queries anchored to the chunk's year and heading
            first_line = pos.document.splitlines()[0].strip(" #*:-")[:100]
            queries = [
                f"Quy định về {title or first_line} trong năm học {ay} như thế nào?",
                f"Năm học {ay}, {dieu} {title} quy định gì?".strip(),
            ]

            # Hard negative: same topic and similar structure, but DIFFERENT academic year
            neg_pool = [
                c for c in topic_chunks
                if c.metadata["start_year"] != sy and c.metadata["doc_id"] != pos.metadata["doc_id"]
            ]

            for q in queries:
                if neg_pool:
                    hard_neg = rng.choice(neg_pool)
                    examples.append(InputExample(texts=[q, pos.text, hard_neg.text]))
                else:
                    examples.append(InputExample(texts=[q, pos.text]))

    rng.shuffle(examples)
    return examples


def train_embedding_model(
    cfg_path: Path | None = None,
    output_dir: Path = Path("runs/rag_embedder_finetuned"),
    epochs: int = 3,
    batch_size: int = 16,
    lr: float = 2e-5,
) -> Path:
    cfg = load_config(cfg_path)
    chunks_path = resolve(cfg["chunks_file"])
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Missing {chunks_path}. Run: python -m src.versioning.cli export-chunks --include-unreviewed --max-chars 1500"
        )

    chunks = load_chunks(
        chunks_path,
        reviewed_file=resolve(cfg["reviewed_documents_file"]),
        documents_file=resolve(cfg.get("documents_file", "data/versioning/documents.jsonl")),
        min_articles=cfg.get("min_articles", 3) if cfg.get("chunk_by_article", True) else 10**9,
        max_article_chars=cfg.get("max_article_chars", 2000),
    )

    examples = build_temporal_triplets(chunks)
    if not examples:
        raise RuntimeError("No valid training triplets generated from chunks.")

    base_model_name = cfg["embedding_model"]
    model = SentenceTransformer(base_model_name)
    train_dataloader = DataLoader(examples, shuffle=True, batch_size=batch_size)
    train_loss = losses.MultipleNegativesRankingLoss(model=model)

    warmup_steps = max(1, int(len(train_dataloader) * epochs * 0.1))
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Training {base_model_name} on {len(examples)} temporal triplets -> {output_dir}")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": lr},
        output_path=str(output_dir),
        show_progress_bar=True,
    )
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune ChronoReg RAG Embedding Model")
    parser.add_argument("--output", type=Path, default=Path("runs/rag_embedder_finetuned"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    args = parser.parse_args()

    out = train_embedding_model(
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )
    print(f"Completed! Update 'embedding_model: {out.as_posix()}' in configs/rag.yaml and re-run: python -m src.rag.index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())