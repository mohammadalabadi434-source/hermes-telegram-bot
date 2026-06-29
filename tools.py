from langchain.tools import tool
from duckduckgo_search import DDGS
from datetime import datetime
import pytz

# ===== أداة البحث =====
@tool
def web_search(query: str) -> str:
    """ابحث على الإنترنت عن معلومات حديثة"""
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)
            formatted = []
            for r in results:
                formatted.append(f"عنوان: {r['title']}\n{r['body']}\nرابط: {r.get('href', 'لا يوجد')}")
            return "\n\n".join(formatted)
    except Exception as e:
        return f"خطأ في البحث: {str(e)}"


# ===== أداة الحاسبة =====
@tool
def calculator(expression: str) -> str:
    """احسب أي عملية رياضية. مثال: 25 * 4 + 10 أو 100 / 5"""
    try:
        allowed = {"__builtins__": {}}
        return str(eval(expression, allowed))
    except:
        return "تعبير غير صالح، جرب مرة ثانية"


# ===== أداة الوقت والتاريخ =====
@tool
def get_current_time(timezone: str = "Asia/Amman") -> str:
    """احصل على الوقت والتاريخ الحالي بدقة. يمكنك تحديد المنطقة الزمنية مثل Asia/Amman أو UTC أو Asia/Dubai"""
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
        months_ar = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                     "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
        day_name = days_ar[now.weekday()]
        month_name = months_ar[now.month - 1]
        return (
            f"🕐 الوقت الحالي: {now.strftime('%H:%M:%S')}\n"
            f"📅 التاريخ: {day_name}، {now.day} {month_name} {now.year}\n"
            f"🌍 المنطقة الزمنية: {timezone}"
        )
    except Exception as e:
        return f"خطأ في جلب الوقت: {str(e)}"
