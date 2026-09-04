# -*- coding: utf-8 -*-
"""
modules/article_rewriter/cms_publisher.py
GOLDEN CMS PUBLISHER: Port nguyên bản kiến trúc đăng bài từ ToolXaoBaiBao_V3 gốc.
Tự động làm sạch Base URL, hỗ trợ chuẩn endpoint /admin/api/v1/posts và /backend/posts,
sử dụng requests library và tự động xử lý trùng lặp slug (HTTP 422).
"""
import os
import re
import json
import time
import random
import requests
from typing import Tuple, Dict, Any, Callable
from urllib.parse import urlparse

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def art_slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'[^a-z0-9\-]', '', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s[:180] or "article"

def art_seo_description(body: str) -> str:
    clean = re.sub(r'<[^>]+>', ' ', body or '')
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:200]

class CMSPublisher:
    def __init__(
        self,
        base_url: str = "https://jesusvibe.danhngon.pro",
        token: str = "",
        cookie: str = "",
        create_url: str = "",
        log_cb: Callable = None
    ):
        # Làm sạch base_url chỉ lấy scheme + netloc (ví dụ: https://bodycamtoday.danhngon.pro)
        raw_base = (base_url or "https://jesusvibe.danhngon.pro").strip()
        if "://" in raw_base:
            p = urlparse(raw_base)
            self.base_url = f"{p.scheme}://{p.netloc}"
        else:
            self.base_url = f"https://{raw_base.split('/')[0]}"

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

        if embed_pos in ("Sau đoạn đầu", "after_first", "sau"):
            idx = body.find("</p>")
            if idx != -1:
                return body[:idx+4] + "\n" + code + "\n" + body[idx+4:]
            else:
                return code + "\n" + body
        elif embed_pos in ("Cuối bài", "bottom", "cuoi"):
            return body + "\n" + code
        elif embed_pos in ("Đầu bài", "top", "dau"):
            return code + "\n" + body
        elif embed_pos in ("Cả đầu và cuối", "both"):
            return code + "\n" + body + "\n" + code
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
        custom_endpoint: str = "",
        image_path: str = ""
    ) -> Tuple[bool, str, str]:
        """
        Gửi request đăng bài lên CMS theo chuẩn Tool gốc ToolXaoBaiBao_V3.
        Trả về: (success: bool, article_url_or_id: str, error_msg: str)
        """
        base = self.base_url.rstrip("/")
        if not base:
            return False, "", "Chưa cấu hình Base URL website!"

        final_body = self.inject_embed(body, embed_code, embed_pos)
        base_slug = slug or art_slugify(title)
        seo_desc = art_seo_description(final_body)

        fields = {
            "_token": self.token,
            "name": title,
            "title": title,
            "slug": base_slug,
            "description": final_body,
            "content": final_body,
            "seo_title": title,
            "seo_description": seo_desc,
            "seo_keywords": "",
            "canonical_url": "",
            "robots": "index, follow",
            "og_title": title,
            "twitter_title": title,
            "og_description": seo_desc,
            "twitter_description": seo_desc,
            "is_active": "1" if art_display else "0",
            "is_featured": "1" if art_top else "0",
            "is_sticky": "1" if art_top else "0",
            "is_home": "1" if art_home else "0",
            "is_top": "1" if art_top else "0",
            "status": "published" if art_display else "draft",
            "format_type": "default"
        }

        if image_path and str(image_path).strip().lower().startswith(('http://', 'https://')):
            fields["image"] = str(image_path).strip()
        else:
            fields.setdefault("image", "")

        # Xác định URL đăng bài
        if custom_endpoint:
            url = custom_endpoint if custom_endpoint.startswith("http") else f"{base}{custom_endpoint}"
        elif self.create_url:
            url = self.create_url if self.create_url.startswith("http") else f"{base}{self.create_url}"
        else:
            url = f"{base}/admin/api/v1/posts"

        headers = {
            "accept": "application/json",
            "x-csrf-token": self.token,
            "x-requested-with": "XMLHttpRequest",
            "origin": base,
            "referer": f"{base}/admin/posts/new",
            "user-agent": USER_AGENT,
            "cookie": self.cookie
        }

        # Trích xuất XSRF-TOKEN nếu có trong cookie
        m_xsrf = re.search(r'XSRF-TOKEN=([^;]+)', self.cookie or "")
        if m_xsrf and not self.token:
            headers["x-xsrf-token"] = m_xsrf.group(1).strip()

        self.log(f"Đang gửi bài viết tới CMS Endpoint: {url}...", "INFO")

        for retry in range(1, 4):
            try:
                r = requests.post(url, headers=headers, data=fields, timeout=120)

                # Nếu endpoint chính bị 404 hoặc 405, chuyển sang endpoint fallback /backend/posts
                if r.status_code in (404, 405) and "/admin/api/v1/posts" in url:
                    fallback_url = f"{base}/backend/posts"
                    headers["referer"] = f"{base}/backend/posts/create"
                    self.log(f"⚠️ Endpoint {url} không hỗ trợ (HTTP {r.status_code}), chuyển sang fallback: {fallback_url}...", "WARNING")
                    time.sleep(1.0)
                    r = requests.post(fallback_url, headers=headers, data=fields, timeout=120)
                    url = fallback_url

                # Xử lý tự động khi trùng Slug (HTTP 422)
                st_retry = 0
                while r.status_code == 422 and st_retry < 5:
                    resp_text = r.text.lower()
                    if "slug" in resp_text or "already been taken" in resp_text:
                        st_retry += 1
                        new_slug = f"{base_slug}-{random.randint(1000, 99999)}"
                        fields["slug"] = new_slug
                        self.log(f"⚠️ Slug bị trùng, tự động đổi sang: {new_slug}...", "WARNING")
                        r = requests.post(url, headers=headers, data=fields, timeout=120)
                    else:
                        break

                if 200 <= r.status_code < 300:
                    try:
                        resp_json = r.json()
                        art_id = str(resp_json.get("id") or resp_json.get("data", {}).get("id") or fields.get("slug"))
                    except Exception:
                        art_id = fields.get("slug")

                    public_link = f"{base}/blog/{fields.get('slug', base_slug)}"
                    self.log(f"✅ Đăng bài thành công lên CMS! Link: {public_link}", "SUCCESS")
                    return True, public_link, ""

                elif r.status_code in (401, 419):
                    self.log(f"❌ Session hoặc CSRF Token đã hết hạn (HTTP {r.status_code})!", "ERROR")
                    return False, "", f"Lỗi xác thực HTTP {r.status_code}: Token/Cookie đã hết hạn, vui lòng bấm 'Lấy Cookie/Token' lại."

                else:
                    self.log(f"⚠️ CMS trả về HTTP {r.status_code}: {r.text[:200]}", "WARNING")
                    time.sleep(2.0)

            except Exception as e:
                self.log(f"Lỗi kết nối tới CMS (Lần {retry}): {e}", "WARNING")
                time.sleep(2.0)

        return False, "", f"Không thể đăng bài lên CMS sau 3 lần thử (HTTP {getattr(r, 'status_code', 0)})!"

