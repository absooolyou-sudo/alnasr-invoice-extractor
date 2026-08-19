from app import extract_pdf_text, readable_lines
raw, rev = readable_lines(extract_pdf_text('/home/ubuntu/upload/وليدالنهدي.pdf'))
for i, line in enumerate(rev):
    if i in (1, 3, 5, 6, 9):
        print(i, repr(line))
