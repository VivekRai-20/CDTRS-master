# models/embeddings/

Sentence embedding model used for semantic understanding (`semantic/embedding_engine.py`),
for example document similarity and semantic classification.

`models/embeddings/model/` holds **sentence-transformers/all-MiniLM-L6-v2** (about
90 MB). It is tracked in git, so it is available offline right after cloning.

The path is set in `config/config.yaml` → `semantic.embedding_model` (default
`models/embeddings/model`). It is loaded with `sentence-transformers` 5.6.1 from
`imp.txt`, and never downloaded at run time.
