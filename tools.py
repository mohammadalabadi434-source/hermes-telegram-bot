from langchain.tools import tool
from duckduckgo_search import DDGS

@tool
def web_search(query: str) -> str:
    """ابحث على الإنترنت عن معلومات حديثة"""
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=4)
            formatted = []
            for r in results:
                formatted.append(f"عنوان: {r['title']}\n{r['body']}\nرابط: {r.get('href', 'لا يوجد')}")
            return "\n\n".join(formatted)
    except Exception as e:
        return f"خطأ في البحث: {str(e)}"


@tool
def calculator(expression: str) -> str:
    """احسب أي عملية رياضية. مثال: 25 * 4 + 10 أو 100 / 5"""
    try:
        # للأمان: لا نسمح بأي أكواد خطيرة
        allowed = {"__builtins__": {}}
        return str(eval(expression, allowed))
    except:
        return "تعبير غير صالح، جرب مرة ثانية"
