import os
from datetime import datetime
import pytz
from langchain.tools import tool

# ===== أداة البحث (Tavily - الأفضل للـ AI agents) =====
@tool
def web_search(query: str) -> str:
    """ابحث على الإنترنت عن أي معلومات حديثة أو أخبار أو أسعار أو أحداث"""
    try:
        from tavily import TavilyClient
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return "خطأ: TAVILY_API_KEY غير موجود في متغيرات البيئة"
        
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=True  # يعطي ملخصاً تلقائياً
        )
        
        parts = []
        
        # الملخص التلقائي من Tavily
        if response.get("answer"):
            parts.append(f"📌 ملخص: {response['answer']}\n")
        
        # النتائج التفصيلية
        for i, r in enumerate(response.get("results", []), 1):
            parts.append(
                f"[{i}] {r.get('title', '')}\n"
                f"{r.get('content', '')[:300]}\n"
                f"🔗 {r.get('url', '')}"
            )
        
        return "\n\n".join(parts) if parts else "لا توجد نتائج"
    
    except Exception as e:
        return f"خطأ في البحث: {str(e)}"


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
        return (
            f"🕐 الوقت: {now.strftime('%H:%M:%S')}\n"
            f"📅 التاريخ: {days_ar[now.weekday()]}، {now.day} {months_ar[now.month-1]} {now.year}\n"
            f"🌍 المنطقة الزمنية: {timezone}"
        )
    except Exception as e:
        return f"خطأ في جلب الوقت: {str(e)}"


# ===== أداة الحاسبة =====
@tool
def calculator(expression: str) -> str:
    """احسب أي عملية رياضية. مثال: 25 * 4 + 10"""
    try:
        result = eval(expression, {"__builtins__": {}})
        return f"النتيجة: {result}"
    except:
        return "تعبير رياضي غير صالح"
