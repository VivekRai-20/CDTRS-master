from paddleocr import PaddleOCR
import cv2

print("=== Test 1: Current default PaddleOCR(lang='en') ===")
try:
    ocr1 = PaddleOCR(lang='en')
    res1 = ocr1.ocr('temp/handwritten_test.png')
    for r in res1:
        print("res1 texts:", r.get("rec_texts"))
        print("res1 scores:", [round(s, 3) for s in r.get("rec_scores", [])])
except Exception as e:
    print("Test 1 error:", e)

print("\n=== Test 2: PaddleOCR(lang='en', use_doc_unwarping=False, use_doc_orientation_classify=False) ===")
try:
    ocr2 = PaddleOCR(lang='en', use_doc_unwarping=False, use_doc_orientation_classify=False)
    res2 = ocr2.ocr('temp/handwritten_test.png')
    for r in res2:
        print("res2 texts:", r.get("rec_texts"))
        print("res2 scores:", [round(s, 3) for s in r.get("rec_scores", [])])
except Exception as e:
    print("Test 2 error:", e)

print("\n=== Test 3: PP-OCRv4 lang='en' ===")
try:
    ocr3 = PaddleOCR(ocr_version='PP-OCRv4', lang='en', use_doc_unwarping=False, use_doc_orientation_classify=False)
    res3 = ocr3.ocr('temp/handwritten_test.png')
    for r in res3:
        print("res3 texts:", r.get("rec_texts"))
        print("res3 scores:", [round(s, 3) for s in r.get("rec_scores", [])])
except Exception as e:
    print("Test 3 error:", e)

print("\n=== Test 4: PP-OCRv4 lang='ch' (General multilingual) ===")
try:
    ocr4 = PaddleOCR(ocr_version='PP-OCRv4', lang='ch', use_doc_unwarping=False, use_doc_orientation_classify=False)
    res4 = ocr4.ocr('temp/handwritten_test.png')
    for r in res4:
        print("res4 texts:", r.get("rec_texts"))
        print("res4 scores:", [round(s, 3) for s in r.get("rec_scores", [])])
except Exception as e:
    print("Test 4 error:", e)
