from app import extract_pdf_text, extract_invoice, format_invoice

pdf_path = "/home/ubuntu/upload/BanderFahad.pdf"
text = extract_pdf_text(pdf_path)
data = extract_invoice(text, 9, pdf_path=pdf_path)
print(format_invoice(data))
