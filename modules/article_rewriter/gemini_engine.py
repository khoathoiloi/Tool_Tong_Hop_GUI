# -*- coding: utf-8 -*-
"""
modules/article_rewriter/gemini_engine.py
GOLDEN GEMINI ENGINE: Port nguyên bản kiến trúc kết nối từ ToolXaoBaiBao_V3 gốc.
Sử dụng requests library, timeout 120s, lọc thẻ <think>/<thought>/<reasoning>,
hỗ trợ xoay vòng / fallback và OpenAI / 9Router tương thích.
"""
import re
import json
import time
import requests
from typing import Tuple, List, Dict, Any, Callable

DEFAULT_PROMPT_TEMPLATE = """You are an elite viral blog editor and masterful investigative storyteller.
Your task is to completely rewrite, reframe, and spin the following source article into a BRAND NEW, captivating, high-retention blog article written in {language}.

ORIGINAL CONTENT:
{article_content}

STRICT WRITING RULES:
1. CREATE A FRESH, COMPELLING TITLE:
   - Make it sensational, dramatic, and high-CTR without being cheap clickbait.
2. COMPELLING REWRITTEN STORY:
   - Rewrite the entire narrative with rich emotion, suspense, and engaging storytelling.
   - Structure with well-crafted paragraphs and ## Subheadings.
3. LANGUAGE:
   - Output completely in {language}.
4. STRICT OUTPUT FORMAT:
Your entire output MUST strictly start with 'TITLE:' and contain ONLY the title and the clean HTML/markdown article body.
Format:
TITLE: [Your New Catchy Title Here]

[Your New Article Body with paragraphs and <h2> Subheadings]

Do NOT include any extra notes, preambles, reasoning tags, or markdown fences.
"""

def _kilo_strip_think(text: str) -> str:
    """Loại bỏ các thẻ suy nghĩ reasoning của model (Gemini 3.7 / DeepSeek)"""
    t = str(text or "")
    t = re.sub(r'(?is)<think>.*?</think>', '', t)
    t = re.sub(r'(?is)<thought>.*?</thought>', '', t)
    t = re.sub(r'(?is)<reasoning>.*?</reasoning>', '', t)
    return t.strip()

def _gemini_is_daily_limit(body_txt: str) -> bool:
    return bool(re.search(
        r'per day|/day|\bdaily\b|tokens? per day|requests? per day|\bTPD\b|\bRPD\b|day limit|RESOURCE_EXHAUSTED|quota exceeded|exceeded your current quota',
        str(body_txt or ""),
        re.I
    ))

class AIEngine:
    def __init__(
        self,
        provider: str = "gemini",
        api_key: str = "",
        model: str = "gemini-3.7-flash",
        base_url: str = "https://api.9router.com/v1",
        log_cb: Callable = None
    ):
        self.provider = (provider or "gemini").lower().strip()
        self.api_key = (api_key or "").strip()
        self.model = (model or "gemini-3.7-flash").strip()
        self.base_url = (base_url or "https://api.9router.com/v1").rstrip("/")
        self.log = log_cb or (lambda m, lv="INFO": None)

    def rewrite_article(
        self,
        original_text: str,
        target_language: str = "English",
        custom_prompt: str = "",
        max_retries: int = 3
    ) -> Tuple[bool, str, str, str]:
        """
        Viết lại bài báo bằng Golden Gemini Engine (hoặc OpenAI/9Router).
        Trả về: (success: bool, title: str, html_body: str, error_msg: str)
        """
        if not self.api_key:
            return False, "", "", f"Chưa cấu hình API Key cho {self.provider.upper()}!"
        if not original_text or not original_text.strip():
            return False, "", "", "Nội dung bài viết gốc trống!"

        prompt = (custom_prompt or DEFAULT_PROMPT_TEMPLATE).format(
            language=target_language,
            article_content=original_text.strip()[:6000]
        )

        if self.provider in ("openai", "openai_9router", "9router"):
            return self._call_openai_compatible(prompt, max_retries)
        else:
            return self._call_gemini_golden(prompt, max_retries)

    def validate_connection(self) -> Tuple[bool, str]:
        """
        Kiểm tra nhanh kết nối API Key và Model trước khi chạy hàng đợi.
        Không log hay làm lộ API Key ra ngoài.
        """
        if not self.api_key:
            return False, f"Chưa nhập API Key cho {self.provider.upper()}!"

        if self.provider in ("openai", "openai_9router", "9router"):
            endpoint = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model or "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MasterToolHub/2.7"
            }
            try:
                r = requests.post(endpoint, headers=headers, json=payload, timeout=15)
                if 200 <= r.status_code < 300:
                    return True, f"Kết nối 9Router thành công! Model '{self.model}' khả dụng."
                elif r.status_code == 401:
                    return False, "Lỗi xác thực (HTTP 401): API Key không hợp lệ."
                elif r.status_code == 404:
                    return False, f"Lỗi Model (HTTP 404): Không tìm thấy model '{self.model}' trên 9Router."
                else:
                    return False, f"HTTP {r.status_code}: {r.text[:120]}"
            except Exception as e:
                return False, f"Lỗi kết nối ({type(e).__name__}): {str(e)}"

        else:
            # Google Gemini Golden Connection Test
            api_version = "v1beta"
            request_model = self.model.strip()
            endpoint = f"https://generativelanguage.googleapis.com/{api_version}/models/{request_model}:generateContent?key={self.api_key}"
            body = {
                "contents": [{"parts": [{"text": "Hello"}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 5
                }
            }
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MasterToolHub/2.7"
            }

            try:
                r = requests.post(endpoint, headers=headers, json=body, timeout=15)
                if 200 <= r.status_code < 300:
                    return True, f"Kết nối Google Gemini thành công! Model '{request_model}' ({api_version}) khả dụng."
                elif r.status_code == 400:
                    return False, f"Lỗi API (HTTP 400): API Key không hợp lệ hoặc cú pháp sai."
                elif r.status_code == 404:
                    return False, f"Lỗi Model (HTTP 404): Model '{request_model}' không tìm thấy cho API {api_version}."
                elif r.status_code == 403:
                    return False, "Lỗi Phân Quyền (HTTP 403): API Key bị giới hạn hoặc chưa bật Generative Language API."
                elif r.status_code == 429:
                    return False, "Lỗi Quota (HTTP 429): API Key đã hết lượt request / rate limit."
                else:
                    return False, f"HTTP {r.status_code}: {r.text[:120]}"
            except Exception as e:
                return False, f"Lỗi kết nối ({type(e).__name__}): {str(e)}"

    @staticmethod
    def fetch_available_models(api_key: str, api_version: str = "v1beta") -> Tuple[bool, List[str], str]:
        """
        Dynamic Model Discovery: Lấy danh sách model Gemini khả dụng từ Google API.
        """
        if not api_key or not api_key.strip():
            return False, [], "Chưa nhập API Key!"

        api_url = f"https://generativelanguage.googleapis.com/{api_version}/models?key={api_key.strip()}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MasterToolHub/2.7"
        }

        try:
            r = requests.get(api_url, headers=headers, timeout=15)
            if 200 <= r.status_code < 300:
                data = r.json()
                raw_models = data.get("models", [])
                
                gemini_models = []
                for m in raw_models:
                    m_name = m.get("name", "").replace("models/", "").strip()
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods and not any(k in m_name for k in ["embedding", "aqa", "imagen"]):
                        gemini_models.append(m_name)

                def _sort_priority(name: str):
                    if "3.7" in name:
                        return (0, name)
                    if "2.5" in name:
                        return (1, name)
                    if "2.0" in name:
                        return (2, name)
                    if "1.5" in name:
                        return (3, name)
                    return (4, name)

                gemini_models.sort(key=_sort_priority)

                if not gemini_models:
                    gemini_models = ["gemini-3.7-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

                return True, gemini_models, f"Đã tìm thấy {len(gemini_models)} model khả dụng từ Google API."
            elif r.status_code == 400:
                return False, [], "API Key không hợp lệ (HTTP 400)."
            elif r.status_code in (401, 403):
                return False, [], f"Lỗi xác thực/phân quyền API Key (HTTP {r.status_code})."
            else:
                return False, [], f"Lỗi HTTP {r.status_code}: {r.text[:100]}"
        except Exception as e:
            return False, [], f"Lỗi kết nối ({type(e).__name__}): {str(e)}"

    def _call_gemini_golden(self, prompt: str, max_retries: int) -> Tuple[bool, str, str, str]:
        """Golden Reference Implementation từ ToolXaoBaiBao_V3"""
        selected_model = self.model.strip()
        request_model = selected_model
        api_version = "v1beta"

        if selected_model != request_model:
            err = f"INTERNAL MODEL MISMATCH: Selected model ({selected_model}) != Request model ({request_model})"
            self.log(f"❌ {err}", "ERROR")
            return False, "", "", err

        endpoint = f"https://generativelanguage.googleapis.com/{api_version}/models/{request_model}:generateContent?key={self.api_key}"

        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.75,
                "topP": 0.9,
                "maxOutputTokens": 4096
            }
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MasterToolHub/2.7"
        }

        for attempt in range(1, max_retries + 1):
            self.log(f"[Gemini] Golden Engine - Model: {selected_model}", "INFO")
            self.log(f"[Gemini] Request model: {request_model}", "INFO")
            self.log(f"[Gemini] API version: {api_version}", "INFO")
            self.log(f"[Gemini] Attempt: {attempt}/{max_retries}", "INFO")

            try:
                # Golden timeout 120s từ Tool gốc
                r = requests.post(endpoint, headers=headers, json=body, timeout=120)
                _code = getattr(r, 'status_code', 0)

                if 200 <= _code < 300:
                    data = r.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        return False, "", "", "Gemini không trả về kết quả hợp lệ!"

                    raw_out = str(candidates[0].get("content", {}).get("parts", [{}])[0].get("text", ""))
                    raw_out = _kilo_strip_think(raw_out)

                    title, html_body = self._parse_golden_response(raw_out)
                    self.log(f"✅ Xào bài thành công qua Golden Gemini! Tiêu đề: {title[:40]}...", "SUCCESS")
                    return True, title, html_body, ""

                # Phân loại lỗi và fail fast
                err_text = getattr(r, 'text', '')[:200]
                if _code == 404:
                    self.log(f"❌ [Gemini] Lỗi HTTP 404: Model '{request_model}' không tồn tại cho API {api_version}!", "ERROR")
                    return False, "", "", f"❌ Gemini model unavailable: {request_model} (HTTP 404)"
                elif _code in (400, 401, 403):
                    self.log(f"❌ [Gemini] Lỗi xác thực/phân quyền (HTTP {_code}): {err_text}", "ERROR")
                    return False, "", "", f"Lỗi HTTP {_code}: API Key hoặc phân quyền không hợp lệ."
                elif _code == 429 or _gemini_is_daily_limit(err_text):
                    backoff = attempt * 3
                    self.log(f"⚠️ Gemini Rate Limit (429)! Đang chờ {backoff}s...", "WARNING")
                    time.sleep(backoff)
                elif _code >= 500:
                    self.log(f"⚠️ Máy chủ Google lỗi (HTTP {_code}), đang thử lại...", "WARNING")
                    time.sleep(attempt * 2)
                else:
                    self.log(f"Lỗi HTTP {_code}: {err_text}", "WARNING")
                    time.sleep(attempt * 2)

            except requests.exceptions.Timeout:
                self.log(f"⚠️ Gemini timeout (Lần {attempt}), đang thử lại...", "WARNING")
                time.sleep(attempt * 2)
            except Exception as e:
                self.log(f"Lỗi kết nối Gemini (Lần {attempt}): {e}", "WARNING")
                time.sleep(attempt * 2)

        return False, "", "", f"Không thể kết nối tới Gemini API ({request_model}) sau các lần thử!"

    def _call_openai_compatible(self, prompt: str, max_retries: int) -> Tuple[bool, str, str, str]:
        selected_model = (self.model or "gpt-4o-mini").strip()
        request_model = selected_model
        endpoint = f"{self.base_url}/chat/completions"

        self.log(f"[9Router/OpenAI] Selected model: {selected_model}", "INFO")
        self.log(f"[9Router/OpenAI] Request model: {request_model}", "INFO")
        self.log(f"[9Router/OpenAI] Endpoint: {endpoint}", "INFO")

        if selected_model != request_model:
            err = f"Configuration error: Selected model ({selected_model}) != Request model ({request_model})"
            self.log(f"❌ {err}", "ERROR")
            return False, "", "", err

        payload = {
            "model": request_model,
            "messages": [
                {"role": "system", "content": "You are a professional SEO journalist. You MUST format output as TITLE: <title>\n\n<body>."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MasterToolHub/2.7"
        }

        for attempt in range(1, max_retries + 1):
            try:
                self.log(f"Đang gửi bài viết tới 9Router/OpenAI ({request_model}) - Lần {attempt}/{max_retries}...", "INFO")
                r = requests.post(endpoint, headers=headers, json=payload, timeout=120)
                _code = r.status_code

                if 200 <= _code < 300:
                    raw_text = self._extract_openai_response(r)
                    if not raw_text:
                        return False, "", "", "9Router không trả về nội dung hợp lệ!"

                    raw_text = _kilo_strip_think(raw_text)
                    title, body = self._parse_golden_response(raw_text)
                    self.log(f"✅ Xào bài thành công qua 9Router! Tiêu đề: {title[:40]}...", "SUCCESS")
                    return True, title, body, ""

                err_text = r.text[:200]
                if _code in (400, 401, 403, 404):
                    self.log(f"❌ [9Router] Lỗi HTTP {_code}: {err_text}", "ERROR")
                    return False, "", "", f"Lỗi 9Router HTTP {_code}: {err_text}"
                elif _code == 429:
                    backoff = attempt * 3
                    self.log(f"⚠️ 9Router Rate Limit (429)! Đang chờ {backoff}s...", "WARNING")
                    time.sleep(backoff)
                else:
                    time.sleep(attempt * 2)

            except Exception as e:
                self.log(f"Lỗi kết nối 9Router (Lần {attempt}): {e}", "WARNING")
                time.sleep(attempt * 2)

        return False, "", "", "Không thể kết nối tới 9Router sau các lần thử!"

    @staticmethod
    def _extract_openai_response(r: requests.Response) -> str:
        ct = r.headers.get("content-type", "")
        text = r.text
        if "event-stream" in ct or text.startswith("data:"):
            chunks = []
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("data:") and not line.startswith("data: [DONE]"):
                    chunk_str = line[5:].strip()
                    try:
                        chunk = json.loads(chunk_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            msg = choices[0].get("message", {})
                            txt = delta.get("content") or msg.get("content") or ""
                            if txt:
                                chunks.append(txt)
                    except Exception:
                        pass
            return "".join(chunks).strip()
        else:
            try:
                resp_data = r.json()
                choices = resp_data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
            except Exception:
                pass
            return text.strip()

    def _parse_golden_response(self, raw_text: str) -> Tuple[str, str]:
        """Tách Tiêu đề và Nội dung bài viết theo chuẩn Golden Format"""
        text = _kilo_strip_think(raw_text or "").strip()
        new_title = ""
        new_body = ""

        m_title = re.search(r'^TITLE:\s*(.+)$', text, flags=re.M | re.I)
        if m_title:
            new_title = m_title.group(1).strip()
            new_body = text[m_title.end():].strip()
        else:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if lines:
                new_title = re.sub(r'^[#*\s]+', '', lines[0]).strip()
                new_body = "\n\n".join(lines[1:]).strip()

        if not new_title:
            new_title = "Tin Tức Tổng Hợp Mới"
        if not new_body:
            new_body = text

        # Chuyển đổi Markdown sang HTML sạch nếu chưa có thẻ HTML
        if "<p>" not in new_body and "<h2>" not in new_body:
            out_lines = []
            for line in new_body.splitlines():
                raw = line.strip()
                if not raw:
                    continue
                if raw.startswith("### "):
                    out_lines.append(f"<h3>{raw[4:].strip()}</h3>")
                elif raw.startswith("## "):
                    out_lines.append(f"<h2>{raw[3:].strip()}</h2>")
                elif raw.startswith("# "):
                    out_lines.append(f"<h1>{raw[2:].strip()}</h1>")
                elif raw.startswith("- ") or raw.startswith("* "):
                    out_lines.append(f"<li>{raw[2:].strip()}</li>")
                else:
                    out_lines.append(f"<p>{raw}</p>")
            new_body = "\n".join(out_lines)

        return new_title, new_body

# Alias tương thích
GeminiEngine = AIEngine
GoldenGeminiEngine = AIEngine
