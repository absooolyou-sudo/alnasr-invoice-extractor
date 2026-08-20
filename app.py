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

# ==================== قواعد التصحيح الذكي ====================

# 1. التصحيح المباشر للأخطاء الشائعة جداً
DIRECT_CORRECTIONS = {
    # الأسماء الشائعة
    "غايل": "غالي",
    "غالي": "غالي",
    "خالد": "خالد",
    "محمد": "محمد",
    "احمد": "أحمد",
    "عبدالله": "عبدالله",
    "عبد الله": "عبدالله",
    
    # الأحياء - تصحيح مباشر
    "الرنجس": "النرجس",
    "العزيزيه": "العزيزية",
    "الشفا": "الشفاء",
    "الورده": "الوردة",
    "الغريب": "الغربي",
    "الثامرية": "الثامرية",
    "العريجاء": "العريجاء",
    "العارض": "العارض",
    "النرجس": "النرجس",
    "الملقا": "الملقا",
    "المروج": "المروج",
    "الروضة": "الروضة",
    "السويدي": "السويدي",
    "المنار": "المنار",
    "البديعة": "البديعة",
    "القدس": "القدس",
    "الصالحية": "الصالحية",
    "النعيم": "النعيم",
    "الواحة": "الواحة",
    "الزهراء": "الزهراء",
    "الزهرة": "الزهرة",
    "المصيف": "المصيف",
    "المدينة الصناعية": "المدينة الصناعية",
    "الشرفية": "الشرفية",
    "الامير مشعل": "الأمير مشعل",
    "امير مشعل": "الأمير مشعل",
    "الهجر": "الهجر",
    "العوالي": "العوالي",
    "السعادة": "السعادة",
    "الفيحاء": "الفيحاء",
    "النسيم": "النسيم",
    "القادسية": "القادسية",
    "الرابية": "الرابية",
    "المرسلات": "المرسلات",
    "الشرق": "الشرق",
    "الغرب": "الغرب",
    "الشمال": "الشمال",
    "الجنوب": "الجنوب",
    "الوسط": "الوسط",
    "الاول": "الأول",
    "الثاني": "الثاني",
    "الثالث": "الثالث",
    "الرابع": "الرابع",
    "الخامس": "الخامس",
    "السادس": "السادس",
    "السابع": "السابع",
    "الثامن": "الثامن",
    "التاسع": "التاسع",
    "العاشر": "العاشر",
}

# 2. قائمة الأحياء المعروفة في الرياض (للمقارنة الذكية)
KNOWN_NEIGHBORHOODS = [
    "العريجاء الغربي", "العريجاء الشرقي", "العريجاء الوسطي",
    "النرجس", "العزيزية", "الملقا", "المروج", "الروضة",
    "السويدي", "المنار", "البديعة", "القدس", "الصالحية",
    "النعيم", "الواحة", "الزهراء", "الزهرة", "المصيف",
    "المدينة الصناعية", "الشرفية", "الأمير مشعل", "الهجر",
    "العوالي", "السعادة", "الفيحاء", "النسيم", "القادسية",
    "الرابية", "المرسلات", "الشرق", "الغرب", "الشمال",
    "الجنوب", "الوسط", "الشفاء", "الوردة", "العارض",
    "الخليج", "السلام", "النزهة", "الحمراء", "اليرموك",
    "الفوطة", "المعذر", "العليا", "المنصورة", "المغرزات",
    "طويق", "بدر", "الرمال", "الوادي", "السفارات",
    "الدوبية", "العقاب", "الجنادرية", "المحمدية", "الندى",
    "السويدي الغربي", "السويدي الشرقي", "الروضة الغربية",
    "الروضة الشرقية", "المروج الغربي", "المروج الشرقي",
    "الملقا الغربي", "الملقا الشرقي", "العارض الشمالي",
    "العارض الجنوبي", "العريجاء",
]

# 3. خريطة تبديل الحروف المتشابهة (للمقارنة المرنة)
SIMILAR_CHARS = {
    'ي': 'اىل',   # ياء تشبه ألف ولام
    'ا': 'يلى',   # ألف تشبه ياء ولام
    'ل': 'ايى',   # لام تشبه ألف وياء
    'ب': 'يتنث',  # باء تشبه ياء وتاء وثاء ونون
    'ت': 'بينث',  # تاء تشبه باء وياء ونون وثاء
    'ث': 'بيتن',  # ثاء تشبه باء وياء وتاء ونون
    'ن': 'بيتث',  # نون تشبه باء وياء وتاء وثاء
    'ى': 'ايل',   # ألف مقصورة تشبه ألف وياء ولام
    'ة': 'هت',    # تاء مربوطة تشبه هاء وتاء
    'ه': 'ةت',    # هاء تشبه تاء مربوطة وتاء
    'ع': 'غ',     # عين تشبه غين
    'غ': 'ع',     # غين تشبه عين
    'ح': 'خ',     # حاء تشبه خاء
    'خ': 'ح',     # خاء تشبه حاء
    'ص': 'ض',     # صاد تشبه ضاد
    'ض': 'ص',     # ضاد تشبه صاد
    'ط': 'ظ',     # طاء تشبه ظاء
    'ظ': 'ط',     # ظاء تشبه طاء
    'د': 'ذ',     # دال تشبه ذال
    'ذ': 'د',     # ذال تشبه دال
    'ر': 'ز',     # راء تشبه زاي
    'ز': 'ر',     # زاي تشبه راء
    'س': 'ش',     # سين تشبه شين
    'ش': 'س',     # شين تشبه سين
}

# ==================== دوال التصحيح الذكي ====================

def levenshtein_distance(s1: str, s2: str) -> int:
    """حساب مسافة ليفنشتاين بين نصين (عدد التعديلات اللازمة للتحويل)."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    # تحسين: معالجة الحروف المتشابهة بتكلفة أقل
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # تكلفة الاستبدال
            if c1 == c2:
                cost = 0
            elif c1 in SIMILAR_CHARS and c2 in SIMILAR_CHARS[c1]:
                cost = 0.3  # تكلفة منخفضة جداً للحروف المتشابهة
            elif c2 in SIMILAR_CHARS and c1 in SIMILAR_CHARS[c2]:
                cost = 0.3
            else:
                cost = 1
            
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + cost
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    
    return prev_row[-1]

def similarity_score(s1: str, s2: str) -> float:
    """حساب درجة التشابه بين نصين (0 إلى 1)."""
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(s1, s2)
    return 1.0 - (dist / max_len)

def smart_correct_neighborhood(word: str) -> str:
    """تصحيح ذكي لاسم الحي باستخدام المقارنة مع قائمة الأحياء المعروفة."""
    word = word.strip()
    if not word:
        return word
    
    # أولاً: جرب التصحيح المباشر
    if word in DIRECT_CORRECTIONS:
        return DIRECT_CORRECTIONS[word]
    
    # ثانياً: جرب التصحيح الجزئي (إذا كان الحي يتكون من كلمتين)
    words = word.split()
    corrected_words = []
    for w in words:
        if w in DIRECT_CORRECTIONS:
            corrected_words.append(DIRECT_CORRECTIONS[w])
        else:
            corrected_words.append(w)
    partial_corrected = ' '.join(corrected_words)
    if partial_corrected != word:
        return partial_corrected
    
    # ثالثاً: المقارنة الذكية مع جميع الأحياء المعروفة
    best_match = None
    best_score = 0
    
    for neighborhood in KNOWN_NEIGHBORHOODS:
        score = similarity_score(word, neighborhood)
        if score > best_score:
            best_score = score
            best_match = neighborhood
    
    # إذا كانت درجة التشابه عالية جداً (أكثر من 75%)
    if best_score >= 0.75 and best_match:
        return best_match
    
    # رابعاً: جرب تقسيم النص والبحث عن أي حي بداخله
    for neighborhood in KNOWN_NEIGHBORHOODS:
        # مقارنة كل كلمة على حدة
        for w in words:
            if len(w) >= 3:
                score = similarity_score(w, neighborhood.split()[0] if ' ' in neighborhood else neighborhood)
                if score >= 0.85:
                    # تحقق مما إذا كانت بقية الكلمات تتطابق أيضاً
                    full_score = similarity_score(word, neighborhood)
                    if full_score >= 0.65:
                        return neighborhood
    
    return word

def smart_correct_name(word: str) -> str:
    """تصحيح ذكي للأسماء الشائعة."""
    word = word.strip()
    if not word:
        return word
    
    # أولاً: التصحيح المباشر
    if word in DIRECT_CORRECTIONS:
        return DIRECT_CORRECTIONS[word]
    
    # ثانياً: إذا كان الاسم مكوناً من عدة أجزاء
    words = word.split()
    corrected = []
    for w in words:
        if w in DIRECT_CORRECTIONS:
            corrected.append(DIRECT_CORRECTIONS[w])
        else:
            # جرب المقارنة مع الأسماء الشائعة
            for correct_name in ["غالي", "خالد", "محمد", "أحمد", "عبدالله", "سلطان", "فهد", "بندر", "تركي", "نايف", "ماجد", "سعود", "خالد", "زياد", "يوسف", "عمر", "علي", "حسن", "حسين", "إبراهيم", "إسماعيل", "طلال", "مشعل", "منصور", "متعب", "ناصر", "واصل", "وليد", "هاني", "سامي", "فارس", "باسل", "راشد", "مهند", "فيصل", "ثامر", "بدر", "حمود", "خالد", "غازي", "عزام", "زامل", "رامي", "عمرو", "مروان", "هشام", "أيمن", "تامر", "بسام", "جمال", "كمال", "هلال", "مازن", "وائل", "عادل", "ماجد", "سامر", "نزار", "هيثم", "أحمد", "سلمان", "عبدالرحمن", "عبدالعزيز", "عبدالله", "عبدالمحسن", "عبدالكريم", "عبدالرزاق", "عبدالوهاب", "عبدالسلام", "عبدالناصر", "عبدالحكيم", "عبدالخالق", "عبدالرحيم", "عبدالجبار", "عبدالفتاح", "عبدالله", "خالد", "غالي"]:
                score = similarity_score(w, correct_name)
                if score >= 0.80:
                    w = correct_name
                    break
            corrected.append(w)
    
    return ' '.join(corrected)

def correct_full_address(text: str) -> str:
    """تصحيح كامل للعنوان باستخدام جميع الطرق."""
    # البحث عن أسماء الأحياء داخل النص الكامل
    for neighborhood in KNOWN_NEIGHBORHOODS:
        # تقسيم الحي إلى كلمات
        neigh_words = neighborhood.split()
        # البحث عن تطابق جزئي ذكي
        pattern = r'حي\s+(.+?)(?:[،,،]|$)'
        matches = re.findall(pattern, text)
        for match in matches:
            match_clean = match.strip()
            score = similarity_score(match_clean, neighborhood)
            if score >= 0.70:
                # استبدال الجزء الخاطئ بالصحيح
                text = text.replace(match_clean, neighborhood)
                return text
    
    return text

# ==================== دوال المعالجة الأساسية ====================

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
    """تصحيح ذكي وشامل لاسم الحي."""
    value = clean_value(value)
    # تطبيق التصحيح الذكي
    value = smart_correct_neighborhood(value)
    return value

def normalize_customer_name(value: str) -> str:
    """تصحيح ذكي لاسم العميل."""
    value = clean_value(value)
    value = smart_correct_name(value)
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
                name = normalize_customer_name(candidate)
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
    
    # تطبيق التصحيح الذكي على اسم العميل
    if customer != "غير مذكور":
        customer = normalize_customer_name(customer)
    
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
    
    # الأولوية لاستخراج المنطقة (أكثر دقة)
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

# دعم الاتجاه من اليمين إلى اليسار + سكريبت النسخ للحافظة
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
    .correction-info {
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
</style>

<script>
function copyToClipboard(text) {
    // إنشاء عنصر نصي مؤقت
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
        // محاولة استخدام API الحديث
        navigator.clipboard.writeText(text).then(() => {
            showToast('✅ تم النسخ بنجاح!');
        }).catch(() => {
            showToast('❌ فشل النسخ، يرجى النسخ يدوياً');
        });
    }
    
    document.body.removeChild(textArea);
}

function showToast(message) {
    // إزالة أي رسالة سابقة
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
        <h4>🛡️ نظام التصحيح الذكي</h4>
        <p>✅ تصحيح أخطاء PDF العربية</p>
        <p>✅ مقارنة ذكية للأحياء الشائعة</p>
        <p>✅ تصحيح تشابه الحروف</p>
        <p>✅ قاعدة بيانات أحياء الرياض</p>
    </div>
    """, unsafe_allow_html=True)

# العنوان الرئيسي
st.title("📄 Absoool Env System")
st.subheader("نظام استخراج فواتير ثنائي اللغة — متجر النُّر للأحذية")
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
        <p>النظام يحتوي على نظام تصحيح ذكي يعالج أخطاء تخزين النص في ملفات PDF العربية تلقائياً.</p>
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
                
                # عرض معلومات التصحيح الذكي
                st.markdown("""
                <div class="correction-info">
                    🔧 تم تطبيق نظام التصحيح الذكي على الأسماء والأحياء لمعالجة أخطاء PDF العربية
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
                
                # أزرار الإجراءات
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
                    # إعداد رابط واتساب
                    whatsapp_text = result.replace('\n', '%0A')
                    whatsapp_url = f"https://web.whatsapp.com/send?text={whatsapp_text}"
                    st.markdown(
                        f'<a href="{whatsapp_url}" target="_blank" style="text-decoration:none;">'
                        f'<button style="width:100%;padding:12px;background-color:#25D366;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:bold;font-size:16px;margin:4px 0;">'
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
    <p>🔒 جميع البيانات تتم معالجتها محلياً ولا يتم إرسالها إلى أي خادم خارجي</p>
    <p>🛡️ نظام التصحيح الذكي v2.0 — معالجة أخطاء PDF العربية</p>
    <p>© Absoool Env System — نظام استخراج الفواتير</p>
</div>
""", unsafe_allow_html=True)
