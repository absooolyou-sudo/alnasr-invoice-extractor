import re
from app import extract_pdf_text, readable_lines
raw, rev = readable_lines(extract_pdf_text('/home/ubuntu/upload/وليدالنهدي.pdf'))
text = "\n".join(rev)
print(repr(rev[9]))
print(re.findall(r"حي\s+(?!شارع\b)([^،,\n]+)", text))
print(re.findall(r"حي\s+([^،,\n]+)", text))
