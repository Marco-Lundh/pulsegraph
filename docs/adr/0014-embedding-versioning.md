# ADR 0014: Embedding model versioning and re-embedding

## Status
Accepted

## Context
Items store an embedding vector used for per-user deduplication and similarity (ADR 0003). Those vectors are only comparable when produced by the same embedding model. Swapping the embedding model silently breaks dedup and similarity without any crash — exactly the silent-failure class that ADR 0010 guards against, but for vectors instead of source schemas.

## Decision
- Every item records the `embedding_model` that produced its vector.
- Dedup and similarity only compare vectors produced by the same `embedding_model`.
- Changing the embedding model is an explicit, versioned migration: introduce the new model → re-embed affected items in the background → switch comparisons over → retire the old vectors.
- The embedding dimension is tied to the recorded model rather than hardcoded in scattered places; a model change with a different dimension is handled as part of the re-embed migration.

## Alternatives considered
- **Assume a single fixed model forever** — blocks ever upgrading to a better/cheaper embedder.
- **Change the model without re-embedding** — silently corrupts dedup and similarity; old and new vectors are not comparable.

## Consequences
- **Easier:** safe embedding upgrades with no silent corruption of dedup/similarity.
- **Harder:** requires re-embedding jobs and tolerating a transition window with mixed vectors.
- Builds on ADR 0003 (Embedder) and applies the silent-failure philosophy of ADR 0010 to embeddings.
