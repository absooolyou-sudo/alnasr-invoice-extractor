"""
نظام النسر لاستخراج الفواتير - النسخة الخامسة (إصلاح استخراج الاسم والحي)
المهندس: عبد السلام فيصل العمري
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
import streamlit as st

# ==================== المكتبات الأساسية ====================
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None

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
MAX_CYCLE = 50

# ==================== دوال المعالجة الأساسية ====================

def normalize_digits(value: str) -> str:
    return value.translate(str.maketrans(
        ARABIC_DIGITS + PERSIAN_DIGITS,
        ENGLISH_DIGITS + ENGLISH_DIGITS
    ))

def clean_spaces(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u200f", "").replace("\u200e", "")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()

def reverse_pdf_line(value: str) -> str:
    """عكس السطر العربي فقط، مع الحفاظ على الإنجليزي."""
    value = clean_spaces(value)
    if not value:
        return value
    arabic_count = len(re.findall(r"[\u0600-\u06ff]", value))
    latin_count = len(re.findall(r"[A-Za-z]", value))
    if latin_count > arabic_count:
        return value
    return clean_spaces(value[::-1])

def readable_lines(text: str):
    """تحويل النص الخام إلى سطور مقروءة."""
    lines = [clean_spaces(line) for line in text.splitlines() if line.strip()]
    reversed_lines = [reverse_pdf_line(line) for line in lines]
    return lines, reversed_lines

def clean_value(value: str) -> str:
    """تنظيف القيمة من الرموز الزائدة."""
    if not value:
        return value
    value = normalize_digits(value)
    value = re.sub(r"^[\s:：\-–—]+", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip(" \t:،,؛")

# ==================== دوال استخراج النص ====================

def extract_pdf_text(pdf_file) -> str:
    """استخراج النص الكامل من PDF باستخدام PyMuPDF."""
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("مكتبة PyMuPDF غير مثبتة. قم بتثبيتها: pip install PyMuPDF")
    
    pdf_file.seek(0)
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    chunks = []
    
    for page in doc:
        chunks.append(page.get_text())
    
    doc.close()
    return "\n".join(chunks)

def extract_customer_region_text(pdf_file) -> str:
    """استخراج نص منطقة العميل من الصفحة باستخدام الإحداثيات."""
    if not PYMUPDF_AVAILABLE:
        return ""
    
    pdf_file.seek(0)
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    page = doc[0]
    
    page_width = page.rect.width
    page_height = page.rect.height
    
    # تجربة إحداثيات مختلفة لضمان الحصول على منطقة العميل
    # الإحداثيات الأساسية
    customer_rect = fitz.Rect(
        0, 
        page_height * 0.15, 
        page_width * 0.60, 
        page_height * 0.80
    )
    
    region_text = page.get_text(clip=customer_rect)
    doc.close()
    
    return region_text

def find_first(patterns, text, flags=re.IGNORECASE | re.MULTILINE):
    """البحث عن أول تطابق لقائمة من الأنماط."""
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return clean_spaces(match.group(1))
    return "غير مذكور"

def extract_phone(text: str) -> str:
    """استخراج رقم الجوال وتنسيقه."""
    text = normalize_digits(text)
    matches = re.findall(r"\+?\d[\d\s()\-]{8,}\d", text)
    
    for candidate in matches:
        digits = re.sub(r"\D", "", candidate)
        if digits.startswith("966") and len(digits) >= 12:
            return "+" + digits
        if digits.startswith("05") and len(digits) == 10:
            return "+966" + digits[1:]
    
    return "غير مذكور"

# ==================== دوال استخراج اسم العميل والحي (المحسنة) ====================

def extract_customer_name(raw_text: str, reversed_text: str, region_raw: str = "", region_reversed: str = "") -> str:
    """
    استخراج اسم العميل باستخدام طرق متعددة ومرنة.
    البحث في: النص الخام، النص المعكوس، نص المنطقة، نص المنطقة المعكوس.
    """
    
    # جميع النصوص الممكنة للبحث
    all_texts = [
        ("المنطقة المعكوسة", region_reversed),
        ("النص المعكوس", reversed_text),
        ("المنطقة الخام", region_raw),
        ("النص الخام", raw_text),
    ]
    
    # قائمة بأنماط البحث عن اسم العميل (الأكثر دقة أولاً)
    name_patterns = [
        # نمط: مصدرة إلى: الاسم
        r"مصدرة\s*(?:إلى|الى|إل|ال|ىل|إىل|اىل|يل)\s*[:：]?\s*([^\n،,]+)",
        # نمط: مصدرة إلى الاسم (بدون نقطتين)
        r"مصدرة\s*(?:إلى|الى|إل|ال|ىل|إىل|اىل|يل)\s+([^\n،,]+)",
        # نمط: اسم العميل: الاسم
        r"(?:اسم\s*العميل|الاسم)\s*[:：]?\s*([^\n،,]+)",
        # نمط: العميل: الاسم
        r"العميل\s*[:：]?\s*([^\n،,]+)",
        # نمط: أي سطر يحتوي على "مصدرة" متبوع بسطر يحتوي على اسم
        r"مصدرة[^\n]*\n\s*([^\n،,]{2,50})",
    ]
    
    # الطريقة الأولى: البحث بالأنماط في جميع النصوص
    for text_name, text_content in all_texts:
        if not text_content:
            continue
        for pattern in name_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                candidate = clean_value(match.group(1))
                # التأكد من أن الاسم ليس كلمة عامة
                if candidate and candidate not in {
                    "السعودية", "الرياض", "غير مذكور", "المتجر", "العنوان",
                    "الحي", "الجوال", "الهاتف", "الطلب", "الفاتورة"
                } and len(candidate) >= 2:
                    # إزالة أي كلمات زائدة مثل "مصدرة من"
                    candidate = candidate.split("مصدرة")[0].strip()
                    candidate = candidate.split("المتجر")[0].strip()
                    if candidate:
                        return candidate
    
    # الطريقة الثانية: البحث عن السطر الذي يأتي بعد سطر يحتوي على "مصدرة"
    for text_name, text_content in all_texts:
        if not text_content:
            continue
        lines = text_content.split('\n')
        for i, line in enumerate(lines):
            if "مصدرة" in line and i + 1 < len(lines):
                next_line = clean_value(lines[i + 1])
                if next_line and next_line not in {
                    "السعودية", "الرياض", "غير مذكور", "", "المتجر"
                } and len(next_line) >= 2:
                    # التأكد من أن السطر التالي ليس عنوان المتجر
                    if "المتجر" not in next_line and "لأحذية" not in next_line and "النسر" not in next_line:
                        return next_line
    
    # الطريقة الثالثة: البحث الاحتياطي - أخذ أول سطر عربي طويل بعد "مصدرة"
    for text_name, text_content in all_texts:
        if not text_content:
            continue
        # تقسيم النص إلى أجزاء حول كلمة "مصدرة"
        parts = re.split(r"مصدرة", text_content)
        if len(parts) >= 2:
            # الجزء الثاني يحتوي على ما بعد كلمة مصدرة الأولى (العميل)
            after_first = parts[1]
            # البحث عن أول سطر يحتوي على أحرف عربية
            for line in after_first.split('\n'):
                line_clean = clean_value(line)
                if line_clean and len(re.findall(r"[\u0600-\u06ff]", line_clean)) >= 3:
                    if line_clean not in {"السعودية", "الرياض"} and "المتجر" not in line_clean:
                        # إزالة أي كلمات زائدة
                        line_clean = line_clean.split("،")[0].split(",")[0].strip()
                        if line_clean and len(line_clean) >= 2:
                            return line_clean
    
    return "غير مذكور"

def extract_neighborhood(raw_text: str, reversed_text: str, region_raw: str = "", region_reversed: str = "") -> str:
    """
    استخراج اسم الحي باستخدام طرق متعددة ومرنة.
    """
    
    all_texts = [
        ("المنطقة المعكوسة", region_reversed),
        ("النص المعكوس", reversed_text),
        ("المنطقة الخام", region_raw),
        ("النص الخام", raw_text),
    ]
    
    # الطريقة الأولى: البحث عن نمط "حي + اسم الحي"
    neighborhood_patterns = [
        r"حي\s+(?!شارع\b)([^،,\n]+)",
        r"حي\s*[:：]?\s*([^،,\n]+)",
        r"(?:الحي|الحياء)\s*[:：]?\s*([^،,\n]+)",
    ]
    
    for text_name, text_content in all_texts:
        if not text_content:
            continue
        for pattern in neighborhood_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE)
            for candidate in matches:
                candidate = clean_value(candidate)
                if candidate and candidate not in {
                    "الحي", "العنوان", "غير مذكور", "", "شارع"
                } and len(candidate) >= 2:
                    # تنظيف الاسم من أي زوائد
                    candidate = candidate.split("،")[0].split(",")[0].strip()
                    candidate = candidate.split("شارع")[0].strip()
                    if candidate and len(candidate) >= 2:
                        return candidate
    
    # الطريقة الثانية: البحث عن أسماء أحياء شائعة مباشرة
    common_neighborhoods = [
        "العريجاء الغربي", "العريجاء الشرقي", "العريجاء الوسطي", "العريجاء",
        "النرجس", "العزيزية", "الملقا", "المروج", "الروضة", "السويدي",
        "المنار", "البديعة", "القدس", "الصالحية", "النعيم", "الواحة",
        "الزهراء", "الزهرة", "المصيف", "الشرفية", "الأمير مشعل",
        "الهجر", "العوالي", "السعادة", "الفيحاء", "النسيم", "القادسية",
        "الرابية", "المرسلات", "الشفاء", "الوردة", "العارض",
        "الخليج", "السلام", "النزهة", "الحمراء", "اليرموك",
        "الفوطة", "المعذر", "العليا", "المنصورة", "المغرزات",
        "طويق", "بدر", "الرمال", "الوادي", "السفارات",
        "الدوبية", "العقاب", "الجنادرية", "المحمدية", "الندى",
        "الغربي", "الشرقي", "الوسطي", "الشمالي", "الجنوبي",
    ]
    
    for text_name, text_content in all_texts:
        if not text_content:
            continue
        text_clean = clean_spaces(text_content)
        for neighborhood in common_neighborhoods:
            # البحث عن تطابق جزئي ذكي
            if neighborhood in text_clean:
                return neighborhood
    
    # الطريقة الثالثة: البحث عن أي كلمة تسبقها "حي" في النص الكامل
    for text_name, text_content in all_texts:
        if not text_content:
            continue
        # تقسيم النص إلى كلمات والبحث عن كلمة "حي"
        words = text_content.split()
        for i, word in enumerate(words):
            if "حي" in word and i + 1 < len(words):
                next_word = clean_value(words[i + 1])
                if next_word and len(next_word) >= 2:
                    # جمع الكلمات التالية التي قد تكون جزءاً من اسم الحي
                    full_name = next_word
                    for j in range(i + 2, min(i + 5, len(words))):
                        extra = clean_value(words[j])
                        if extra and extra not in {"،", ",", "شارع", "رقم", "الرمز"}:
                            full_name += " " + extra
                        else:
                            break
                    full_name = full_name.split("،")[0].split(",")[0].strip()
                    if len(full_name) >= 2:
                        return full_name
    
    return "غير مذكور"

# ==================== الدالة الرئيسية لاستخراج الفاتورة ====================

def extract_invoice(text: str, invoice_number: int, pdf_file=None) -> dict:
    """استخراج جميع بيانات الفاتورة."""
    
    text = normalize_digits(text)
    raw_lines, reversed_lines = readable_lines(text)
    raw_text = "\n".join(raw_lines)
    readable_text = "\n".join(reversed_lines)
    
    # استخراج نص منطقة العميل إذا كان ملف PDF متاحاً
    region_raw = ""
    region_reversed = ""
    if pdf_file:
        pdf_file.seek(0)
        region_raw = extract_customer_region_text(pdf_file)
        if region_raw:
            _, region_rev_lines = readable_lines(region_raw)
            region_reversed = "\n".join(region_rev_lines)
    
    # ==================== رقم الطلب ====================
    order_number = find_first([
        r"(\d{6,})\s*[:：]?\s*رقم\s*الطلب",
        r"(\d{6,})\s*[:：]?\s*بلطلا\s*مقر",
        r"رقم\s*الطلب\s*[:：]?\s*(\d{6,})",
    ], raw_text)
    
    if order_number == "غير مذكور":
        order_number = find_first([r"رقم\s*الطلب\s*[:：]?\s*(\d{6,})"], readable_text)
    
    # ==================== اسم العميل (المحسن) ====================
    customer = extract_customer_name(raw_text, readable_text, region_raw, region_reversed)
    
    # ==================== اسم الحي (المحسن) ====================
    neighborhood = extract_neighborhood(raw_text, readable_text, region_raw, region_reversed)
    
    # ==================== رقم الجوال ====================
    phone = extract_phone(raw_text)
    
    # ==================== اليوم ====================
    day_match = re.search(
        r"\b(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b",
        raw_text, re.IGNORECASE
    )
    day = DAYS.get(day_match.group(1).capitalize(), day_match.group(1)) if day_match else "غير مذكور"
    
    # ==================== معلومات الدورة ====================
    cycle_position = ((invoice_number - 1) % MAX_CYCLE) + 1
    cycle_number = ((invoice_number - 1) // MAX_CYCLE) + 1
    
    result = {
        "اليوم": day,
        "رقم الفاتورة": str(invoice_number),
        "الاسم": customer,
        "الحي": neighborhood,
        "رقم الجوال": phone,
        "رقم الطلب": order_number,
        "عدد الطلبات الحالية": str(invoice_number),
        "الموضع في الدورة": str(cycle_position),
        "رقم الدورة": str(cycle_number),
    }
    
    return result

def format_invoice(data: dict) -> str:
    """تنسيق بيانات الفاتورة كنص منظم."""
    return "\n".join([
        f"اليوم: {data['اليوم']}",
        f"محتوى الفاتورة رقم {data['رقم الفاتورة']}:",
        f"الاسم: {data['الاسم']}",
        f"الحي: {data['الحي']}",
        f"رقم الجوال: {data['رقم الجوال']}",
        f"رقم الطلب: {data['رقم الطلب']}",
        f"عدد الطلبات الحالية: {data['عدد الطلبات الحالية']}",
    ])

# ==================== دوال إدارة الإعدادات والإحصائيات ====================

def save_full_settings(data: dict):
    """حفظ جميع الإعدادات والإحصائيات."""
    STATE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def load_all_settings() -> dict:
    """تحميل جميع الإعدادات والإحصائيات."""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if "total_extracted" not in data:
            data["total_extracted"] = 0
        if "today_date" not in data or data["today_date"] != datetime.now().strftime("%Y-%m-%d"):
            data["today_date"] = datetime.now().strftime("%Y-%m-%d")
            data["today_count"] = 0
        if "today_count" not in data:
            data["today_count"] = 0
        if "next_invoice_number" not in data:
            data["next_invoice_number"] = DEFAULT_START_NUMBER
        return data
    except Exception:
        return {
            "next_invoice_number": DEFAULT_START_NUMBER,
            "total_extracted": 0,
            "today_date": datetime.now().strftime("%Y-%m-%d"),
            "today_count": 0,
        }

def increment_stats_and_save(next_number: int):
    """زيادة الإحصائيات وحفظها."""
    data = load_all_settings()
    data["next_invoice_number"] = next_number
    data["total_extracted"] = data.get("total_extracted", 0) + 1
    if data.get("today_date") == datetime.now().strftime("%Y-%m-%d"):
        data["today_count"] = data.get("today_count", 0) + 1
    else:
        data["today_date"] = datetime.now().strftime("%Y-%m-%d")
        data["today_count"] = 1
    save_full_settings(data)
    return data

# ==================== دوال لوحة التحكم ====================

def get_cycle_info(current_number: int) -> dict:
    """الحصول على معلومات الدورة الحالية."""
    cycle_num = ((current_number - 1) // MAX_CYCLE) + 1
    position = ((current_number - 1) % MAX_CYCLE) + 1
    remaining = MAX_CYCLE - position
    return {
        "cycle_number": cycle_num,
        "current_position": position,
        "remaining": remaining,
        "progress": position / MAX_CYCLE,
        "next_reset": position == MAX_CYCLE
    }

# ==================== تهيئة حالة الجلسة ====================
if 'settings_data' not in st.session_state:
    st.session_state.settings_data = load_all_settings()

if 'next_number' not in st.session_state:
    st.session_state.next_number = int(st.session_state.settings_data.get("next_invoice_number", DEFAULT_START_NUMBER))

if 'extraction_result' not in st.session_state:
    st.session_state.extraction_result = None

if 'extraction_data' not in st.session_state:
    st.session_state.extraction_data = None

# ==================== واجهة Streamlit ====================

st.set_page_config(
    page_title="نظام النسر | استخراج الفواتير",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS والتصميم
st.markdown("""
<style>
    * { font-family: 'Segoe UI', 'Arial', sans-serif; }
    .rtl { direction: rtl; text-align: right; }
    .result-box {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        padding: 28px; border-radius: 16px; direction: rtl; text-align: right;
        font-size: 18px; line-height: 2.2; border: 2px solid #cbd5e1;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .result-box .line { padding: 6px 0; border-bottom: 1px dashed #cbd5e1; }
    .result-box .line:last-child { border-bottom: none; }
    .result-box .label { font-weight: bold; color: #1e40af; display: inline-block; min-width: 130px; }
    .result-box .value { color: #0f172a; }
    h1, h2, h3, h4 { direction: rtl; text-align: center; }
    .stButton > button { width: 100%; }
    .dashboard-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
        color: white; padding: 20px; border-radius: 16px; text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.1);
    }
    .dashboard-card .card-icon { font-size: 36px; margin-bottom: 8px; }
    .dashboard-card .card-value { font-size: 32px; font-weight: bold; margin: 8px 0; }
    .dashboard-card .card-label { font-size: 14px; opacity: 0.85; }
    .dashboard-card.green { background: linear-gradient(135deg, #065f46 0%, #064e3b 100%); }
    .dashboard-card.gold { background: linear-gradient(135deg, #92400e 0%, #78350f 100%); }
    .dashboard-card.purple { background: linear-gradient(135deg, #5b21b6 0%, #4c1d95 100%); }
    .cycle-container {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        padding: 24px; border-radius: 16px; text-align: center; border: 2px solid #f59e0b;
    }
    .cycle-title { font-size: 18px; font-weight: bold; color: #92400e; margin-bottom: 12px; }
    .cycle-info { display: flex; justify-content: space-around; margin-top: 16px; }
    .cycle-info-item { text-align: center; }
    .cycle-info-value { font-size: 24px; font-weight: bold; color: #78350f; }
    .cycle-info-label { font-size: 13px; color: #92400e; }
    .progress-custom {
        height: 24px; background-color: #e5e7eb; border-radius: 12px;
        overflow: hidden; margin: 12px 0;
    }
    .progress-custom-bar {
        height: 100%; background: linear-gradient(90deg, #f59e0b 0%, #ef4444 100%);
        border-radius: 12px; transition: width 0.5s ease;
        display: flex; align-items: center; justify-content: center;
        color: white; font-weight: bold; font-size: 12px;
    }
    .footer {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0; padding: 24px; border-radius: 16px;
        text-align: center; margin-top: 40px; direction: rtl;
    }
    .footer .name { font-size: 18px; font-weight: bold; margin-bottom: 8px; color: #fbbf24; }
    .footer .title { font-size: 14px; opacity: 0.9; margin-bottom: 4px; }
    .footer .english { font-size: 13px; opacity: 0.75; margin-top: 8px; direction: ltr; }
    .footer .divider { width: 60px; height: 2px; background: #fbbf24; margin: 12px auto; border-radius: 1px; }
    .copy-toast {
        position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
        background-color: #10b981; color: white; padding: 12px 24px;
        border-radius: 8px; z-index: 9999; animation: fadeInOut 2s ease-in-out; font-weight: bold;
    }
    @keyframes fadeInOut {
        0% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
        15% { opacity: 1; transform: translateX(-50%) translateY(0); }
        85% { opacity: 1; transform: translateX(-50%) translateY(0); }
        100% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
    }
    .section-title {
        direction: rtl; text-align: right; color: #1e3a5f; font-size: 20px;
        font-weight: bold; margin-bottom: 16px; padding-bottom: 8px;
        border-bottom: 3px solid #fbbf24; display: inline-block;
    }
    .upload-section {
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        padding: 24px; border-radius: 16px; border: 2px dashed #3b82f6;
    }
</style>

<script>
function copyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text; textArea.style.position = 'fixed';
    textArea.style.left = '-9999px'; textArea.style.direction = 'rtl';
    document.body.appendChild(textArea); textArea.select();
    try {
        document.execCommand('copy'); showToast('✅ تم النسخ بنجاح!');
    } catch (err) {
        navigator.clipboard.writeText(text).then(() => showToast('✅ تم النسخ بنجاح!'))
            .catch(() => showToast('❌ فشل النسخ، يرجى النسخ يدوياً'));
    }
    document.body.removeChild(textArea);
}
function showToast(message) {
    const existing = document.querySelector('.copy-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'copy-toast'; toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
}
</script>
""", unsafe_allow_html=True)

# ==================== الشريط الجانبي ====================
with st.sidebar:
    st.markdown("### ⚙️ الإعدادات")
    
    invoice_number = st.number_input(
        "رقم الفاتورة الحالية",
        min_value=1,
        value=st.session_state.next_number,
    )
    
    if invoice_number != st.session_state.next_number:
        st.session_state.next_number = invoice_number
    
    st.markdown("---")
    
    cycle_info = get_cycle_info(st.session_state.next_number)
    st.markdown(f"""
    <div class="cycle-container" style="padding: 16px;">
        <div class="cycle-title" style="font-size: 15px;">🔄 الدورة الحالية</div>
        <div class="cycle-info-value" style="font-size: 28px;">{cycle_info['cycle_number']}</div>
        <div style="font-size: 13px; color: #92400e; margin-top: 8px;">
            الطلب {cycle_info['current_position']} من {MAX_CYCLE}
        </div>
        <div class="progress-custom" style="height: 16px; margin-top: 12px;">
            <div class="progress-custom-bar" style="width: {cycle_info['progress']*100:.0f}%; font-size: 11px;">
                {cycle_info['progress']*100:.0f}%
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ==================== العنوان الرئيسي ====================
st.title("🦅 نظام النسر لاستخراج الفواتير")
st.subheader("Al-Nasr Invoice Extraction System")
st.markdown("---")

# ==================== لوحة التحكم الذكية ====================
st.markdown('<div class="section-title">📊 لوحة التحكم الذكية</div>', unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)
settings = st.session_state.settings_data
cycle_info = get_cycle_info(st.session_state.next_number)

with col1:
    st.markdown(f"""
    <div class="dashboard-card">
        <div class="card-icon">📄</div>
        <div class="card-value">{st.session_state.next_number}</div>
        <div class="card-label">رقم الفاتورة الحالية</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <div class="dashboard-card green">
        <div class="card-icon">📦</div>
        <div class="card-value">{settings.get('total_extracted', 0)}</div>
        <div class="card-label">إجمالي الطلبات المستخرجة</div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown(f"""
    <div class="dashboard-card gold">
        <div class="card-icon">📅</div>
        <div class="card-value">{settings.get('today_count', 0)}</div>
        <div class="card-label">طلبات اليوم</div>
    </div>
    """, unsafe_allow_html=True)
with col4:
    st.markdown(f"""
    <div class="dashboard-card purple">
        <div class="card-icon">🔄</div>
        <div class="card-value">{cycle_info['cycle_number']}</div>
        <div class="card-label">رقم الدورة الحالية</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

col_cycle1, col_cycle2 = st.columns([2, 1])
with col_cycle1:
    next_reset_html = ""
    if cycle_info['next_reset']:
        next_reset_html = "<div style='margin-top: 12px; padding: 8px; background: #fef2f2; color: #991b1b; border-radius: 8px; font-weight: bold;'>🎉 ستبدأ دورة جديدة مع الطلب القادم!</div>"
    st.markdown(f"""
    <div class="cycle-container">
        <div class="cycle-title">🔄 تقدم الدورة الحالية (كل {MAX_CYCLE} طلب تبدأ دورة جديدة)</div>
        <div class="progress-custom" style="height: 32px;">
            <div class="progress-custom-bar" style="width: {cycle_info['progress']*100:.0f}%; font-size: 14px;">
                الطلب {cycle_info['current_position']} من {MAX_CYCLE} — {cycle_info['progress']*100:.0f}%
            </div>
        </div>
        <div class="cycle-info">
            <div class="cycle-info-item"><div class="cycle-info-value">{cycle_info['current_position']}</div><div class="cycle-info-label">الطلب الحالي</div></div>
            <div class="cycle-info-item"><div class="cycle-info-value">{cycle_info['remaining']}</div><div class="cycle-info-label">متبقي في الدورة</div></div>
            <div class="cycle-info-item"><div class="cycle-info-value">{cycle_info['cycle_number']}</div><div class="cycle-info-label">رقم الدورة</div></div>
            <div class="cycle-info-item"><div class="cycle-info-value">{MAX_CYCLE}</div><div class="cycle-info-label">حد الدورة</div></div>
        </div>
        {next_reset_html}
    </div>
    """, unsafe_allow_html=True)

with col_cycle2:
    progress_pct = cycle_info['progress'] * 100
    circumference = 2 * 3.14159 * 70
    offset = circumference - (progress_pct / 100) * circumference
    st.markdown(f"""
    <div style="text-align: center; background: #f8fafc; padding: 20px; border-radius: 16px; border: 2px solid #e2e8f0;">
        <h4 style="margin-bottom: 16px; color: #1e3a5f;">نسبة إنجاز الدورة</h4>
        <svg width="180" height="180" viewBox="0 0 180 180">
            <circle cx="90" cy="90" r="70" fill="none" stroke="#e5e7eb" stroke-width="14"/>
            <circle cx="90" cy="90" r="70" fill="none" stroke="url(#gradient)" stroke-width="14"
                    stroke-dasharray="{circumference}" stroke-dashoffset="{offset}"
                    stroke-linecap="round" transform="rotate(-90 90 90)"/>
            <defs>
                <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" style="stop-color:#f59e0b"/>
                    <stop offset="100%" style="stop-color:#ef4444"/>
                </linearGradient>
            </defs>
            <text x="90" y="85" text-anchor="middle" font-size="28" font-weight="bold" fill="#1e3a5f">{progress_pct:.0f}%</text>
            <text x="90" y="108" text-anchor="middle" font-size="12" fill="#64748b">مكتمل</text>
        </svg>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ==================== قسم الاستخراج ====================
st.markdown('<div class="section-title">📂 استخراج بيانات الفاتورة</div>', unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown('<div class="upload-section">', unsafe_allow_html=True)
    st.markdown("### 📤 رفع ملف PDF")
    
    uploaded_file = st.file_uploader(
        "اختر ملف الفاتورة",
        type="pdf",
        key="pdf_uploader"
    )
    
    if uploaded_file:
        st.success(f"✅ تم اختيار الملف: {uploaded_file.name}")
    
    extract_btn = st.button(
        "🚀 استخراج البيانات",
        type="primary",
        use_container_width=True,
        disabled=not uploaded_file
    )
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    # ========== عملية الاستخراج ==========
    if uploaded_file and extract_btn:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            status_text.text("⏳ الخطوة 1/3: جاري قراءة ملف PDF...")
            progress_bar.progress(20)
            
            text = extract_pdf_text(uploaded_file)
            progress_bar.progress(50)
            status_text.text("⏳ الخطوة 2/3: جاري تحليل واستخراج البيانات...")
            
            uploaded_file.seek(0)
            data = extract_invoice(text, invoice_number, pdf_file=uploaded_file)
            result = format_invoice(data)
            
            progress_bar.progress(80)
            status_text.text("⏳ الخطوة 3/3: جاري تنسيق النتائج...")
            
            # تحديث الإحصائيات
            next_num = invoice_number + 1
            updated_settings = increment_stats_and_save(next_num)
            
            st.session_state.next_number = next_num
            st.session_state.settings_data = updated_settings
            st.session_state.extraction_result = result
            st.session_state.extraction_data = data
            
            progress_bar.progress(100)
            status_text.text("✅ تم الانتهاء بنجاح!")
            
            import time
            time.sleep(0.8)
            progress_bar.empty()
            status_text.empty()
            
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"❌ حدث خطأ أثناء الاستخراج: {str(e)}")
            st.session_state.extraction_result = None
            st.session_state.extraction_data = None
    
    # ========== عرض النتائج ==========
    if st.session_state.extraction_result:
        result = st.session_state.extraction_result
        data = st.session_state.extraction_data
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### ✅ نتيجة الاستخراج")
        
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
        
        st.info(f"🔢 رقم الفاتورة التالي: {st.session_state.next_number}")
        
        st.markdown("### 📌 الإجراءات")
        
        copy_btn_html = f"""
        <button onclick="copyToClipboard(`{result}`)" 
            style="width:100%;padding:12px;background-color:#243b53;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:bold;font-size:16px;margin:4px 0;">
            📋 نسخ النتيجة للحافظة
        </button>
        """
        st.markdown(copy_btn_html, unsafe_allow_html=True)
        
        col_download, col_whatsapp = st.columns(2)
        
        with col_download:
            current_inv_num = data.get('رقم الفاتورة', 'result') if data else 'result'
            st.download_button(
                label="💾 تحميل كملف نصي",
                data=result,
                file_name=f"فاتورة_{current_inv_num}.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        with col_whatsapp:
            whatsapp_text = result.replace('\n', '%0A')
            whatsapp_url = f"https://web.whatsapp.com/send?text={whatsapp_text}"
            st.markdown(
                f'<a href="{whatsapp_url}" target="_blank" style="text-decoration:none;">'
                f'<button style="width:100%;padding:12px;background-color:#25D366;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:bold;font-size:16px;margin:4px 0;">'
                f'💬 فتح في واتساب'
                f'</button></a>',
                unsafe_allow_html=True
            )
    
    elif not uploaded_file and not st.session_state.extraction_result:
        st.info("👆 يرجى اختيار ملف PDF للبدء في استخراج البيانات")
        
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

# ==================== التذييل ====================
st.markdown("---")
st.markdown("""
<div class="footer">
    <div class="name">🦅 نظام النسر لاستخراج الفواتير</div>
    <div class="title">Al-Nasr Invoice Extraction System</div>
    <div class="divider"></div>
    <div class="title">تم التطوير بواسطة</div>
    <div class="name">المهندس عبد السلام فيصل العمري</div>
    <div class="title">Engineer Abdul Salam Faisal Al-Omari</div>
    <div class="english">© All Rights Reserved — 2026</div>
</div>
""", unsafe_allow_html=True)
