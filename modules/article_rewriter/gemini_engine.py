# -*- coding: utf-8 -*-
"""
modules/article_rewriter/gemini_engine.py
Multi-Provider AI Engine: Hỗ trợ cả Google Gemini và OpenAI / 9Router (OpenAI Compatible).
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

class AIEngine:
    def __init__(
        self,
        provider: str = "gemini",
        api_key: str = "",
        model: str = "gemini-3.5-flash-lite",
        base_url: str = "https://api.9router.com/v1",
        log_cb: Callable = None
    ):
        self.provider = (provider or "gemini").lower().strip()
        self.api_key = (api_key or "").strip()
        self.model = (model or "gemini-3.5-flash-lite").strip()
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
        Viết lại bài báo bằng AI Engine (Tự động chuyển tiếp theo Provider: Gemini hoặc OpenAI/9Router).
        Trả về: (success: bool, title: str, html_body: str, error_msg: str)
        """
        if not self.api_key:
            return False, "", "", f"Chưa cấu hình API Key cho nhà cung cấp {self.provider.upper()}!"
        if not original_text or not original_text.strip():
            return False, "", "", "Nội dung bài viết gốc trống!"

        prompt = (custom_prompt or DEFAULT_PROMPT_TEMPLATE).format(
            language=target_language,
            article_content=original_text.strip()
        )

        if self.provider in ("openai", "openai_9router", "9router"):
            return self._call_openai_compatible(prompt, max_retries)
        else:
            return self._call_gemini(prompt, max_retries)

    def validate_connection(self) -> Tuple[bool, str]:
        """
        Kiểm tra nhanh kết nối API Key và Model trước khi chạy hàng đợi.
        Không log hay làm lộ API Key ra ngoài.
        Trả về: (success: bool, detail_message: str)
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
                "User-Agent": "MasterToolHub-Validator"
            }
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            try:
                req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    resp_text = resp.read().decode("utf-8-sig", errors="ignore")
                    resp_data = json.loads(resp_text)
                    if "choices" in resp_data:
                        return True, f"Kết nối 9Router thành công! Model '{self.model}' khả dụng."
                    else:
                        err = resp_data.get("error", {}).get("message", "Phản hồi không hợp lệ")
                        return False, f"Lỗi 9Router: {err}"
            except urllib.error.HTTPError as he:
                err_b = he.read().decode("utf-8", errors="ignore")
                try:
                    err_j = json.loads(err_b)
                    msg = err_j.get("error", {}).get("message", err_b[:120])
                except Exception:
                    msg = err_b[:120]
                if he.code == 401:
                    return False, "Lỗi xác thực (HTTP 401): API Key không hợp lệ."
                elif he.code == 404:
                    return False, f"Lỗi Model (HTTP 404): Không tìm thấy model '{self.model}' trên 9Router."
                return False, f"HTTP {he.code}: {msg}"
            except Exception as e:
                return False, f"Lỗi kết nối: {str(e)}"

        else:
            # Google Gemini
            api_version = "v1beta"
            request_model = self.model.strip()
            api_url = f"https://generativelanguage.googleapis.com/{api_version}/models/{request_model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{"parts": [{"text": "Hi"}]}],
                "generationConfig": {"maxOutputTokens": 5}
            }
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            try:
                req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    resp_text = resp.read().decode("utf-8-sig", errors="ignore")
                    resp_data = json.loads(resp_text)
                    if "candidates" in resp_data:
                        return True, f"Kết nối Google Gemini thành công! Model '{request_model}' ({api_version}) khả dụng."
                    else:
                        err = resp_data.get("error", {}).get("message", "Phản hồi không hợp lệ")
                        return False, f"Lỗi Gemini: {err}"
            except urllib.error.HTTPError as he:
                err_b = he.read().decode("utf-8", errors="ignore")
                try:
                    err_j = json.loads(err_b)
                    msg = err_j.get("error", {}).get("message", err_b[:120])
                except Exception:
                    msg = err_b[:120]
                if he.code == 400:
                    return False, f"Lỗi API (HTTP 400): API Key không hợp lệ hoặc cú pháp sai: {msg}"
                elif he.code == 404:
                    return False, f"Lỗi Model (HTTP 404): Model '{request_model}' không tìm thấy cho API {api_version}."
                elif he.code == 403:
                    return False, "Lỗi Phân Quyền (HTTP 403): API Key bị giới hạn hoặc chưa bật Generative Language API."
                return False, f"HTTP {he.code}: {msg}"
            except Exception as e:
                return False, f"Lỗi kết nối: {str(e)}"

    def _call_gemini(self, prompt: str, max_retries: int) -> Tuple[bool, str, str, str]:
        selected_model = self.model.strip()
        request_model = selected_model
        api_version = "v1beta"

        # Log đúng 3 dòng bắt buộc
        self.log(f"[Gemini] Selected model: {selected_model}", "INFO")
        self.log(f"[Gemini] Request model: {request_model}", "INFO")
        self.log(f"[Gemini] API version: {api_version}", "INFO")

        if selected_model != request_model:
            err = f"Configuration error: Selected model ({selected_model}) != Request model ({request_model})"
            self.log(f"❌ {err}", "ERROR")
            return False, "", "", err

        api_url = f"https://generativelanguage.googleapis.com/{api_version}/models/{request_model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
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
                self.log(f"Đang gửi bài viết tới Google Gemini ({request_model}) - Lần {attempt}/{max_retries}...", "INFO")
                req = urllib.request.Request(api_url, data=json_bytes, headers={"Content-Type": "application/json"})

                with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    candidates = resp_data.get("candidates", [])
                    if not candidates:
                        return False, "", "", "Gemini không trả về kết quả hợp lệ!"

                    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    title, body = self._parse_json_or_text(raw_text)
                    self.log(f"✅ Xào bài thành công qua Gemini! Tiêu đề: {title[:40]}...", "SUCCESS")
                    return True, title, body, ""

            except urllib.error.HTTPError as he:
                if he.code == 429:
                    backoff = attempt * 3
                    self.log(f"⚠️ Gemini Rate Limit (429)! Đang chờ {backoff}s...", "WARNING")
                    time.sleep(backoff)
                else:
                    err_b = he.read().decode("utf-8", errors="ignore")[:100]
                    self.log(f"Lỗi HTTP {he.code}: {err_b}", "WARNING")
                    time.sleep(attempt * 2)
            except Exception as e:
                self.log(f"Lỗi kết nối Gemini (Lần {attempt}): {e}", "WARNING")
                time.sleep(attempt * 2)

        return False, "", "", "Không thể kết nối tới Gemini API sau các lần thử!"

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
                {"role": "system", "content": "You are a professional SEO journalist. You MUST ALWAYS respond with a strict JSON object containing 'title' and 'body' fields."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }

        # Bật response_format json nếu model hỗ trợ
        if any(k in request_model.lower() for k in ["gpt", "4o", "mini", "deepseek"]):
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MasterToolHub-AIEngine"
        }

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        json_bytes = json.dumps(payload).encode("utf-8")

        for attempt in range(1, max_retries + 1):
            try:
                self.log(f"Đang gửi bài viết tới 9Router/OpenAI ({self.model}) - Lần {attempt}/{max_retries}...", "INFO")
                req = urllib.request.Request(endpoint, data=json_bytes, headers=headers, method="POST")

                with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                    resp_bytes = resp.read()
                    resp_text = resp_bytes.decode("utf-8-sig", errors="ignore").strip()
                    if not resp_text:
                        self.log(f"⚠️ 9Router trả về dữ liệu rỗng (Empty response)! Kiểm tra lại Model '{self.model}' trên 9Router.", "WARNING")
                        time.sleep(attempt * 2)
                        continue

                    try:
                        resp_data = json.loads(resp_text)
                    except Exception as json_err:
                        snippet = resp_text[:120].replace('\n', ' ')
                        self.log(f"⚠️ Máy chủ 9Router không trả JSON hợp lệ: {snippet}", "WARNING")
                        time.sleep(attempt * 2)
                        continue

                    choices = resp_data.get("choices", [])
                    if not choices:
                        err_msg = resp_data.get("error", {}).get("message", str(resp_data))
                        self.log(f"⚠️ 9Router không trả choices: {err_msg[:120]}", "WARNING")
                        return False, "", "", f"Lỗi 9Router: {err_msg[:120]}"

                    raw_text = choices[0].get("message", {}).get("content", "")
                    title, body = self._parse_json_or_text(raw_text)
                    self.log(f"✅ Xào bài thành công qua 9Router! Tiêu đề: {title[:40]}...", "SUCCESS")
                    return True, title, body, ""

            except urllib.error.HTTPError as he:
                err_b = he.read().decode("utf-8", errors="ignore")[:150]
                if he.code == 429:
                    backoff = attempt * 3
                    self.log(f"⚠️ 9Router Rate Limit (429)! Đang chờ {backoff}s...", "WARNING")
                    time.sleep(backoff)
                elif he.code == 401:
                    self.log(f"❌ 9Router API Key không hợp lệ (401)!", "ERROR")
                    return False, "", "", "API Key 9Router không hợp lệ!"
                else:
                    self.log(f"Lỗi 9Router HTTP {he.code}: {err_b}", "WARNING")
                    time.sleep(attempt * 2)
            except Exception as e:
                self.log(f"Lỗi kết nối 9Router (Lần {attempt}): {e}", "WARNING")
                time.sleep(attempt * 2)

        return False, "", "", "Không thể kết nối tới 9Router/OpenAI API sau các lần thử!"

    @staticmethod
    def _parse_json_or_text(raw_text: str) -> Tuple[str, str]:
        raw_text = raw_text.strip()
        # Loại bỏ markdown code block nếu có
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        try:
            parsed = json.loads(raw_text)
            title = str(parsed.get("title", "")).strip()
            body = str(parsed.get("body", "")).strip()
            if title and body:
                return title, body
        except Exception:
            pass

        # Fallback text parsing
        lines = raw_text.strip().split("\n")
        title = lines[0].lstrip("# ").strip()
        body = "<p>" + "</p><p>".join([l.strip() for l in lines[1:] if l.strip()]) + "</p>"
        return title, body

# Alias for backward compatibility
GeminiEngine = AIEngine
