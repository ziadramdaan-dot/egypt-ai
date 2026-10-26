"""
العقل المفتوح — نسخة مطوّرة
ترتيب التشغيل:
1) Claude API إذا وُجد ANTHROPIC_API_KEY أو api_key.txt: إجابات عامة + بحث ويب.
2) Ollama إذا كان مثبتًا ويعمل: نموذج محلي للمحادثة (لا يحتاج API key).
3) بدون الاثنين: بحث مجاني عبر DuckDuckGo وWikipedia، مع ردود بسيطة للتاريخ/الوقت/الحساب/التحية.

إعدادات اختيارية:
  ANTHROPIC_API_KEY      مفتاح Claude
  ANTHROPIC_MODEL        اسم الموديل (الافتراضي claude-sonnet-4-5)
  OLLAMA_URL             الافتراضي http://127.0.0.1:11434
  OLLAMA_MODEL           الافتراضي llama3.2
"""

import ast
import datetime as dt
import html
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "Egypt AI"
VERSION = "2.0"
IS_PLACEHOLDER = False

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
API_URL = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
# Anthropic's stable Messages API version header:
API_VERSION = "2023-06-01"
MAX_TOKENS = 1800
MAX_SEARCHES = 3
HISTORY_LIMIT = 12
TIMEOUT = 45
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
WIKI_USER_AGENT = "OpenBrainLearningProject/2.0 (personal assistant)"
KEY_FILES = ("api_key.txt", "api_key.txt.txt", "api_key")


class BrainError(Exception):
    user_facing = True


def _read_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    if key:
        return key, workspace
    for filename in KEY_FILES:
        path = HERE / filename
        if not path.is_file():
            continue
        try:
            lines = [x.strip() for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
        except OSError:
            continue
        if not lines:
            continue
        first = lines[0]
        if "=" in first and first.split("=", 1)[0].strip().lower() in ("api_key", "anthropic_api_key"):
            first = first.split("=", 1)[1]
        key = first.strip().strip("\"'")
        if len(lines) > 1 and lines[1].startswith("wrkspc_"):
            workspace = lines[1]
        return key, workspace
    return "", ""


def _http_json(url, payload=None, headers=None, timeout=TIMEOUT):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="GET" if data is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _local_reply(message, history):
    now = dt.datetime.now().astimezone()
    lower = message.strip().lower()
    # الهوية والردود التعريفية الخاصة بـ Egypt AI
    if re.search(r"(مين (اللي|الي) (صنعك|عملك|برمجك|طورك)|من (صنعك|طورك|برمجك)|who (made|created|built) you|who is your (creator|developer))", lower):
        return "أنا Egypt AI، مساعد ذكاء اصطناعي برمجه وطوّره زياد رمضان."
    if re.search(r"(السلام عليكم|سلام عليكم|^سلام$|^هاي$|^hello$|^hi$|^اهلا|^أهلا|^ازيك|^إزيك)", lower):
        return "أهلًا بيك! أنا Egypt AI 🇪🇬 اسألني عن أي موضوع وهحاول أساعدك بإجابة واضحة ومنظمة."
    if re.search(r"(الساعة كام|الوقت كام|time now|what time)", lower):
        return "الوقت الآن حسب جهاز السيرفر: " + now.strftime("%H:%M")
    if re.search(r"(النهارده كام|تاريخ اليوم|النهارده ايه|date today|today's date)", lower):
        return "تاريخ اليوم حسب جهاز السيرفر: " + now.strftime("%Y-%m-%d")
    if re.search(r"(الحضارة المصرية|مصر القديمة|الفراعنة|ancient egypt|egyptian civilization)", lower):
        return (
            "## الحضارة المصرية القديمة 🇪🇬\\n\\n"
            "تُعد الحضارة المصرية القديمة من أعرق حضارات العالم، ونشأت حول نهر النيل الذي ساعد على الزراعة والاستقرار وقيام المدن والدولة.\\n\\n"
            "### أهم ملامحها\\n"
            "- **الملوك والفراعنة:** حكموا مصر، وارتبطت الدولة بفترات ازدهار وتوحيد وبناء.\\n"
            "- **الأهرامات والمعابد:** من أشهر آثارها أهرامات الجيزة ومعابد الكرنك والأقصر.\\n"
            "- **الكتابة:** استخدم المصريون القدماء الهيروغليفية، إلى جانب أنظمة كتابة أخرى في فترات مختلفة.\\n"
            "- **العلوم والإدارة:** برعوا في تنظيم الري، والعمارة، والحساب، والطب، وتسجيل الضرائب والمحاصيل.\\n"
            "- **الدين والحياة بعد الموت:** أثّرت المعتقدات الدينية في الفن والعمارة والطقوس الجنائزية.\\n\\n"
            "### ليه كانت مهمة؟\\n"
            "لأنها طوّرت نظام دولة وإدارة ومشروعات هندسية وفنونًا تركت أثرًا كبيرًا في تاريخ العالم. "
            "وامتدت الحضارة المصرية عبر آلاف السنين، وتغيّرت مؤسساتها وثقافتها من عصر لآخر."
        )
    # حاسبة آمنة للتعبيرات الحسابية فقط، من دون eval.
    expr = message.strip().replace("×", "*").replace("÷", "/").replace("^", "**")
    if re.fullmatch(r"[\d\s.+\-*/()%*]+", expr) and any(c.isdigit() for c in expr):
        try:
            tree = ast.parse(expr, mode="eval")
            def calc(node):
                if isinstance(node, ast.Expression): return calc(node.body)
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return node.value
                if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                    v = calc(node.operand)
                    return v if isinstance(node.op, ast.UAdd) else -v
                if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
                    a, b = calc(node.left), calc(node.right)
                    if isinstance(node.op, ast.Add): return a + b
                    if isinstance(node.op, ast.Sub): return a - b
                    if isinstance(node.op, ast.Mult): return a * b
                    if isinstance(node.op, ast.Div): return a / b
                    if isinstance(node.op, ast.FloorDiv): return a // b
                    if isinstance(node.op, ast.Mod): return a % b
                    if isinstance(node.op, ast.Pow):
                        if abs(b) > 8 or abs(a) > 1e8: raise ValueError
                        return a ** b
                raise ValueError
            result = calc(tree)
            return f"الناتج: {result}"
        except Exception:
            return "مش قادر أحسب التعبير ده. راجع العملية والأرقام وجرب تاني."
    return None


def _history_messages(history, message):
    msgs = []
    for item in (history or [])[-HISTORY_LIMIT:]:
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), str(item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["content"] += "\n\n" + content
            else:
                msgs.append({"role": role, "content": content})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"] += "\n\n" + message
    else:
        msgs.append({"role": "user", "content": message})
    return msgs


def _ask_claude(message, history, key, workspace):
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", key):
        raise BrainError("مفتاح Claude API في api_key.txt شكله غير صحيح.")
    system = (
        "You are Egypt AI, an AI assistant developed and programmed by Ziad Ramadan. "
        "If asked who created, programmed, or developed you, answer that Ziad Ramadan did. "
        "Answer in the user's language, especially clear Egyptian Arabic when the user uses Arabic. "
        "Give direct, polished, well-organized answers using a short title and bullet points or numbered steps when useful. "
        "Do not append a Sources, References, or Where I got this answer section, and do not narrate the search process. "
        "Use web search internally for current or factual questions, then synthesize the findings into a coherent answer. "
        "Do not invent facts; if evidence is uncertain or unavailable, say so briefly. "
        "You know about Egypt and ancient Egyptian civilization, including the Nile, pharaohs, pyramids, temples, hieroglyphs, administration, science, art, and chronology. "
        "Keep answers useful, accurate, and organized."
    )
    headers = {
        "content-type": "application/json",
        "anthropic-version": API_VERSION,
        "x-api-key": key,
    }
    if workspace:
        headers["anthropic-workspace-id"] = workspace
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": _history_messages(history, message),
        "tools": [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": MAX_SEARCHES,
            "user_location": {"type": "approximate", "country": "EG", "timezone": "Africa/Cairo"},
        }],
        # Force the first action to be a web search for each substantive question.
        "tool_choice": {"type": "tool", "name": "web_search"},
    }
    try:
        blocks = []
        for _ in range(4):
            response = _http_json(API_URL, payload, headers)
            blocks.extend(response.get("content") or [])
            if response.get("stop_reason") != "pause_turn":
                break
            payload["messages"] = payload["messages"] + [{"role": "assistant", "content": blocks}]
        answer_blocks = [b for b in blocks if b.get("type") == "text" and b.get("text")]
        answer = "\n".join(b["text"] for b in answer_blocks).strip()
        sources, seen = [], set()
        for block in answer_blocks:
            for citation in block.get("citations") or []:
                url = citation.get("url")
                if url and url not in seen:
                    seen.add(url)
                    sources.append((citation.get("title") or url, url))
        if not answer:
            raise BrainError("Claude رجّع رد فاضي. جرّب صياغة السؤال بطريقة مختلفة.")
        if sources:
            answer += "\n\nالمصادر:\n" + "\n".join(f"- {title}\n  {url}" for title, url in sources[:5])
        return answer
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        if exc.code == 401:
            raise BrainError("مفتاح Claude API غير صحيح أو غير مفعّل.") from None
        if exc.code == 429:
            raise BrainError("وصلت لحد الاستخدام أو الرصيد المتاح في Claude. جرّب لاحقًا أو راجع حسابك.") from None
        raise BrainError(f"Claude API رجّع خطأ ({exc.code}). {detail[:220]}") from None
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        raise BrainError("مش قادر أوصل لـ Claude. اتأكد من الإنترنت أو جرّب بعد شوية.") from None


def _ollama_available():
    try:
        _http_json(OLLAMA_URL + "/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _ask_ollama(message, history):
    msgs = []
    for item in (history or [])[-HISTORY_LIMIT:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant") and item.get("content"):
            msgs.append({"role": item["role"], "content": str(item["content"])[:5000]})
    msgs.append({"role": "user", "content": message})
    msgs.insert(0, {"role": "system", "content":
        "You are Egypt AI, an AI assistant developed and programmed by Ziad Ramadan. "
        "If asked who created you, say Ziad Ramadan did. Answer in the user's language, preferably clear Egyptian Arabic. "
        "Write organized, direct answers with headings and bullets when useful. Do not append sources/references sections or narrate the search process. "
        "Use any supplied search results internally to form the answer; do not invent facts. "
        "You can explain Egyptian history and ancient Egyptian civilization accurately."
    })
    payload = {
        "model": OLLAMA_MODEL,
        "messages": msgs,
        "stream": False,
        "options": {"temperature": 0.6},
    }
    try:
        data = _http_json(
            OLLAMA_URL + "/api/chat",
            payload,
            {"content-type": "application/json"},
            timeout=180,
        )
        answer = ((data.get("message") or {}).get("content") or "").strip()
        if not answer:
            raise BrainError("النموذج المحلي رجّع رد فاضي.")
        return answer
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise BrainError(f"نموذج Ollama '{OLLAMA_MODEL}' مش متثبت. افتح الطرفية واكتب: ollama pull {OLLAMA_MODEL}") from None
        raise BrainError(f"في مشكلة مع Ollama ({exc.code}).") from None
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        raise BrainError("Ollama مش متاح حاليًا.") from None


class _SearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._capture = False
        self._current = None
        self._snippet = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "")
        if tag == "a" and ("result__a" in classes.split()):
            self._current = {"title": "", "url": attrs.get("href", ""), "snippet": ""}
            self._capture = True
        elif self._current and tag in ("a", "div", "td") and any(
            cls in classes.split() for cls in ("result__snippet",)
        ):
            self._snippet = True

    def handle_data(self, data):
        if self._current and self._capture:
            self._current["title"] += data
        elif self._current and self._snippet:
            self._current["snippet"] += data

    def handle_endtag(self, tag):
        if self._current and tag == "a" and self._capture:
            self._capture = False
            if self._current.get("title") and self._current.get("url"):
                self.results.append(self._current)
                self._current = None
        if tag in ("div", "td"):
            self._snippet = False


def _ddg_search(query):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": WIKI_USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=15) as response:
        page = response.read().decode("utf-8", "replace")
    parser = _SearchParser()
    parser.feed(page)
    results = []
    for item in parser.results[:5]:
        results.append({
            "title": html.unescape(item["title"]).strip(),
            "url": html.unescape(item["url"]).strip(),
            "snippet": re.sub(r"\s+", " ", html.unescape(item["snippet"])).strip(),
        })
    return results


def _wiki_search(query):
    lang = "ar" if re.search(r"[\u0600-\u06ff]", query) else "en"
    params = {
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrlimit": 3, "prop": "extracts", "exintro": 1, "explaintext": 1,
        "exlimit": 3, "exsentences": 4, "redirects": 1,
        "format": "json", "formatversion": 2,
    }
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": WIKI_USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))
    pages = (data.get("query") or {}).get("pages") or []
    if isinstance(pages, dict):
        pages = list(pages.values())
    return lang, [p for p in pages if p.get("title") and p.get("extract")]


def _search_context(message):
    """Search the web for every substantive question and return usable snippets + links."""
    try:
        results = _ddg_search(message)
        if results:
            lines = ["نتائج بحث ويب حديثة/متاحة مرتبطة بسؤال المستخدم:"]
            for item in results[:5]:
                lines.append(f"العنوان: {item['title']}\nالرابط: {item['url']}\nالمقتطف: {item['snippet']}")
            return "\n\n".join(lines), [(x['title'], x['url']) for x in results[:5]]
    except Exception:
        pass
    try:
        lang, pages = _wiki_search(message)
        if pages:
            items = []
            lines = ["نتائج من ويكيبيديا:"]
            for page in pages[:3]:
                url = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(page['title'].replace(' ', '_'))
                items.append((page['title'], url))
                lines.append(f"العنوان: {page['title']}\nالرابط: {url}\nالمقتطف: {page['extract']}")
            return "\n\n".join(lines), items
    except Exception:
        pass
    return "لم تتوفر نتائج بحث ويب في هذه المحاولة. لا تخترع مصادر أو معلومات حديثة.", []


def _append_sources(answer, sources):
    if not sources:
        return answer
    existing = answer.lower()
    if "المصادر:" in answer or "sources:" in existing:
        return answer
    return answer.rstrip() + "\n\nمصادر البحث:\n" + "\n".join(
        f"- {title}\n  {url}" for title, url in sources[:5]
    )


def _web_fallback(message):
    # بحث الويب المجاني؛ لا ينتج إجابات تركيبية مثل النموذج اللغوي لكنه يعرض نتائج وروابط.
    try:
        results = _ddg_search(message)
        if results:
            lines = ["لقيت لك نتائج بحث على الإنترنت. دي ملخصات قصيرة من النتائج، راجع الروابط للتفاصيل:"]
            for item in results[:5]:
                line = f"\n- {item['title']}\n  {item['url']}"
                if item["snippet"]:
                    line += "\n  " + item["snippet"]
                lines.append(line)
            return "\n".join(lines)
    except Exception:
        pass
    try:
        lang, pages = _wiki_search(message)
        if pages:
            top = pages[0]
            wiki_url = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(top["title"].replace(" ", "_"))
            lines = [f"من ويكيبيديا — {top['title']}:\n{top['extract']}\n\nالمصدر: {wiki_url}"]
            for page in pages[1:3]:
                lines.append(f"\nنتيجة أخرى: {page['title']}\n{f'https://{lang}.wikipedia.org/wiki/' + urllib.parse.quote(page['title'].replace(' ', '_'))}")
            return "\n".join(lines)
    except Exception:
        pass
    return (
        "مش قادر أوصل لنتائج البحث دلوقتي. لو عايز إجابات ذكية كاملة، شغّل Ollama بنموذج محلي "
        "أو أضف مفتاح Claude API. وتأكد إن الإنترنت شغال."
    )


def describe():
    key, _ = _read_key()
    if key:
        return {
            "name": "العقل المفتوح + بحث الويب",
            "version": VERSION,
            "placeholder": False,
            "note": "يبحث على الويب أولًا لكل سؤال موضوعي، ثم يستخدم النموذج لصياغة الإجابة. قد تُحتسب تكلفة API.",
            "intro": "أنا Egypt AI، اسألني عن أي موضوع.",
            "suggestions": ["اشرحلي الذكاء الاصطناعي ببساطة", "ابحث عن أحدث أخبار التكنولوجيا", "اكتب كود Python يقرأ ملف CSV", "ما الفرق بين HTML وJavaScript؟"],
        }
    if _ollama_available():
        return {
            "name": "Egypt AI",
            "version": OLLAMA_MODEL,
            "placeholder": False,
            "note": "يبحث على الويب أولًا لكل سؤال موضوعي ثم يمرر النتائج للنموذج المحلي.",
            "intro": "أنا Egypt AI، اسألني عن أي موضوع.",
            "suggestions": ["اشرحلي الذكاء الاصطناعي ببساطة", "ساعدني أتعلم Python", "ترجم الجملة دي", "اكتب خطة مذاكرة"],
        }
    return {
        "name": "Egypt AI — Free Search",
        "version": VERSION,
        "placeholder": True,
        "note": "بحث ويب مجاني لكل سؤال موضوعي. لإجابات تركيبية ذكية ثبّت Ollama أو أضف API key.",
        "intro": "أنا Egypt AI، أبحث عن المعلومات وأعرض لك إجابة منظمة قدر الإمكان.",
        "suggestions": ["مين هو نجيب محفوظ؟", "يعني إيه ذكاء اصطناعي؟", "ابحث عن أساسيات البرمجة", "احسب 12 × 7 + 3"],
    }


def think(message, history):
    message = (message or "").strip()
    if not message:
        return "اكتب سؤالك الأول."
    simple = _local_reply(message, history)
    if simple is not None:
        return simple

    # Search every substantive question first, whether the answer engine is API or local Ollama.
    search_context, sources = _search_context(message)
    enriched_message = (
        message + "\n\n[استخدم نتائج البحث التالية للإجابة عن سؤال المستخدم، وميّز بين الحقائق والاستنتاجات. "
        "لا تنسخ المقتطفات حرفيًا، ولا تدّعي أن النتائج تثبت ما لا تقوله.]\n" + search_context
    )

    key, workspace = _read_key()
    if key:
        answer = _ask_claude(enriched_message, history, key, workspace)
        return answer
    if _ollama_available():
        try:
            answer = _ask_ollama(enriched_message, history)
            return answer
        except BrainError:
            # If a local model is installed but unavailable, show its clear error.
            raise
    # Without a language model, return the search results and source links directly.
    return _web_fallback(message)
