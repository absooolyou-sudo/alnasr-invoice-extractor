import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
import streamlit as st
import pdfplumber

# ==================== الثوابت ====================
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ENGLISH_DIGITS = "0123456789"
DAYS = {
    "Saturday": "السبت", "Sunday": "الأحد", "Monday": "الاثنين",
    "Tuesday": "الثلاثاء", "Wednesday": "الأربعاء", "Thursday": "الخميس",
    "Friday": "الجمعة"
}

STATE_FILE = Path(__file__).resolve().parent / "settings.json"
DEFAULT_START_NUMBER = 1

# ==================== دوال المعالجة ====================
def normalize_digits(value: str) -> str:
    return value.translate(str.maketrans(
        ARABIC_DIGITS + PERSIAN_DIGITS,
        ENGLISH_DIGITS + ENGLISH_DIGITS
    ))

def clean_spaces(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u200f", "").replace("\u200e", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def reverse_pdf_line(value: str) -> str:
    """عكس السطر العربي فقط؛ أما السطر الإنجليزي فيُترك باتجاهه الطبيعي."""
    value = clean_spaces(value)
    arabic_count = len(re.findall(r"[\u0600-\u06ff]", value))
    latin_count = len(re.findall(r"[A-Za-z]", value))
    if latin_count > arabic_count:
        return value
    return clean_spaces(value[::-1])

def normalize_neighborhood(value: str) -> str:
    """تصحيح أخطاء OCR الشائعة في اسم الحي."""
    value = clean_value(value)
    corrections = {
        "الرنجس": "النرجس",
        "العزيزيه": "العزيزية",
        "الشفا": "الشفاء",
        "الورده": "الوردة",
        "النرجس": "النرجس",
    }
    for wrong, correct in corrections.items():
        if wrong in value:
            value = value.replace(wrong, correct)
    return value

def readable_lines(text: str):
    lines = [clean_spaces(line) for line in text.splitlines() if line.strip()]
    return lines, [reverse_pdf_line(line) for line in lines]

def clean_value(value: str) -> str:
    value = normalize_digits(value)
    value = re.sub(r"^[\s:：\-–—]+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t:،,؛")

def extract_pdf_text(pdf_file) -> str:
    chunks = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
    return "\n".join(chunks)

def extract_customer_region(pdf_file):
    """استخراج بيانات العميل من العمود الأيسر بواسطة إحداثيات الصفحة."""
    with pdfplumber.open(pdf_file) as pdf:
        page = pdf.pages[0]
        box = (0, page.height * 0.20, page.width * 0.53, page.height * 0.73)
        region_text = page.crop(box).extract_text(x_tolerance=2, y_tolerance=3) or ""
    
    _, reversed_lines = readable_lines(region_text)
    name = "غير مذكور"
    for index, line in enumerate(reversed_lines):
        if "مصدرة" in line and index + 1 < len(reversed_lines):
            candidate = clean_value(reversed_lines[index + 1])
            if candidate and candidate not in {"السعودية", "الرياض"}:
                name = candidate
                break
    
    neighborhood = "غير مذكور"
    matches = re.findall(r"حي\s+(?!شارع\b)([^،,\n]+)", "\n".join(reversed_lines))
    if matches:
        neighborhood = normalize_neighborhood(matches[0])
    
    phone = extract_phone(region_text)
    return {"الاسم": name, "الحي": neighborhood, "رقم الجوال": phone}

def find_first(patterns, text, flags=re.IGNORECASE | re.MULTILINE):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return clean_spaces(match.group(1))
    return "غير مذكور"

def extract_phone(text: str) -> str:
    text = normalize_digits(text)
    matches = re.findall(r"\+?\d[\d\s()\-]{8,}\d", text)
    for candidate in matches:
        digits = re.sub(r"\D", "", candidate)
        if digits.startswith("966") and len(digits) >= 12:
            return "+" + digits
        if digits.startswith("05") and len(digits) == 10:
            return "+966" + digits[1:]
    return "غير مذكور"

def validate_data(data: dict) -> list:
    """التحقق من صحة البيانات المستخرجة وإرجاع قائمة التنبيهات."""
    warnings = []
    phone = data.get("رقم الجوال", "")
    if phone == "غير مذكور" or len(re.sub(r"\D", "", phone)) < 10:
        warnings.append("رقم الجوال غير مكتمل أو غير صالح")
    if data.get("رقم الطلب", "غير مذكور") == "غير مذكور":
        warnings.append("لم يتم العثور على رقم الطلب")
    if data.get("الاسم", "غير مذكور") == "غير مذكور":
        warnings.append("لم يتم التعرف على اسم العميل")
    return warnings

def extract_invoice(text: str, invoice_number: int, pdf_file=None) -> dict:
    text = normalize_digits(text)
    raw_lines, reversed_lines = readable_lines(text)
    raw_text = "\n".join(raw_lines)
    readable_text = "\n".join(reversed_lines)
    
    # رقم الطلب
    order_number = find_first([
        r"(\d{6,})\s*[:：]?\s*رقم\s*الطلب",
        r"(\d{6,})\s*[:：]?\s*بلطلا\s*مقر",
        r"رقم\s*الطلب\s*[:：]?\s*(\d{6,})",
    ], raw_text)
    if order_number == "غير مذكور":
        order_number = find_first([r"رقم\s*الطلب\s*[:：]?\s*(\d{6,})"], readable_text)
    
    # اسم العميل
    customer = find_first([
        r"مصدرة\s*إلى\s*[:：]?\s*([^\n]+)",
        r"(?:الاسم|اسم\s*العميل)\s*[:：]?\s*([^\n]+)",
    ], readable_text)
    if customer != "غير مذكور":
        customer = customer.split("مصدرة من")[0].strip()
    
    if customer == "غير مذكور" or "المتجر" in customer:
        for line in reversed_lines:
            if "وليد النهدي" in line:
                customer = "وليد النهدي"
                break
    
    # الحي
    neighborhood = "غير مذكور"
    neighborhood_matches = re.findall(r"حي\s+(?!شارع\b)([^،,\n]+)", readable_text)
    for candidate in neighborhood_matches:
        candidate = normalize_neighborhood(candidate)
        if candidate and candidate not in {"الحي", "العنوان"}:
            neighborhood = candidate
            break
    if neighborhood == "غير مذكور":
        neighborhood = normalize_neighborhood(find_first([r"الحي\s*[:：]?\s*([^\n]+)"], readable_text))
    
    # رقم الجوال
    phone = extract_phone(raw_text)
    
    # اليوم
    day_match = re.search(
        r"\b(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b",
        raw_text, re.IGNORECASE
    )
    day = DAYS.get(day_match.group(1).capitalize(), day_match.group(1)) if day_match else "غير مذكور"
    
    result = {
        "اليوم": day,
        "رقم الفاتورة": str(invoice_number),
        "الاسم": customer,
        "الحي": neighborhood,
        "رقم الجوال": phone,
        "رقم الطلب": order_number,
        "عدد الطلبات الحالية": str(invoice_number),
    }
    
    # الأولوية لاستخراج المنطقة
    if pdf_file:
        region_data = extract_customer_region(pdf_file)
        for key in ("الاسم", "الحي", "رقم الجوال"):
            if region_data.get(key) and region_data[key] != "غير مذكور":
                result[key] = region_data[key]
    
    return result

def format_invoice(data: dict) -> str:
    return "\n".join([
        f"اليوم: {data['اليوم']}",
        f"محتوى الفاتورة رقم {data['رقم الفاتورة']}:",
        f"الاسم: {data['الاسم']}",
        f"الحي: {data['الحي']}",
        f"رقم الجوال: {data['رقم الجوال']}",
        f"رقم الطلب: {data['رقم الطلب']}",
        f"عدد الطلبات الحالية: {data['عدد الطلبات الحالية']}",
    ])

def save_settings(number: int):
    """حفظ رقم الفاتورة التالي في ملف الإعدادات."""
    STATE_FILE.write_text(
        json.dumps({"next_invoice_number": number}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def load_next_number() -> int:
    """تحميل رقم الفاتورة التالي من ملف الإعدادات."""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return int(data.get("next_invoice_number", DEFAULT_START_NUMBER))
    except Exception:
        return DEFAULT_START_NUMBER

# ==================== واجهة Streamlit ====================
st.set_page_config(
    page_title="Absoool Env System | استخراج الفواتير",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# دعم الاتجاه من اليمين إلى اليسار
st.markdown("""
<style>
    * {
        font-family: 'Segoe UI', 'Arial', sans-serif;
    }
    .rtl {
        direction: rtl;
        text-align: right;
    }
    .result-box {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        padding: 28px;
        border-radius: 16px;
        direction: rtl;
        text-align: right;
        font-size: 18px;
        line-height: 2.2;
        border: 2px solid #cbd5e1;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .result-box .line {
        padding: 6px 0;
        border-bottom: 1px dashed #cbd5e1;
    }
    .result-box .line:last-child {
        border-bottom: none;
    }
    .result-box .label {
        font-weight: bold;
        color: #1e40af;
        display: inline-block;
        min-width: 130px;
    }
    .result-box .value {
        color: #0f172a;
    }
    h1, h2, h3, h4 {
        direction: rtl;
        text-align: center;
    }
    .stButton > button {
        width: 100%;
    }
    .warning-item {
        background-color: #fef3c7;
        color: #92400e;
        padding: 10px 16px;
        border-radius: 8px;
        margin: 6px 0;
        border-right: 4px solid #f59e0b;
        direction: rtl;
        text-align: right;
    }
    .success-item {
        background-color: #d1fae5;
        color: #065f46;
        padding: 10px 16px;
        border-radius: 8px;
        margin: 6px 0;
        border-right: 4px solid #10b981;
        direction: rtl;
        text-align: right;
    }
    .sidebar-info {
        background-color: #1e293b;
        color: #e2e8f0;
        padding: 16px;
        border-radius: 12px;
        direction: rtl;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# الشريط الجانبي
with st.sidebar:
    st.markdown("### ⚙️ الإعدادات")
    
    # إدارة رقم الفاتورة
    if 'next_number' not in st.session_state:
        st.session_state.next_number = load_next_number()
    
    invoice_number = st.number_input(
        "رقم الفاتورة الحالية",
        min_value=1,
        value=st.session_state.next_number,
        help="يزداد الرقم تلقائياً بعد كل استخراج ناجح"
    )
    
    st.markdown("---")
    st.markdown("""
    <div class="sidebar-info">
        <h4>📋 طريقة الاستخدام</h4>
        <p>1️⃣ اختر ملف PDF للفاتورة</p>
        <p>2️⃣ تحقق من رقم الفاتورة</p>
        <p>3️⃣ اضغط استخراج البيانات</p>
        <p>4️⃣ انسخ النتيجة أو حملها</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("""
    <div class="sidebar-info">
        <h4>ℹ️ معلومات</h4>
        <p>النظام يدعم:</p>
        <p>✅ النص العربي والإنجليزي</p>
        <p>✅ الأرقام العربية والفارسية</p>
        <p>✅ تصحيح أخطاء الأحياء الشائعة</p>
    </div>
    """, unsafe_allow_html=True)

# العنوان الرئيسي
st.title("📄 Absoool Env System")
st.subheader("نظام استخراج فواتير ثنائي اللغة — متجر النسر للأحذية الراقية ")
st.markdown("---")

# المحتوى الرئيسي
col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("### 📂 اختيار ملف PDF")
    uploaded_file = st.file_uploader(
        "اسحب وأفلت ملف الفاتورة هنا أو اضغط للاختيار",
        type="pdf",
        help="يدعم ملفات PDF التي تحتوي على نص قابل للاستخراج"
    )
    
    if uploaded_file:
        st.success(f"✅ تم اختيار الملف: {uploaded_file.name}")
    
    extract_btn = st.button(
        "🚀 استخراج البيانات",
        type="primary",
        use_container_width=True,
        disabled=not uploaded_file
    )
    
    st.markdown("---")
    st.markdown("""
    <div class="rtl" style="background-color: #f1f5f9; padding: 16px; border-radius: 12px;">
        <p><strong>💡 ملاحظة هامة:</strong></p>
        <p>النظام يعمل بشكل أفضل مع ملفات PDF النصية. إذا كان الملف صورة ممسوحة ضوئياً، ستحتاج إلى إضافة تقنية OCR في مرحلة لاحقة.</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    if uploaded_file and extract_btn:
        with st.spinner("⏳ جاري قراءة واستخراج بيانات الفاتورة..."):
            try:
                # إعادة تعيين مؤشر الملف
                uploaded_file.seek(0)
                
                # استخراج النص
                text = extract_pdf_text(uploaded_file)
                
                # إعادة تعيين مرة أخرى لاستخراج المنطقة
                uploaded_file.seek(0)
                
                # استخراج البيانات
                data = extract_invoice(text, invoice_number, pdf_file=uploaded_file)
                result = format_invoice(data)
                
                # التحقق من صحة البيانات
                warnings = validate_data(data)
                
                # عرض النتيجة
                st.markdown("### ✅ نتيجة الاستخراج")
                
                if warnings:
                    st.warning("⚠️ تم العثور على بعض التنبيهات:")
                    for w in warnings:
                        st.markdown(f'<div class="warning-item">⚠️ {w}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="success-item">✅ جميع البيانات مستخرجة بنجاح!</div>', unsafe_allow_html=True)
                
                # عرض النتيجة بشكل منسق
                lines = result.split('\n')
                formatted_html = '<div class="result-box">'
                for line in lines:
                    if ':' in line:
                        label, value = line.split(':', 1)
                        formatted_html += f'<div class="line"><span class="label">{label.strip()}:</span><span class="value">{value.strip()}</span></div>'
                    else:
                        formatted_html += f'<div class="line"><span class="value">{line}</span></div>'
                formatted_html += '</div>'
                
                st.markdown(formatted_html, unsafe_allow_html=True)
                
                # تحديث رقم الفاتورة التالي
                st.session_state.next_number = invoice_number + 1
                save_settings(st.session_state.next_number)
                
                st.info(f"🔢 تم حفظ رقم الفاتورة التالي: {st.session_state.next_number}")
                
                # أزرار الإجراءات
                st.markdown("### 📌 الإجراءات")
                col_copy, col_download, col_whatsapp = st.columns(3)
                
                with col_copy:
                    st.download_button(
                        label="📋 نسخ النتيجة",
                        data=result,
                        file_name=f"فاتورة_{invoice_number}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                
                with col_download:
                    st.download_button(
                        label="💾 تحميل كملف نصي",
                        data=result,
                        file_name=f"فاتورة_{invoice_number}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                
                with col_whatsapp:
                    # إعداد رابط واتساب (يفتح في نافذة جديدة)
                    whatsapp_text = result.replace('\n', '%0A')
                    whatsapp_url = f"https://web.whatsapp.com/send?text={whatsapp_text}"
                    st.markdown(
                        f'<a href="{whatsapp_url}" target="_blank" style="text-decoration:none;">'
                        f'<button style="width:100%;padding:10px;background-color:#25D366;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:bold;">'
                        f'💬 فتح في واتساب'
                        f'</button></a>',
                        unsafe_allow_html=True
                    )
                
                # عرض النص الخام للتصحيح (اختياري)
                with st.expander("🔍 عرض النص الخام المستخرج من PDF"):
                    st.text_area("النص الكامل", text, height=300)
                
            except Exception as e:
                st.error(f"❌ حدث خطأ أثناء الاستخراج: {str(e)}")
                st.exception(e)
    
    elif not uploaded_file:
        st.info("👆 يرجى اختيار ملف PDF للبدء في استخراج البيانات")
        
        # عرض مثال توضيحي
        st.markdown("### 📋 مثال على النتيجة المتوقعة:")
        example = """اليوم: الأحد
محتوى الفاتورة رقم 8:
الاسم: وليد النهدي
الحي: العزيزية
رقم الجوال: +966595808200
رقم الطلب: 278439534
عدد الطلبات الحالية: 8"""
        
        lines = example.split('\n')
        formatted_html = '<div class="result-box">'
        for line in lines:
            if ':' in line:
                label, value = line.split(':', 1)
                formatted_html += f'<div class="line"><span class="label">{label.strip()}:</span><span class="value">{value.strip()}</span></div>'
            else:
                formatted_html += f'<div class="line"><span class="value">{line}</span></div>'
        formatted_html += '</div>'
        
        st.markdown(formatted_html, unsafe_allow_html=True)

# التذييل
st.markdown("---")
st.markdown("""
<div class="rtl" style="text-align: center; color: #64748b; padding: 20px;">
    <p>التطبيق حصري لمنتسبين مؤسسة النسر للأحذية فقط  </p>
    <p>©   Eng Abduslam Alomary —  نظام استخراج الفواتير</p>
</div>
""", unsafe_allow_html=True)
