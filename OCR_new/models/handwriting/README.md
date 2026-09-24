# models/handwriting/

Place a TrOCR-compatible handwriting recognition model here.

## Recommended: Microsoft TrOCR

Download the model files offline and place them in this directory:

    models/handwriting/v1/
    ├── config.json
    ├── tokenizer_config.json
    ├── vocab.json
    ├── merges.txt
    ├── generation_config.json
    └── pytorch_model.bin  (or model.safetensors)

## Activation

Set the active version:

    echo "v1" > models/handwriting/active.txt

## Configuration (config.yaml)

    handwriting:
      enabled: true
      model_path: "models/handwriting"
      device: "cpu"
      confidence_threshold: 0.5
