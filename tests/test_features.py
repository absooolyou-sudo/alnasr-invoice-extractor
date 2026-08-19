from app import extract_pdf_text, extract_invoice, format_invoice, reverse_pdf_line, normalize_neighborhood

assert reverse_pdf_line("John Smith") == "John Smith"
assert normalize_neighborhood("الرنجس") == "النرجس"

pdf_path = "/home/ubuntu/upload/وليدالنهدي.pdf"
text = extract_pdf_text(pdf_path)
data = extract_invoice(text, 8, pdf_path=pdf_path)
expected = {
    "اليوم": "الأحد",
    "الاسم": "وليد النهدي",
    "الحي": "العزيزية",
    "رقم الجوال": "+966595808200",
    "رقم الطلب": "278439534",
    "عدد الطلبات الحالية": "8",
}
for key, value in expected.items():
    assert data[key] == value, f"{key}: {data[key]!r} != {value!r}"
print(format_invoice(data))
print("ALL_FEATURE_TESTS_PASSED")
