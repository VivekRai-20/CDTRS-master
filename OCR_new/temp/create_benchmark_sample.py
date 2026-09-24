import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs('temp/benchmark', exist_ok=True)

def create_sample_form():
    # Create a realistic scanned form with printed headers and handwritten entries
    img = np.full((1200, 1000, 3), 250, dtype=np.uint8) # slight off-white paper
    pil_img = Image.fromarray(img)
    draw = ImageDraw.Draw(pil_img)
    
    # Fonts
    font_printed = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 24)
    font_printed_bold = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 28)
    
    # Try different handwriting fonts
    try:
        font_hw1 = ImageFont.truetype('C:/Windows/Fonts/segprint.ttf', 24)
        font_hw2 = ImageFont.truetype('C:/Windows/Fonts/segoesc.ttf', 24)
    except Exception:
        font_hw1 = font_printed
        font_hw2 = font_printed
        
    # Title
    draw.text((250, 40), "LABORATORY REPORT", fill=(0, 0, 0), font=font_printed_bold)
    
    # Lines & Fields
    fields = [
        ("Subject:", "Applied Chemistry II", 120),
        ("Experiment No:", "07", 180),
        ("Title:", "Kinetics of Ester Hydrolysis", 240),
        ("Student Name:", "Vivek Rai", 300),
        ("Roll Number:", "20261042", 360),
        ("Date of Submission:", "24/08/2026", 420),
        ("Department:", "Computer Engineering", 480),
        ("Semester:", "IV", 540),
        ("Aim:", "To determine the velocity constant of acid hydrolysis", 600),
        ("Faculty Incharge:", "Dr. S. K. Mehta", 660),
        ("Marks Obtained:", "24 / 25", 720),
    ]
    
    for label, hw_val, y in fields:
        draw.text((60, y), label, fill=(10, 10, 10), font=font_printed_bold)
        # Draw underline
        draw.line([(320, y + 28), (900, y + 28)], fill=(180, 180, 180), width=1)
        # Handwritten value in blue ink
        draw.text((340, y - 2), hw_val, fill=(15, 30, 140), font=font_hw1)
        
    # Add some handwritten remarks at the bottom
    draw.text((60, 800), "Remarks:", fill=(10, 10, 10), font=font_printed_bold)
    draw.text((200, 800), "Good understanding of first order reaction dynamics.", fill=(15, 30, 140), font=font_hw2)
    draw.text((200, 840), "Calculations verified accurately.", fill=(15, 30, 140), font=font_hw2)
    
    pil_img.save('temp/benchmark/form_sample.png')
    print("Created temp/benchmark/form_sample.png")

if __name__ == "__main__":
    create_sample_form()
