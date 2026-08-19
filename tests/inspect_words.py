import pdfplumber
from pathlib import Path

pdf_path = '/home/ubuntu/upload/وليدالنهدي.pdf'
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    for word in words:
        text = word['text']
        if any(key in text for key in ['وليد', 'النهدي', 'مصدرة', 'العزيزية', '278439534']):
            print({k: word[k] for k in ['text', 'x0', 'x1', 'top', 'bottom']})
