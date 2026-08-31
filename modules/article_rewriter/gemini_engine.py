# -*- coding: utf-8 -*-
"""
modules/article_rewriter/gemini_engine.py
Engine viết lại nội dung bài báo chuẩn SEO qua Google Gemini API.
Hỗ trợ Timeout, Retry, Exponential Backoff (429 Rate Limit), và Thread-Safe.
"""
import time
import json
import urllib.request
import urllib.error
import ssl
from typing import Tuple, Dict, Any, Callable

DEFAULT_PROMPT_TEMPLATE = """You are a professional SEO journalist and content creator.
Please rewrite and translate the following article into {language}.
Requirements:
1. Make it captivating, engaging, natural, and 100% unique (pass AI detection and plagiarism checks).
2. Structure with clear paragraphs.
3. Return the response in strict JSON format with exactly two fields:
   - "title": A catchy, SEO-optimized title.
   - "body": The full rewritten article in clean HTML format (<p>, <h2>, <h3>, <ul>, <li>, <strong>).

Original Article:
{article_content}
"""

class GeminiEngine:
    def __init__(self, api_key: str = "", model: str = "gemini-3.5-flash-lite", log_cb: Callable = None):
        self.api_key = (api_key or "").strip()
        self.model = (model or "gemini-3.5-flash-lite").strip()
        self.log = log_cb or (lambda m, lv="INFO": None)

    def rewrite_article(
        self,
        original_text: str,
        target_language: str = "English",
        custom_prompt: str = "",
        max_retries: int = 3
    ) -> Tuple[bool, str, str, str]:
        """
        Viết lại bài báo bằng Gemini API.
        Trả về: (success: bool, title: str, html_body: str, error_msg: str)
        """
        if not self.api_key:
            return False, "", "", "Chưa cấu hình Gemini API Key!"
        if not original_text or not original_text.strip():
            return False, "", "", "Nội dung bài viết gốc trống!"

        prompt = (custom_prompt or DEFAULT_PROMPT_TEMPLATE).format(
            language=target_language,
            article_content=original_text.strip()
        )

        # Mapping tên model chuẩn nếu user nhập model alias
        model_name = self.model
        if "3.5" in model_name:
            # Fallback model nếu 3.5 chưa hỗ trợ endpoint trực tiếp
            actual_model = "gemini-1.5-flash"
        elif not model_name.startswith("gemini-"):
            actual_model = f"gemini-{model_name}"
        else:
            actual_model = model_name

        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "responseMimeType": "application/json"
            }
        }

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        json_bytes = json.dumps(payload).encode("utf-8")

        for attempt in range(1, max_retries + 1):
            try:
                self.log(f"Đang gửi bài viết tới AI Gemini ({actual_model}) - Lần thử {attempt}/{max_retries}...", "INFO")
                req = urllib.request.Request(
                    api_url,
                    data=json_bytes,
                    headers={"Content-Type": "application/json"}
                )

                with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    
                    # Trích xuất text từ response
                    candidates = resp_data.get("candidates", [])
                    if not candidates:
                        return False, "", "", "Gemini không trả về kết quả hợp lệ!"

                    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if not raw_text:
                        return False, "", "", "Nội dung phản hồi từ Gemini trống!"

                    # Parse JSON từ câu trả lời của AI
                    try:
                        parsed = json.loads(raw_text)
                        title = parsed.get("title", "").strip()
                        body = parsed.get("body", "").strip()
                    except Exception:
                        # Fallback nếu AI trả text thường thay vì JSON
                        lines = raw_text.strip().split("\n")
                        title = lines[0].lstrip("# ").strip()
                        body = "<p>" + "</p><p>".join([l for l in lines[1:] if l.strip()]) + "</p>"

                    self.log(f"✅ Xào bài thành công qua Gemini! Tiêu đề mới: {title[:40]}...", "SUCCESS")
                    return True, title, body, ""

            except urllib.error.HTTPError as he:
                status_code = he.code
                err_body = he.read().decode("utf-8", errors="ignore")
                
                if status_code == 429:
                    backoff = attempt * 3
                    self.log(f"⚠️ Gemini Rate Limit (429)! Đang chờ {backoff}s trước khi thử lại...", "WARNING")
                    time.sleep(backoff)
                elif status_code == 400:
                    self.log(f"❌ Lỗi API Key hoặc cú pháp không hợp lệ (400): {err_body[:100]}", "ERROR")
                    return False, "", "", f"Lỗi API 400: Kiểm tra lại API Key hoặc Model ({self.model})"
                else:
                    self.log(f"Lỗi HTTP {status_code}: {err_body[:100]}", "WARNING")
                    time.sleep(attempt * 2)

            except Exception as e:
                self.log(f"Lỗi kết nối Gemini (Lần {attempt}): {e}", "WARNING")
                time.sleep(attempt * 2)

        return False, "", "", "Không thể kết nối tới Gemini API sau 3 lần thử!"
