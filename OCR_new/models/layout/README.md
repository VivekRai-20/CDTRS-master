# models/layout/

Reserved for a layout model for `layout/region_detector.py`. **No model is
needed and none is used.**

The region detector always uses its built-in contour method, which works for
letters, notes and forms. The code loads `models/layout/layout_model.pkl` if one
exists, but model-based detection is not implemented: it falls back to the contour
method. There is no training tool for a layout model in this project.
