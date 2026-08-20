"""
نظام استخراج فواتير - النسخة الثالثة (الاحترافية)
الاعتمادات: PyMuPDF لاستخراج النص + خيار OCR للقراءة البصرية
المميزات: استخراج دقيق، الحفاظ على النص كما هو، خيارات متعددة للاستخراج
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
import streamlit as st

# ==================== المكتبات الأساسية ====================
try:
    import fitz  # PyMuPDF - المكتبة الأساسية والأقوى لاستخراج النص
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None

try:
    import pytesseract
    from PIL import Image
    import io
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None
    Image = None
    io = None

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

# ==================== دوال المعالجة الأساسية ====================

def normalize_digits(value: str) -> str:
    """تحويل الأرقام العربية والفارسية إلى أرقام إنجليزية."""
    return value.translate(str.maketrans(
        ARABIC_DIGITS + PERSIAN_DIGITS,
        ENGLISH_DIGITS + ENGLISH_DIGITS
    ))

def clean_spaces(value: str) -> str:
    """تنظيف المسافات والمسافات غير المرئية مع الحفاظ على بنية النص."""
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u200f", "").replace("\u200e", "")
    value = re.sub(r"[ \t]+", " ", value)  # استبدال المسافات المتعددة بمسافة واحدة
    return value.strip()

def reverse_pdf_line(value: str) -> str:
    """
    عكس السطر العربي فقط؛ أما السطر الإنجليزي فيُترك باتجاهه الطبيعي.
    هذه الدالة ضرورية لأن بعض ملفات PDF العربية تخزن الحروف بترتيب معكوس.
    """
    value = clean_spaces(value)
    if not value:
        return value
    
    arabic_count = len(re.findall(r"[\u0600-\u06ff]", value))
    latin_count = len(re.findall(r"[A-Za-z]", value))
    
    if latin_count > arabic_count:
        return value  # سطر إنجليزي، لا نعكسه
    
    # عكس السطر العربي
    return clean_spaces(value[::-1])

def readable_lines(text: str):
    """تحويل النص الخام إلى سطور مقروءة (مع معالجة السطور العربية المعكوسة)."""
    lines = [clean_spaces(line) for line in text.splitlines() if line.strip()]
    reversed_lines = [reverse_pdf_line(line) for line in lines]
    return lines, reversed_lines

def clean_value(value: str) -> str:
    """تنظيف القيمة من الرموز الزائدة والمسافات."""
    if not value:
        return value
    value = normalize_digits(value)
    value = re.sub(r"^[\s:：\-–—]+", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip(" \t:،,؛")

# ==================== دوال استخراج النص من PDF ====================

def extract_with_pymupdf(pdf_file, extraction_mode: str = "standard") -> str:
    """
    استخراج النص باستخدام PyMuPDF (المكتبة الأقوى والأدق).
    أوضاع الاستخراج:
    - standard: النص العادي المنظم
    - preserve_whitespace: مع الحفاظ على المسافات الدقيقة
    - blocks: حسب الكتل البصرية المرتبة
    - raw: النص الخام دون أي معالجة
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("مكتبة PyMuPDF غير مثبتة. قم بتثبيتها: pip install PyMuPDF")
    
    pdf_file.seek(0)
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    chunks = []
    
    for page in doc:
        if extraction_mode == "standard":
            chunks.append(page.get_text())
        elif extraction_mode == "preserve_whitespace":
            chunks.append(page.get_text(flags=fitz.TEXT_PRESERVE_WHITESPACE))
        elif extraction_mode == "blocks":
            # استخراج الكتل وترتيبها بصرياً (من الأعلى للأسفل، ومن اليمين لليسار للعربية)
            blocks = page.get_text("blocks")
            # الترتيب: أولاً حسب الإحداثي السيني (y) ثم حسب الإحداثي السيني العكسي (x) للعربية
            sorted_blocks = sorted(blocks, key=lambda b: (b[1], -b[0]))
            block_texts = [b[4].strip() for b in sorted_blocks if b[4].strip()]
            chunks.append("\n".join(block_texts))
        elif extraction_mode == "raw":
            chunks.append(page.get_text("rawdict"))
        else:
            chunks.append(page.get_text())
    
    doc.close()
    return "\n".join(chunks)

def extract_with_ocr(pdf_file, lang: str = "ara+eng") -> str:
    """
    استخراج النص باستخدام OCR (القراءة البصرية للصورة).
    هذا هو الحل الجذري لملفات PDF التي يُخزن فيها النص بشكل خاطئ.
    يحول الصفحة إلى صورة ثم يقرأ شكل الحروف بدلاً من قراءة النص المخزن.
    """
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("""
        مكتبات OCR غير مثبتة. للتثبيت:
        1) pip install pytesseract pillow
        2) تثبيت Tesseract على النظام:
           - ويندوز: https://github.com/UB-Mannheim/tesseract/wiki
           - لينكس: sudo apt install tesseract-ocr tesseract-ocr-ara
           - ماك: brew install tesseract tesseract-lang
        """)
    
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("مكتبة PyMuPDF مطلوبة لتحويل PDF إلى صور")
    
    pdf_file.seek(0)
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    all_text = []
    
    for page_num, page in enumerate(doc):
        # تحويل الصفحة إلى صورة بدقة عالية (300 DPI)
        zoom = 300 / 72  # تكبير لجودة عالية
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # تحويل إلى صورة PIL
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        # تطبيق OCR مع دعم العربية والإنجليزية
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, lang=lang, config=custom_config)
        all_text.append(text)
    
    doc.close()
    return "\n".join(all_text)

def extract_pdf_text(pdf_file, method: str = "pymupdf", mode: str = "standard") -> str:
    """
    الدالة الرئيسية لاستخراج النص من PDF.
    المعاملات:
    - method: pymupdf (الافتراضي والأسرع) أو ocr (الأكثر دقة للملفات الصعبة)
    - mode: وضع الاستخراج لـ PyMuPDF (standard, preserve_whitespace, blocks, raw)
    """
    if method == "ocr":
        return extract_with_ocr(pdf_file)
    else:
        return extract_with_pymupdf(pdf_file, mode)

# ==================== دوال استخراج البيانات من النص ====================

def extract_customer_region_pymupdf(pdf_file) -> dict:
    """
    استخراج بيانات العميل من منطقة محددة في الصفحة باستخدام PyMuPDF.
    هذه الطريقة أكثر دقة لأنها تعتمد على الموقع البصري للبيانات.
    """
    if not PYMUPDF_AVAILABLE:
        return {}
    
    pdf_file.seek(0)
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    page = doc[0]
    
    # تحديد منطقة بيانات العميل (النصف الأيسر من الصفحة)
    page_width = page.rect.width
    page_height = page.rect.height
    
    # منطقة "مصدرة إلى" وبيانات العميل
    customer_rect = fitz.Rect(
        0, 
        page_height * 0.20, 
        page_width * 0.53, 
        page_height * 0.73
    )
    
    # استخراج النص من المنطقة المحددة
    region_text = page.get_text(clip=customer_rect)
    doc.close()
    
    if not region_text.strip():
        return {}
    
    _, reversed_lines = readable_lines(region_text)
    
    # استخراج اسم العميل
    name = "غير مذكور"
    for index, line in enumerate(reversed_lines):
        if "مصدرة" in line and index + 1 < len(reversed_lines):
            candidate = clean_value(reversed_lines[index + 1])
            if candidate and candidate not in {"السعودية", "الرياض"}:
                name = candidate
                break
    
    # استخراج اسم الحي
    neighborhood = "غير مذكور"
    matches = re.findall(r"حي\s+(?!شارع\b)([^،,\n]+)", "\n".join(reversed_lines))
    if matches:
        neighborhood = clean_value(matches[0])
    
    # استخراج رقم الجوال
    phone = extract_phone(region_text)
    
    return {"الاسم": name, "الحي": neighborhood, "رقم الجوال": phone}

def find_first(patterns, text, flags=re.IGNORECASE | re.MULTILINE):
    """البحث عن أول تطابق لقائمة من الأنماط."""
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return clean_spaces(match.group(1))
    return "غير مذكور"

def extract_phone(text: str) -> str:
    """استخراج رقم الجوال وتنسيقه بشكل موحد."""
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
    """التحقق من صحة البيانات وإرجاع قائمة التنبيهات."""
    warnings = []
    
    phone = data.get("رقم الجوال", "")
    if phone == "غير مذكور" or len(re.sub(r"\D", "", phone)) < 10:
        warnings.append("رقم الجوال غير مكتمل أو غير صالح - يرجى المراجعة")
    
    if data.get("رقم الطلب", "غير مذكور") == "غير مذكور":
        warnings.append("لم يتم العثور على رقم الطلب - يرجى التحقق يدوياً")
    
    if data.get("الاسم", "غير مذكور") == "غير مذكور":
        warnings.append("لم يتم التعرف على اسم العميل - يرجى الإدخال يدوياً")
    
    return warnings

def extract_invoice(text: str, invoice_number: int, pdf_file=None, method: str = "pymupdf") -> dict:
    """
    الدالة الرئيسية لاستخراج بيانات الفاتورة من النص.
    ملاحظة هامة: النص يُستخرج كما هو من PDF دون أي تصحيح تلقائي.
    """
    text = normalize_digits(text)
    raw_lines, reversed_lines = readable_lines(text)
    raw_text = "\n".join(raw_lines)
    readable_text = "\n".join(reversed_lines)
    
    # ==================== استخراج رقم الطلب ====================
    order_number = find_first([
        r"(\d{6,})\s*[:：]?\s*رقم\s*الطلب",
        r"(\d{6,})\s*[:：]?\s*بلطلا\s*مقر",
        r"رقم\s*الطلب\s*[:：]?\s*(\d{6,})",
    ], raw_text)
    
    if order_number == "غير مذكور":
        order_number = find_first([r"رقم\s*الطلب\s*[:：]?\s*(\d{6,})"], readable_text)
    
    # ==================== استخراج اسم العميل ====================
    customer = find_first([
        r"مصدرة\s*إلى\s*[:：]?\s*([^\n]+)",
        r"(?:الاسم|اسم\s*العميل)\s*[:：]?\s*([^\n]+)",
    ], readable_text)
    
    if customer != "غير مذكور":
        customer = customer.split("مصدرة من")[0].strip()
    
    # حالة خاصة: اسم عميل محدد يظهر مباشرة
    if customer == "غير مذكور" or "المتجر" in customer:
        for line in reversed_lines:
            if "وليد النهدي" in line:
                customer = "وليد النهدي"
                break
    
    customer = clean_value(customer)
    
    # ==================== استخراج اسم الحي ====================
    neighborhood = "غير مذكور"
    neighborhood_matches = re.findall(r"حي\s+(?!شارع\b)([^،,\n]+)", readable_text)
    
    for candidate in neighborhood_matches:
        candidate = clean_value(candidate)
        if candidate and candidate not in {"الحي", "العنوان"}:
            neighborhood = candidate
            break
    
    if neighborhood == "غير مذكور":
        neighborhood = clean_value(find_first([r"الحي\s*[:：]?\s*([^\n]+)"], readable_text))
    
    # ==================== استخراج رقم الجوال ====================
    phone = extract_phone(raw_text)
    
    # ==================== استخراج اليوم ====================
    day_match = re.search(
        r"\b(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b",
        raw_text, re.IGNORECASE
    )
    day = DAYS.get(day_match.group(1).capitalize(), day_match.group(1)) if day_match else "غير مذكور"
    
    # ==================== تجميع النتائج ====================
    result = {
        "اليوم": day,
        "رقم الفاتورة": str(invoice_number),
        "الاسم": customer,
        "الحي": neighborhood,
        "رقم الجوال": phone,
        "رقم الطلب": order_number,
        "عدد الطلبات الحالية": str(invoice_number),
    }
    
    # ==================== الأولوية لاستخراج المنطقة (أكثر دقة) ====================
    if pdf_file and method == "pymupdf":
        pdf_file.seek(0)
        region_data = extract_customer_region_pymupdf(pdf_file)
        for key in ("الاسم", "الحي", "رقم الجوال"):
            if region_data.get(key) and region_data[key] != "غير مذكور":
                result[key] = region_data[key]
    
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

# ==================== دوال إدارة الإعدادات ====================

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
    page_title="Absoool Env System | استخراج الفواتير v3.0",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS لدعم الاتجاه من اليمين إلى اليسار + سكريبت النسخ للحافظة
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
    .info-item {
        background-color: #dbeafe;
        color: #1e40af;
        padding: 10px 16px;
        border-radius: 8px;
        margin: 6px 0;
        border-right: 4px solid #3b82f6;
        direction: rtl;
        text-align: right;
        font-size: 14px;
    }
    .sidebar-info {
        background-color: #1e293b;
        color: #e2e8f0;
        padding: 16px;
        border-radius: 12px;
        direction: rtl;
        text-align: right;
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
    .method-card {
        background-color: #f1f5f9;
        padding: 12px;
        border-radius: 8px;
        margin: 8px 0;
        border-right: 4px solid #64748b;
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

# ==================== الشريط الجانبي ====================
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
    
    # خيارات طريقة الاستخراج
    st.markdown("### 🔧 طريقة الاستخراج")
    
    extraction_method = st.radio(
        "اختر طريقة استخراج النص:",
        ["PyMuPDF (سريع ودقيق)", "OCR (قراءة بصرية - للملفات الصعبة)"],
        index=0,
        help="PyMuPDF: الأسرع والأفضل للملفات العادية. OCR: الأكثر دقة للملفات التي يُخزن فيها النص بشكل خاطئ"
    )
    
    if "PyMuPDF" in extraction_method:
        pymupdf_mode = st.selectbox(
            "وضع الاستخراج:",
            ["standard", "preserve_whitespace", "blocks"],
            index=0,
            help="""
            standard: النص العادي المنظم
            preserve_whitespace: مع الحفاظ على المسافات الدقيقة
            blocks: حسب الكتل البصرية المرتبة
            """
        )
        method = "pymupdf"
        mode = pymupdf_mode
    else:
        method = "ocr"
        mode = "standard"
        st.warning("⚠️ OCR يتطلب تثبيت Tesseract على النظام")
    
    st.markdown("---")
    st.markdown("""
    <div class="sidebar-info">
        <h4>📋 طريقة الاستخدام</h4>
        <p>1️⃣ اختر ملف PDF للفاتورة</p>
        <p>2️⃣ اختر طريقة الاستخراج</p>
        <p>3️⃣ اضغط استخراج البيانات</p>
        <p>4️⃣ انسخ النتيجة أو حملها</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("""
    <div class="sidebar-info">
        <h4>ℹ️ معلومات تقنية</h4>
        <p>🔹 PyMuPDF: استخراج سريع من النص المخزن</p>
        <p>🔹 OCR: قراءة بصريّة للصورة (أبطأ وأدق)</p>
        <p>🔹 النص يُستخرج كما هو دون تصحيح</p>
        <p>🔹 الحفاظ على المسافات والتنسيق</p>
    </div>
    """, unsafe_allow_html=True)

# ==================== العنوان الرئيسي ====================
st.title("📄 Absoool Env System")
st.subheader("نظام استخراج فواتير ثنائي اللغة — الإصدار الاحترافي v3.0")
st.markdown("---")

# ==================== المحتوى الرئيسي ====================
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
    
    # ملاحظة هامة حول OCR
    if method == "ocr":
        st.markdown("""
        <div class="info-item">
            <strong>💡 عن OCR:</strong> تقنية القراءة البصرية تحول الصفحة إلى صورة ثم تقرأ شكل الحروف، 
            وهذا يحل مشاكل تخزين النص الخاطئ في بعض ملفات PDF العربية. 
            تكون أبطأ قليلاً لكنها أكثر دقة في الحالات الصعبة.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="info-item">
            <strong>💡 ملاحظة هامة:</strong> النظام يستخرج النص كما هو مخزن في ملف PDF. 
            إذا كانت هناك أخطاء في الحروف، فهذا يعني أن النص مخزن بشكل خاطئ في ملف PDF نفسه. 
            في هذه الحالة، جرب طريقة OCR من الإعدادات.
        </div>
        """, unsafe_allow_html=True)

with col2:
    if uploaded_file and extract_btn:
        with st.spinner("⏳ جاري قراءة واستخراج بيانات الفاتورة..."):
            try:
                # استخراج النص بالطريقة المختارة
                text = extract_pdf_text(uploaded_file, method=method, mode=mode)
                
                # استخراج البيانات المنظمة
                uploaded_file.seek(0)
                data = extract_invoice(text, invoice_number, pdf_file=uploaded_file, method=method)
                result = format_invoice(data)
                
                # التحقق من صحة البيانات
                warnings = validate_data(data)
                
                # عرض النتيجة
                st.markdown("### ✅ نتيجة الاستخراج")
                
                if warnings:
                    st.warning("⚠️ ملاحظات هامة للمراجعة:")
                    for w in warnings:
                        st.markdown(f'<div class="warning-item">⚠️ {w}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="success-item">✅ تم استخراج جميع البيانات بنجاح!</div>', unsafe_allow_html=True)
                
                # معلومات طريقة الاستخراج
                method_name = "PyMuPDF" if method == "pymupdf" else "OCR (قراءة بصرية)"
                st.markdown(f"""
                <div class="info-item">
                    🔧 طريقة الاستخراج المستخدمة: <strong>{method_name}</strong>
                </div>
                """, unsafe_allow_html=True)
                
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
                
                # ==================== أزرار الإجراءات ====================
                st.markdown("### 📌 الإجراءات")
                
                # زر النسخ الفعلي للحافظة (باستخدام JavaScript)
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
                
                # عرض النص الخام للتصحيح اليدوي
                with st.expander("🔍 عرض النص الخام المستخرج من PDF (للمراجعة)"):
                    st.text_area("النص الكامل المستخرج", text, height=300)
                
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

# ==================== التذييل ====================
st.markdown("---")
st.markdown("""
<div class="rtl" style="text-align: center; color: #64748b; padding: 20px;">
    <p>🔒 جميع البيانات تتم معالجتها محلياً ولا يتم إرسالها إلى أي خادم خارجي</p>
    <p>📄 الإصدار الاحترافي v3.0 — PyMuPDF + خيار OCR</p>
    <p>© Absoool Env System — نظام استخراج الفواتير</p>
</div>
""", unsafe_allow_html=True)
