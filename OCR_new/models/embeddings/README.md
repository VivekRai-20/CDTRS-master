# models/embeddings/

Place a Sentence-Transformer compatible embedding model here.

## Recommended: sentence-transformers/all-MiniLM-L6-v2

Download the model offline and place in:

    models/embeddings/model/
    ├── config.json
    ├── tokenizer_config.json
    ├── tokenizer.json
    ├── vocab.txt
    └── pytorch_model.bin  (or model.safetensors)

## Configuration (config.yaml)

    semantic:
      enabled: true
      embedding_model: "models/embeddings/model"
