# models/layout/

Place a trained layout detection model here.

## Expected file

    models/layout/layout_model.pkl   (scikit-learn or compatible)

If no model is present, the layout analyzer uses a built-in contour-based
heuristic for region detection. This works for most documents without any
trained model.

## Configuration (config.yaml)

    layout:
      enabled: true
      model_path: "models/layout"
