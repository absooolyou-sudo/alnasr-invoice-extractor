from app import extract_pdf_text

text = extract_pdf_text('/home/ubuntu/upload/وليدالنهدي.pdf')
for i, line in enumerate(text.splitlines()):
    if line.strip():
        print(i, repr(line))
