"""Cross-cutting constants shared by the schema and the pipeline.

Kept in the domain layer so both :mod:`pulsegraph.db.models` (the column
type) and :mod:`pulsegraph.pipeline.local` (the offline embedder) reference
one value, instead of hardcoding the embedding dimension in several places
(ADR 0014).
"""

# The stored embedding vector dimension. This is fixed at the database
# column level (``Vector(EMBEDDING_DIM)``); changing it is a migration, done
# as part of an embedding-model change together with a re-embed of existing
# items (ADR 0014). The default Ollama embedder (nomic-embed-text) and the
# offline HashingEmbedder both produce vectors of this size.
EMBEDDING_DIM = 768
