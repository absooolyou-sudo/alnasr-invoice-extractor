from app import extract_pdf_text, extract_invoice, format_invoice

pdf_path = "/home/ubuntu/upload/وليدالنهدي.pdf"
text = extract_pdf_text(pdf_path)
data = extract_invoice(text, 8)
print(format_invoice(data))
