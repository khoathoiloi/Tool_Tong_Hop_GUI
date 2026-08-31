# -*- coding: utf-8 -*-
"""
modules/article_rewriter/cms_publisher.py
Engine đăng bài tự động lên website CMS với xác thực Token/Cookie và chèn mã nhúng/Embed.
"""
import time
import json
import re
import urllib.request
import urllib.error
import ssl
from typing import Tuple, Dict, Any, Callable
from urllib.parse import urljoin

class CMSPublisher:
    def __init__(
        self,
        base_url: str = "https://jesusvibe.danhngon.pro",
        token: str = "",
        cookie: str = "",
        create_url: str = "",
        log_cb: Callable = None
    ):
        self.base_url = (base_url or "https://jesusvibe.danhngon.pro").rstrip("/")
        self.token = (token or "").strip()
        self.cookie = (cookie or "").strip()
        self.create_url = (create_url or "").strip()
        self.log = log_cb or (lambda m, lv="INFO": None)

    def inject_embed(self, html_body: str, embed_code: str, embed_pos: str = "Sau đoạn đầu") -> str:
        """Chèn mã nhúng/embed vào vị trí chỉ định trong bài viết"""
        if not embed_code or not embed_code.strip():
            return html_body

        code = embed_code.strip()
        body = html_body.strip()

        if embed_pos == "Sau đoạn đầu":
            idx = body.find("</p>")
            if idx != -1:
                return body[:idx+4] + "\n" + code + "\n" + body[idx+4:]
            else:
                return code + "\n" + body
        elif embed_pos == "Cuối bài":
            return body + "\n" + code
        elif embed_pos == "Đầu bài":
            return code + "\n" + body
        elif embed_pos == "Giữa bài":
            paragraphs = [p for p in body.split("</p>") if p.strip()]
            if len(paragraphs) > 2:
                mid = len(paragraphs) // 2
                paragraphs.insert(mid, "\n" + code + "\n")
                return "</p>".join(paragraphs) + "</p>"
            return body + "\n" + code
        return body + "\n" + code

    def post_article(
        self,
        title: str,
        body: str,
        slug: str = "",
        art_display: bool = True,
        art_home: bool = True,
        art_top: bool = True,
        embed_code: str = "",
        embed_pos: str = "Sau đoạn đầu",
        custom_endpoint: str = ""
    ) -> Tuple[bool, str, str]:
        """
        Gửi request đăng bài lên CMS qua HTTP POST API.
        Trả về: (success: bool, article_url_or_id: str, error_msg: str)
        """
        if not self.base_url:
            return False, "", "Chưa cấu hình URL website bài báo (base_url)!"

        # Chèn mã nhúng vào nội dung bài
        final_body = self.inject_embed(body, embed_code, embed_pos)

        # Chuẩn bị danh sách endpoint thử nghiệm nếu create_url chưa xác định
        endpoints = []
        if custom_endpoint:
            endpoints.append(custom_endpoint)
        if self.create_url:
            endpoints.append(self.create_url)
        endpoints.extend([
            f"{self.base_url}/api/blogs/store",
            f"{self.base_url}/admin/blogs/store",
            f"{self.base_url}/admin/articles/create",
            f"{self.base_url}/api/articles",
            f"{self.base_url}/admin/posts/store"
        ])

        payload = {
            "title": title,
            "slug": slug or re.sub(r'[^a-zA-Z0-9]+', '-', title).strip('-').lower(),
            "content": final_body,
            "body": final_body,
            "is_display": 1 if art_display else 0,
            "is_home": 1 if art_home else 0,
            "is_top": 1 if art_top else 0,
            "status": "published",
            "_token": self.token
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/"
        }

        if self.token:
            headers["X-CSRF-TOKEN"] = self.token
            headers["X-XSRF-TOKEN"] = self.token
        if self.cookie:
            headers["Cookie"] = self.cookie

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        json_bytes = json.dumps(payload).encode("utf-8")

        for ep in endpoints:
            try:
                self.log(f"Đang gửi bài viết tới CMS Endpoint: {ep}...", "INFO")
                req = urllib.request.Request(ep, data=json_bytes, headers=headers, method="POST")
                
                with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                    resp_body = resp.read().decode("utf-8", errors="ignore")
                    status_code = resp.status

                    # Parse JSON response nếu có
                    try:
                        res_json = json.loads(resp_body)
                        if res_json.get("success") or res_json.get("status") == "success" or res_json.get("id"):
                            art_id = str(res_json.get("id", "") or res_json.get("data", {}).get("id", "OK"))
                            self.log(f"✅ Đăng bài thành công lên CMS! (ID: {art_id})", "SUCCESS")
                            return True, art_id, ""
                    except Exception:
                        pass

                    if 200 <= status_code < 300:
                        self.log(f"✅ Đăng bài thành công! (HTTP {status_code})", "SUCCESS")
                        return True, ep, ""

            except urllib.error.HTTPError as he:
                if he.code in (401, 419):
                    self.log(f"❌ Session hoặc CSRF Token đã hết hạn (HTTP {he.code})!", "ERROR")
                    return False, "", f"Lỗi xác thực HTTP {he.code}: Vui lòng bấm 'Lấy Cookie/Token' lại."
                elif he.code != 404:
                    self.log(f"⚠️ Endpoint {ep} trả về HTTP {he.code}", "WARNING")
            except Exception as e:
                self.log(f"Lỗi gửi request: {e}", "WARNING")

        return False, "", "Không thể đăng bài lên các Endpoint CMS của website (Vui lòng kiểm tra lại Token/Cookie)!"
