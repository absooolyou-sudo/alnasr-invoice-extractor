"""
نظام استخراج فواتير - النسخة الرابعة (لوحة التحكم الذكية)
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
MAX_CYCLE = 50  # عدد الطلبات في الدورة الواحدة

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
    value = clean_spaces(value)
    if not value:
        return value
    arabic_count = len(re.findall(r"[\u0600-\u06ff]", value))
    latin_count = len(re.findall(r"[A-Za-z]", value))
    if latin_count > arabic_count:
        return value
    return clean_spaces(value[::-1])

def readable_lines(text: str):
    lines = [clean_spaces(line) for line in text.splitlines() if line.strip()]
    reversed_lines = [reverse_pdf_line(line) for line in lines]
    return lines, reversed_lines

def clean_value(value: str) -> str:
    if not value:
        return value
    value = normalize_digits(value)
    value = re.sub(r"^[\s:：\-–—]+", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip(" \t:،,؛")

# ==================== دوال استخراج النص ====================

def extract_pdf_text(pdf_file) -> str:
    """استخراج النص باستخدام PyMuPDF."""
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("مكتبة PyMuPDF غير مثبتة. قم بتثبيتها: pip install PyMuPDF")
    
    pdf_file.seek(0)
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    chunks = []
    
    for page in doc:
        chunks.append(page.get_text())
    
    doc.close()
    return "\n".join(chunks)

def extract_customer_region(pdf_file) -> dict:
    """استخراج بيانات العميل من منطقة محددة في الصفحة."""
    if not PYMUPDF_AVAILABLE:
        return {}
    
    pdf_file.seek(0)
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    page = doc[0]
    
    page_width = page.rect.width
    page_height = page.rect.height
    
    customer_rect = fitz.Rect(
        0, 
        page_height * 0.20, 
        page_width * 0.53, 
        page_height * 0.73
    )
    
    region_text = page.get_text(clip=customer_rect)
    doc.close()
    
    if not region_text.strip():
        return {}
    
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
        neighborhood = clean_value(matches[0])
    
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

def extract_invoice(text: str, invoice_number: int, pdf_file=None) -> dict:
    """استخراج بيانات الفاتورة من النص."""
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
    
    customer = clean_value(customer)
    
    # الحي
    neighborhood = "غير مذكور"
    neighborhood_matches = re.findall(r"حي\s+(?!شارع\b)([^،,\n]+)", readable_text)
    
    for candidate in neighborhood_matches:
        candidate = clean_value(candidate)
        if candidate and candidate not in {"الحي", "العنوان"}:
            neighborhood = candidate
            break
    
    if neighborhood == "غير مذكور":
        neighborhood = clean_value(find_first([r"الحي\s*[:：]?\s*([^\n]+)"], readable_text))
    
    # رقم الجوال
    phone = extract_phone(raw_text)
    
    # اليوم
    day_match = re.search(
        r"\b(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b",
        raw_text, re.IGNORECASE
    )
    day = DAYS.get(day_match.group(1).capitalize(), day_match.group(1)) if day_match else "غير مذكور"
    
    # حساب الموضع في الدورة الحالية
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
    
    # الأولوية لاستخراج المنطقة
    if pdf_file:
        pdf_file.seek(0)
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

# ==================== دوال إدارة الإعدادات والإحصائيات ====================

def save_settings(number: int, total_extracted: int = None):
    """حفظ الإعدادات والإحصائيات."""
    current_data = load_all_settings()
    current_data["next_invoice_number"] = number
    if total_extracted is not None:
        current_data["total_extracted"] = total_extracted
    if "total_extracted" not in current_data:
        current_data["total_extracted"] = 0
    if "today_date" not in current_data or current_data["today_date"] != datetime.now().strftime("%Y-%m-%d"):
        current_data["today_date"] = datetime.now().strftime("%Y-%m-%d")
        current_data["today_count"] = 0
    
    STATE_FILE.write_text(
        json.dumps(current_data, ensure_ascii=False, indent=2),
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
        return data
    except Exception:
        return {
            "next_invoice_number": DEFAULT_START_NUMBER,
            "total_extracted": 0,
            "today_date": datetime.now().strftime("%Y-%m-%d"),
            "today_count": 0,
        }

def load_next_number() -> int:
    data = load_all_settings()
    return int(data.get("next_invoice_number", DEFAULT_START_NUMBER))

def increment_stats():
    """زيادة الإحصائيات بعد عملية استخراج ناجحة."""
    data = load_all_settings()
    data["total_extracted"] = data.get("total_extracted", 0) + 1
    if data.get("today_date") == datetime.now().strftime("%Y-%m-%d"):
        data["today_count"] = data.get("today_count", 0) + 1
    else:
        data["today_date"] = datetime.now().strftime("%Y-%m-%d")
        data["today_count"] = 1
    STATE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

# ==================== دوال لوحة التحكم ====================

def get_cycle_progress(current_number: int) -> float:
    """حساب نسبة التقدم في الدورة الحالية (من 0 إلى 1)."""
    position = ((current_number - 1) % MAX_CYCLE) + 1
    return position / MAX_CYCLE

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

# ==================== واجهة Streamlit ====================

st.set_page_config(
    page_title="نظام النسر | استخراج الفواتير",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS لدعم الاتجاه من اليمين إلى اليسار + التصميم + الشارتات
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
    .dashboard-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
        color: white;
        padding: 20px;
        border-radius: 16px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        border: 1px solid rgba(255,255,255,0.1);
    }
    .dashboard-card .card-icon {
        font-size: 36px;
        margin-bottom: 8px;
    }
    .dashboard-card .card-value {
        font-size: 32px;
        font-weight: bold;
        margin: 8px 0;
    }
    .dashboard-card .card-label {
        font-size: 14px;
        opacity: 0.85;
    }
    .dashboard-card.green {
        background: linear-gradient(135deg, #065f46 0%, #064e3b 100%);
    }
    .dashboard-card.gold {
        background: linear-gradient(135deg, #92400e 0%, #78350f 100%);
    }
    .dashboard-card.purple {
        background: linear-gradient(135deg, #5b21b6 0%, #4c1d95 100%);
    }
    .cycle-container {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        padding: 24px;
        border-radius: 16px;
        text-align: center;
        border: 2px solid #f59e0b;
    }
    .cycle-title {
        font-size: 18px;
        font-weight: bold;
        color: #92400e;
        margin-bottom: 12px;
    }
    .cycle-info {
        display: flex;
        justify-content: space-around;
        margin-top: 16px;
    }
    .cycle-info-item {
        text-align: center;
    }
    .cycle-info-value {
        font-size: 24px;
        font-weight: bold;
        color: #78350f;
    }
    .cycle-info-label {
        font-size: 13px;
        color: #92400e;
    }
    .progress-custom {
        height: 24px;
        background-color: #e5e7eb;
        border-radius: 12px;
        overflow: hidden;
        margin: 12px 0;
    }
    .progress-custom-bar {
        height: 100%;
        background: linear-gradient(90deg, #f59e0b 0%, #ef4444 100%);
        border-radius: 12px;
        transition: width 0.5s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: bold;
        font-size: 12px;
    }
    .footer {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0;
        padding: 24px;
        border-radius: 16px;
        text-align: center;
        margin-top: 40px;
        direction: rtl;
    }
    .footer .name {
        font-size: 18px;
        font-weight: bold;
        margin-bottom: 8px;
        color: #fbbf24;
    }
    .footer .title {
        font-size: 14px;
        opacity: 0.9;
        margin-bottom: 4px;
    }
    .footer .english {
        font-size: 13px;
        opacity: 0.75;
        margin-top: 8px;
        direction: ltr;
    }
    .footer .divider {
        width: 60px;
        height: 2px;
        background: #fbbf24;
        margin: 12px auto;
        border-radius: 1px;
    }
    .copy-toast {
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background-color: #10b981;
        color: white;
        padding: 12px 24px;
        border-radius: 8px;
        z-index: 9999;
        animation: fadeInOut 2s ease-in-out;
        font-weight: bold;
    }
    @keyframes fadeInOut {
        0% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
        15% { opacity: 1; transform: translateX(-50%) translateY(0); }
        85% { opacity: 1; transform: translateX(-50%) translateY(0); }
        100% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
    }
    .section-title {
        direction: rtl;
        text-align: right;
        color: #1e3a5f;
        font-size: 20px;
        font-weight: bold;
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 3px solid #fbbf24;
        display: inline-block;
    }
    .upload-section {
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        padding: 24px;
        border-radius: 16px;
        border: 2px dashed #3b82f6;
    }
</style>

<script>
function copyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    textArea.style.direction = 'rtl';
    document.body.appendChild(textArea);
    textArea.select();
    
    try {
        document.execCommand('copy');
        showToast('✅ تم النسخ بنجاح!');
    } catch (err) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('✅ تم النسخ بنجاح!');
        }).catch(() => {
            showToast('❌ فشل النسخ، يرجى النسخ يدوياً');
        });
    }
    
    document.body.removeChild(textArea);
}

function showToast(message) {
    const existing = document.querySelector('.copy-toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = 'copy-toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 2000);
}
</script>
""", unsafe_allow_html=True)

# ==================== تهيئة حالة الجلسة ====================
if 'next_number' not in st.session_state:
    st.session_state.next_number = load_next_number()

if 'settings_data' not in st.session_state:
    st.session_state.settings_data = load_all_settings()

# ==================== الشريط الجانبي ====================
with st.sidebar:
    st.markdown("### ⚙️ الإعدادات")
    
    invoice_number = st.number_input(
        "رقم الفاتورة الحالية",
        min_value=1,
        value=st.session_state.next_number,
        help="يزداد الرقم تلقائياً بعد كل استخراج ناجح"
    )
    
    st.markdown("---")
    
    # معلومات سريعة في الشريط الجانبي
    cycle_info = get_cycle_info(invoice_number)
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

# بطاقات الإحصائيات
col1, col2, col3, col4 = st.columns(4)

settings = st.session_state.settings_data
cycle_info = get_cycle_info(invoice_number)

with col1:
    st.markdown(f"""
    <div class="dashboard-card">
        <div class="card-icon">📄</div>
        <div class="card-value">{invoice_number}</div>
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

# شارت الدورة الكبير
col_cycle1, col_cycle2 = st.columns([2, 1])

with col_cycle1:
    st.markdown(f"""
    <div class="cycle-container">
        <div class="cycle-title">🔄 تقدم الدورة الحالية (كل {MAX_CYCLE} طلب تبدأ دورة جديدة)</div>
        <div class="progress-custom" style="height: 32px;">
            <div class="progress-custom-bar" style="width: {cycle_info['progress']*100:.0f}%; font-size: 14px;">
                الطلب {cycle_info['current_position']} من {MAX_CYCLE} — {cycle_info['progress']*100:.0f}%
            </div>
        </div>
        <div class="cycle-info">
            <div class="cycle-info-item">
                <div class="cycle-info-value">{cycle_info['current_position']}</div>
                <div class="cycle-info-label">الطلب الحالي</div>
            </div>
            <div class="cycle-info-item">
                <div class="cycle-info-value">{cycle_info['remaining']}</div>
                <div class="cycle-info-label">متبقي في الدورة</div>
            </div>
            <div class="cycle-info-item">
                <div class="cycle-info-value">{cycle_info['cycle_number']}</div>
                <div class="cycle-info-label">رقم الدورة</div>
            </div>
            <div class="cycle-info-item">
                <div class="cycle-info-value">{MAX_CYCLE}</div>
                <div class="cycle-info-label">حد الدورة</div>
            </div>
        </div>
        {"<div style='margin-top: 12px; padding: 8px; background: #fef2f2; color: #991b1b; border-radius: 8px; font-weight: bold;'>🎉 ستبدأ دورة جديدة مع الطلب القادم!</div>" if cycle_info['next_reset'] else ""}
    </div>
    """, unsafe_allow_html=True)

with col_cycle2:
    # شارت دائري بسيط باستخدام CSS
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
        help="اختر ملف PDF للفاتورة لاستخراج البيانات منه"
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
    if uploaded_file and extract_btn:
        # شريط تقدم الاستخراج
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # الخطوة 1: قراءة الملف
        status_text.text("⏳ الخطوة 1/3: جاري قراءة ملف PDF...")
        progress_bar.progress(20)
        
        try:
            # استخراج النص
            text = extract_pdf_text(uploaded_file)
            progress_bar.progress(50)
            status_text.text("⏳ الخطوة 2/3: جاري تحليل واستخراج البيانات...")
            
            # استخراج البيانات المنظمة
            uploaded_file.seek(0)
            data = extract_invoice(text, invoice_number, pdf_file=uploaded_file)
            result = format_invoice(data)
            
            progress_bar.progress(80)
            status_text.text("⏳ الخطوة 3/3: جاري تنسيق النتائج...")
            
            # تحديث الإحصائيات
            st.session_state.next_number = invoice_number + 1
            save_settings(st.session_state.next_number)
            increment_stats()
            st.session_state.settings_data = load_all_settings()
            
            progress_bar.progress(100)
            status_text.text("✅ تم الانتهاء!")
            
            # عرض النتيجة
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
            
            # أزرار الإجراءات
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
                st.download_button(
                    label="💾 تحميل كملف نصي",
                    data=result,
                    file_name=f"فاتورة_{invoice_number}.txt",
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
            
            # تحديث الصفحة لعرض الإحصائيات الجديدة
            st.rerun()
            
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"❌ حدث خطأ أثناء الاستخراج: {str(e)}")
    
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

# ==================== التذييل - حقوق الملكية ====================
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
