# -*- coding: utf-8 -*-
"""
modules/article_rewriter/worker.py
Quản lý Hàng Đợi bài viết, bóc tách link báo gốc, xử lý đa luồng (Multi-threading),
tự động kiểm tra xác minh bài mới đã có trên web hay chưa, và tự động làm lại các bài
chưa được xào/đăng để đảm bảo chuẩn xác số lượng link đầu vào (không thiếu, không thừa).
"""
import os
import re
import time
import queue
import urllib.parse
import threading
from html import unescape as html_unescape
from typing import List, Dict, Any, Callable, Tuple
import requests

from .gemini_engine import GeminiEngine
from .cms_publisher import CMSPublisher
from .history_manager import HistoryManager

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def art_fetch_and_parse_url(url: str, timeout: int = 25) -> Tuple[bool, Dict[str, Any], str]:
    """
    Tải và bóc tách toàn bộ dữ liệu từ link bài báo cũ:
    - Tiêu đề gốc
    - Ảnh bìa (og:image)
    - Toàn bộ ảnh minh họa trong bài (content_images)
    - Video embed iframe nếu có (YouTube, iframes, videos)
    - Văn bản bài viết sạch để đưa vào AI xào lại
    """
    url = str(url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, {}, "URL bài báo không hợp lệ (cần bắt đầu bằng http:// hoặc https://)"

    parsed_u = urllib.parse.urlparse(url)
    api_base = f"{parsed_u.scheme}://{parsed_u.netloc}"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8"
    }

    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return False, {}, f"HTTP {r.status_code}: Không thể tải trang gốc"

        html = r.text
        if not html or len(html) < 200:
            return False, {}, "Trang bài báo trả về nội dung rỗng"

        # 1. Trích xuất tiêu đề gốc
        title_m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']*)["\']', html, re.I)
        if not title_m:
            title_m = re.search(r'<h1[^>]*class=["\'][^"\']*module-article-header__title[^"\']*["\'][^>]*>(.*?)</h1>', html, re.I | re.S)
        if not title_m:
            title_m = re.search(r'<title>(.*?)</title>', html, re.I | re.S)

        title = html_unescape(title_m.group(1).strip()) if title_m else ""
        title = re.sub(r'\s*[-|]\s*[^-\|]+$', '', title).strip()

        # 2. Trích xuất ảnh đại diện (og:image)
        og_img_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']*)["\']', html, re.I)
        cover_image = html_unescape(og_img_m.group(1).strip()) if og_img_m else ""

        # 3. Trích xuất vùng nội dung bài viết chính
        content_body_m = re.search(r'<div[^>]*class=["\'][^"\']*module-article-content__body[^"\']*["\'][^>]*>(.*?)(?:<section\b|<!-- module:|$)', html, re.I | re.S)
        if content_body_m:
            content_html = content_body_m.group(1)
        else:
            art_m = re.search(r'<article[^>]*>(.*?)</article>', html, re.I | re.S)
            content_html = art_m.group(1) if art_m else html

        # Làm sạch quảng cáo và rác trong nội dung
        content_clean = re.sub(r'<div[^>]*class=["\'][^"\']*in-article-ad[^"\']*["\'][^>]*>.*?</div>\s*</div>', '', content_html, flags=re.I | re.S)
        content_clean = re.sub(r'<div[^>]*class=["\'][^"\']*in-article-ad[^"\']*["\'][^>]*>.*?</div>', '', content_clean, flags=re.I | re.S)
        content_clean = re.sub(r'<div[^>]*class=["\'][^"\']*ad\s+article-below-title[^"\']*["\'][^>]*>.*?</div>\s*</div>', '', content_clean, flags=re.I | re.S)
        content_clean = re.sub(r'<div[^>]*class=["\'][^"\']*ad\s+article-below-title[^"\']*["\'][^>]*>.*?</div>', '', content_clean, flags=re.I | re.S)
        content_clean = re.sub(r'<section[^>]*class=["\'][^"\']*module-report-button[^"\']*["\'][^>]*>.*', '', content_clean, flags=re.I | re.S)

        # 4. Trích xuất ảnh trong bài
        raw_images = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content_clean, re.I)
        content_images = []
        for img_u in raw_images:
            img_u = img_u.strip()
            if img_u.startswith("//"):
                img_u = "https:" + img_u
            elif img_u.startswith("/"):
                img_u = api_base + img_u
            if img_u.startswith("http") and img_u not in content_images:
                content_images.append(img_u)

        if not cover_image and content_images:
            cover_image = content_images[0]

        # 5. Trích xuất Embeds / Iframes / Video
        iframes = []
        for m in re.finditer(r'<iframe[^>]*\bsrc=["\']([^"\']+)["\']', html, re.I):
            ifr_src = html_unescape(m.group(1)).strip()
            if ifr_src.startswith("//"):
                ifr_src = "https:" + ifr_src
            elif ifr_src.startswith("/"):
                ifr_src = api_base + ifr_src
            if ifr_src and ifr_src not in iframes:
                iframes.append(ifr_src)

        for yt_m in re.finditer(r'(?:https?:)?//(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})', html, re.I):
            vid = yt_m.group(1)
            full_yt = f"https://www.youtube.com/watch?v={vid}"
            if full_yt not in iframes and vid not in iframes:
                iframes.append(full_yt)

        for v_m in re.finditer(r'<video[^>]*\bsrc=["\']([^"\']+)["\']', html, re.I):
            v_src = html_unescape(v_m.group(1)).strip()
            if v_src and v_src not in iframes:
                iframes.append(v_src)

        # 6. Văn bản thuần để AI xào
        text_only = re.sub(r'<thought>.*?</thought>', '', content_clean, flags=re.I | re.S)
        text_only = re.sub(r'<script.*?</script>', '', text_only, flags=re.I | re.S)
        text_only = re.sub(r'<style.*?</style>', '', text_only, flags=re.I | re.S)
        text_only = re.sub(r'<[^>]+>', ' ', text_only)
        text_only = html_unescape(text_only)
        text_only = re.sub(r'\s+', ' ', text_only).strip()

        if len(text_only) < 100:
            fallback_text = re.sub(r'<script.*?</script>', '', html, flags=re.I | re.S)
            fallback_text = re.sub(r'<style.*?</style>', '', fallback_text, flags=re.I | re.S)
            fallback_text = re.sub(r'<[^>]+>', ' ', fallback_text)
            fallback_text = html_unescape(fallback_text)
            fallback_text = re.sub(r'\s+', ' ', fallback_text).strip()
            if len(fallback_text) > len(text_only):
                text_only = fallback_text

        if len(text_only) < 60:
            return False, {}, "Không bóc tách được nội dung bài báo (quá ngắn hoặc bị chặn bởi bot protection)"

        return True, {
            "url": url,
            "api_base": api_base,
            "title": title,
            "cover_image": cover_image,
            "content_images": content_images,
            "iframes": iframes,
            "text_content": text_only
        }, ""

    except Exception as e:
        return False, {}, f"Lỗi kết nối tải bài: {str(e)}"


def verify_article_on_web(url: str, expected_title: str = "", timeout: int = 15) -> Tuple[bool, str]:
    """
    Kiểm tra xem bài báo mới đã thực sự hiển thị trên Web hay chưa.
    Thử nghiệm tối đa 2 lần (cách nhau 1.5s) để tránh trường hợp máy chủ CMS vừa đăng chưa kịp ghi cache.
    """
    url = str(url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, "Link bài mới không hợp lệ"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    for attempt in range(1, 3):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                # 1. Kiểm tra chuyển hướng về trang chủ khi bài viết không tồn tại (CMS behavior)
                p_orig = urllib.parse.urlparse(url).path.rstrip('/')
                p_final = urllib.parse.urlparse(r.url).path.rstrip('/')
                if p_orig and p_final != p_orig:
                    if attempt == 1:
                        time.sleep(1.5)
                        continue
                    return False, "Bị chuyển hướng về trang chủ (Bài chưa tồn tại)"

                html = r.text
                if len(html) < 400:
                    if attempt == 1:
                        time.sleep(1.5)
                        continue
                    return False, "Trang web trả về nội dung quá ngắn hoặc rỗng"

                # 2. Kiểm tra tiêu đề lỗi 404
                m_title = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
                t_low = m_title.group(1).lower() if m_title else ""
                if any(err_kw in t_low for err_kw in ["404", "not found", "không tìm thấy", "error 404"]):
                    if attempt == 1:
                        time.sleep(1.5)
                        continue
                    return False, f"Trang hiển thị lỗi: {t_low[:40]}"

                return True, "OK (HTTP 200)"
            elif r.status_code == 404 and attempt == 1:
                time.sleep(2.0)
                continue
            else:
                return False, f"HTTP {r.status_code}"
        except Exception as e:
            if attempt == 1:
                time.sleep(1.5)
                continue
            return False, f"Lỗi kết nối: {str(e)}"

    return False, "Không thể xác minh bài viết trên Web"


def write_result_to_source_file(file_path: str, new_title: str, new_link: str) -> Tuple[bool, str]:
    """
    Dán tiêu đề mới và đường link mới của bài báo vào file .txt ban đầu đã được lấy.
    Ghi rõ tiêu đề mới và link báo mới để tránh bị nhầm lẫn với link/tiêu đề cũ.
    """
    if not file_path or not os.path.exists(file_path):
        return False, f"Đường dẫn file không tồn tại: {file_path}"
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Làm sạch khối kết quả cũ nếu đã có để tránh trùng lặp khi chạy lại
        block_pattern = re.compile(r'\n*-{10,}\s*\[KẾT QUẢ XÀO BÀI MỚI\].*?-{10,}', re.S)
        content_clean = block_pattern.sub('', content).strip()

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        new_block = (
            "\n\n"
            "--------------------------------------------------\n"
            "[KẾT QUẢ XÀO BÀI MỚI]\n"
            f"Tiêu đề mới: {new_title}\n"
            f"Link báo mới: {new_link}\n"
            f"Thời gian xào & đăng: {now_str}\n"
            "--------------------------------------------------"
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content_clean + new_block + "\n")
        return True, ""
    except Exception as e:
        return False, f"Lỗi ghi file {os.path.basename(file_path)}: {str(e)}"


class ArticleItem:
    def __init__(self, item_id: int, content: str, force_post: bool = False, source_file: str = ""):
        self.id = item_id
        self.content = content.strip()
        self.source_file = source_file.strip() # Đường dẫn file .txt ban đầu chứa link này
        self.is_url = bool(re.match(r'^https?://', self.content, re.I))
        self.status = "Pending"  # Pending, Fetching, Rewriting, Posting, Verifying, Success, Failed, Cancelled
        self.orig_title = ""
        self.title = ""
        self.body = ""
        self.result_id = ""      # Đường link bài báo mới được đăng
        self.is_verified = False # Đã xác minh có mặt trên web hay chưa
        self.error = ""
        self.retry_count = 0
        self.force_post = force_post


class ArticleWorker:
    def __init__(
        self,
        app_dir: str,
        config_data: Dict[str, Any],
        log_cb: Callable = None,
        on_item_updated: Callable = None,
        on_finished: Callable = None
    ):
        self.app_dir = app_dir
        self.config = config_data
        self.log = log_cb or (lambda m, lv="INFO": None)
        self.on_item_updated = on_item_updated or (lambda item: None)
        self.on_finished = on_finished or (lambda: None)

        self.items: List[ArticleItem] = []
        self.history_mgr = HistoryManager(app_dir)
        self.task_queue = queue.Queue()
        self.stop_requested = False
        self.is_running = False
        self.current_mode = "rewrite_and_post"
        self.auto_retry_passes = 0
        self.max_auto_retries = 2
        self._threads: List[threading.Thread] = []

    def set_items(self, contents: List[str], force_post: bool = False, source_files: Dict[str, str] = None):
        self.source_files = source_files or {}
        self.items = []
        for i, c in enumerate(contents):
            c_clean = c.strip()
            if c_clean:
                sf = self.source_files.get(c_clean, "")
                self.items.append(ArticleItem(i + 1, c_clean, force_post, source_file=sf))
        self.auto_retry_passes = 0

    def start(self, mode: str = "rewrite_and_post"):
        """
        Bắt đầu xử lý hàng đợi bài viết.
        mode: 'rewrite_only' hoặc 'rewrite_and_post'
        """
        if self.is_running:
            return

        self.stop_requested = False
        self.is_running = True
        self.current_mode = mode
        self.task_queue = queue.Queue()

        pending_count = 0
        for item in self.items:
            if item.status in ("Pending", "Failed", "Cancelled"):
                item.status = "Pending"
                item.error = ""
                self.task_queue.put(item)
                pending_count += 1
                self.on_item_updated(item)

        if pending_count == 0:
            self.log("Không có bài viết nào cần xử lý!", "WARNING")
            self.is_running = False
            self.on_finished()
            return

        n_threads = max(1, min(int(self.config.get("performance", {}).get("n_threads", 3)), 8))
        self.log(f"🚀 Khởi chạy {n_threads} luồng xử lý cho {pending_count} bài viết (Chế độ: {'Xào & Đăng + Kiểm Duyệt Web' if mode == 'rewrite_and_post' else 'Chỉ Xào AI'})...", "INFO")

        self._threads = []
        for i in range(n_threads):
            t = threading.Thread(target=self._worker_loop, args=(i + 1, mode), daemon=True)
            self._threads.append(t)
            t.start()

        threading.Thread(target=self._monitor_completion, daemon=True).start()

    def _worker_loop(self, thread_id: int, mode: str):
        ai_cfg = self.config.get("ai", {})
        provider = ai_cfg.get("provider", "gemini")
        if provider in ("openai", "openai_9router", "9router"):
            api_key = ai_cfg.get("openai_api_key", "")
            model = ai_cfg.get("openai_model", "gpt-4o-mini")
            base_url = ai_cfg.get("openai_base_url", "https://api.9router.com/v1")
        else:
            gemini_legacy = self.config.get("gemini", {})
            api_key = ai_cfg.get("gemini_api_key") or gemini_legacy.get("api_key", "")
            model = ai_cfg.get("gemini_model") or gemini_legacy.get("model", "gemini-3.7-flash")
            base_url = ""

        website_cfg = self.config.get("website", {})
        art_cfg = self.config.get("article", {})
        delay_sec = int(self.config.get("performance", {}).get("delay", 5))

        ai_engine = GeminiEngine(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            log_cb=self.log
        )

        publisher = CMSPublisher(
            base_url=website_cfg.get("base_url", "https://jesusvibe.danhngon.pro"),
            token=website_cfg.get("token", ""),
            cookie=website_cfg.get("cookie", ""),
            create_url=website_cfg.get("create_url", ""),
            log_cb=self.log
        )

        while not self.stop_requested:
            try:
                item: ArticleItem = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                break

            if self.stop_requested:
                item.status = "Cancelled"
                self.on_item_updated(item)
                self.task_queue.task_done()
                break

            # Kiểm tra chống đăng trùng
            if not item.force_post and self.history_mgr.is_posted(item.content):
                self.log(f"⚠️ [T{thread_id}] [Bài #{item.id:03d}] Đã từng được đăng trước đó! (Bỏ qua)", "WARNING")
                item.status = "Success"
                item.is_verified = True
                item.error = "Đã đăng trước đó (Skip duplicate)"
                self.on_item_updated(item)
                self.task_queue.task_done()
                continue

            text_to_rewrite = item.content
            orig_images = []
            orig_iframes = []

            # Bước 0: Nếu đầu vào là đường link URL -> Bóc tách nội dung bài báo gốc
            if item.is_url:
                item.status = "Fetching"
                self.on_item_updated(item)
                self.log(f"[T{thread_id}] [Bài #{item.id:03d}] Đang cào nội dung bài báo gốc từ URL: {item.content[:65]}...", "INFO")

                fetch_ok, parsed_data, fetch_err = art_fetch_and_parse_url(item.content)
                if not fetch_ok:
                    item.status = "Failed"
                    item.error = f"Lỗi cào bài: {fetch_err}"
                    self.log(f"❌ [T{thread_id}] [Bài #{item.id:03d}] Cào bài thất bại: {fetch_err}", "ERROR")
                    self.on_item_updated(item)
                    self.task_queue.task_done()
                    continue

                item.orig_title = parsed_data.get("title", "")
                text_to_rewrite = parsed_data.get("text_content", "")
                orig_images = parsed_data.get("content_images", [])
                orig_iframes = parsed_data.get("iframes", [])
                self.log(f"📄 [T{thread_id}] [Bài #{item.id:03d}] Bóc tách thành công: '{item.orig_title[:50]}...' ({len(text_to_rewrite)} ký tự)", "INFO")

            # Bước 1: AI Rewrite
            item.status = "Rewriting"
            self.on_item_updated(item)
            provider_label = "9Router/OpenAI" if provider in ("openai", "openai_9router", "9router") else "Google Gemini"
            self.log(f"[T{thread_id}] [Bài #{item.id:03d}] Bắt đầu xào bài qua AI ({provider_label} - {model})...", "INFO")

            target_lang = ai_cfg.get("language") or self.config.get("gemini", {}).get("language", "English")
            custom_prompt = ai_cfg.get("custom_prompt") or self.config.get("gemini", {}).get("custom_prompt", "")

            if item.orig_title:
                text_payload = f"SOURCE TITLE: {item.orig_title}\n\n{text_to_rewrite}"
            else:
                text_payload = text_to_rewrite

            ok, title, body, err = ai_engine.rewrite_article(
                original_text=text_payload,
                target_language=target_lang,
                custom_prompt=custom_prompt
            )

            if not ok:
                item.status = "Failed"
                item.error = f"Lỗi AI ({provider_label}): {err}"
                self.log(f"❌ [T{thread_id}] [Bài #{item.id:03d}] Xào bài thất bại: {err}", "ERROR")
                self.on_item_updated(item)
                self.task_queue.task_done()
                continue

            item.title = title
            item.body = body

            # Nếu chỉ chọn chế độ Rewrite
            if mode == "rewrite_only":
                item.status = "Success"
                item.is_verified = True
                item.error = "Đã xào xong (Chế độ chỉ AI)"
                self.log(f"✅ [T{thread_id}] [Bài #{item.id:03d}] Đã xào xong: '{title[:50]}...' (Không đăng)", "SUCCESS")
                self.on_item_updated(item)
                self.task_queue.task_done()
                time.sleep(delay_sec)
                continue

            # Bước 2: Post lên CMS
            item.status = "Posting"
            self.on_item_updated(item)
            self.log(f"[T{thread_id}] [Bài #{item.id:03d}] Đang đăng bài lên CMS...", "INFO")

            post_ok, art_link, post_err = publisher.post_article(
                title=title,
                body=body,
                art_display=art_cfg.get("art_display", True),
                art_home=art_cfg.get("art_home", True),
                art_top=art_cfg.get("art_top", True),
                embed_code=art_cfg.get("embed_code", ""),
                embed_pos=art_cfg.get("embed_pos", "Sau đoạn đầu")
            )

            if not post_ok:
                item.status = "Failed"
                item.error = f"Lỗi CMS: {post_err}"
                self.log(f"❌ [T{thread_id}] [Bài #{item.id:03d}] Đăng bài thất bại: {post_err}", "ERROR")
                self.on_item_updated(item)
                self.task_queue.task_done()
                time.sleep(delay_sec)
                continue

            item.result_id = art_link
            self.log(f"🌐 [T{thread_id}] [Bài #{item.id:03d}] CMS đã tạo bài: {art_link}. Đang tiến hành kiểm tra trên Web...", "INFO")

            # Bước 3: Kiểm tra xác minh xem bài báo mới đã thực sự có trên Web hay chưa
            item.status = "Verifying"
            self.on_item_updated(item)
            time.sleep(1.0)

            live_ok, live_msg = verify_article_on_web(art_link, expected_title=title, timeout=15)
            if live_ok:
                item.status = "Success"
                item.is_verified = True
                item.error = "✅ Đã có trên Web (200 OK)"
                self.history_mgr.mark_posted(item.content, title, art_link)
                self.log(f"🎉 [T{thread_id}] [Bài #{item.id:03d}] XÁC MINH THÀNH CÔNG: Bài mới đã hiển thị trực tiếp trên Web! Link: {art_link}", "SUCCESS")

                # Cập nhật tiêu đề mới và đường link mới vào đúng vị trí file .txt ban đầu
                if item.source_file and os.path.exists(item.source_file):
                    w_ok, w_err = write_result_to_source_file(item.source_file, title, art_link)
                    if w_ok:
                        folder_name = os.path.basename(os.path.dirname(item.source_file))
                        file_name = os.path.basename(item.source_file)
                        self.log(f"📝 [T{thread_id}] [Bài #{item.id:03d}] Đã dán Tiêu đề mới & Link mới vào: {folder_name}\\{file_name}", "INFO")
                    else:
                        self.log(f"⚠️ [T{thread_id}] [Bài #{item.id:03d}] Lỗi ghi file .txt ban đầu: {w_err}", "WARNING")
            else:
                item.status = "Failed"
                item.is_verified = False
                item.error = f"Chưa hiển thị trên Web ({live_msg})"
                self.log(f"⚠️ [T{thread_id}] [Bài #{item.id:03d}] Đăng CMS thành công nhưng chưa xác minh được trên Web: {live_msg}", "WARNING")

            self.on_item_updated(item)
            self.task_queue.task_done()
            time.sleep(delay_sec)

    def _monitor_completion(self):
        """Giám sát quá trình xử lý, kiểm duyệt đủ số lượng bài và tự động làm lại các bài thiếu"""
        for t in self._threads:
            t.join()

        if self.stop_requested:
            self.is_running = False
            self.log("⏹ Tiến trình đã được người dùng dừng lại!", "WARNING")
            self.on_finished()
            return

        total_count = len(self.items)
        success_verified = [
            it for it in self.items
            if it.status == "Success" and (self.current_mode == "rewrite_only" or it.is_verified)
        ]
        failed_or_missing = [it for it in self.items if it not in success_verified]

        # Kiểm tra nếu còn bài thiếu và chưa quá số lần thử tự động
        if failed_or_missing and self.auto_retry_passes < self.max_auto_retries and not self.stop_requested:
            self.auto_retry_passes += 1
            missing_ids = [f"#{it.id:03d}" for it in failed_or_missing[:8]]
            missing_preview = ", ".join(missing_ids) + (f" và {len(failed_or_missing)-8} bài khác" if len(failed_or_missing) > 8 else "")

            self.log(f"🔄 [KIỂM DUYỆT TỰ ĐỘNG] Phát hiện {len(failed_or_missing)}/{total_count} bài chưa có trên web hoặc bị lỗi: [{missing_preview}].", "WARNING")
            self.log(f"⚡ Đang tự động làm lại các bài chưa xong (Lượt thử {self.auto_retry_passes}/{self.max_auto_retries}) để đảm bảo chuẩn số lượng {total_count} bài, không thiếu không thừa...", "INFO")

            self.task_queue = queue.Queue()
            for it in failed_or_missing:
                it.status = "Pending"
                it.error = f"Đang làm lại lượt {self.auto_retry_passes}..."
                it.retry_count += 1
                self.task_queue.put(it)
                self.on_item_updated(it)

            n_threads = max(1, min(int(self.config.get("performance", {}).get("n_threads", 3)), 8))
            self._threads = []
            for i in range(n_threads):
                t = threading.Thread(target=self._worker_loop, args=(i + 1, self.current_mode), daemon=True)
                self._threads.append(t)
                t.start()

            threading.Thread(target=self._monitor_completion, daemon=True).start()
            return

        self.is_running = False
        final_success = [
            it for it in self.items
            if it.status == "Success" and (self.current_mode == "rewrite_only" or it.is_verified)
        ]
        final_failed = len(self.items) - len(final_success)

        if final_failed == 0 and total_count > 0:
            updated_count = sum(1 for it in self.items if it.source_file and os.path.exists(it.source_file))
            file_info = f" Đã dán tiêu đề mới & link mới vào {updated_count} file .txt ban đầu." if updated_count > 0 else ""
            self.log(f"🏆 [HOÀN TẤT CHUẨN XÁC 100%] Toàn bộ {total_count}/{total_count} bài báo đã được xào, đăng và xác minh hiển thị trực tiếp trên Web!{file_info} (Không thiếu, không thừa).", "SUCCESS")
        else:
            self.log(f"🏁 Đã xử lý xong hàng đợi: {len(final_success)}/{total_count} bài thành công trên Web. Còn {final_failed} bài chưa đạt. (Bạn có thể bấm '🔄 Thử Lại Bài Lỗi' để làm tiếp).", "WARNING")

        self.on_finished()

    def stop(self):
        if not self.is_running:
            return
        self.log("⏹ Đang yêu cầu dừng an toàn... Đợi các luồng hiện tại hoàn thành lượt...", "WARNING")
        self.stop_requested = True

    def retry_failed(self, mode: str = "rewrite_and_post"):
        """Chạy lại toàn bộ các bài chưa thành công hoặc chưa có mặt trên web"""
        if self.is_running:
            return

        self.auto_retry_passes = 0
        missing_count = 0
        for item in self.items:
            if item.status != "Success" or (mode == "rewrite_and_post" and not item.is_verified):
                item.status = "Pending"
                item.error = ""
                missing_count += 1
                self.on_item_updated(item)

        if missing_count > 0:
            self.log(f"🔄 Bắt đầu làm lại {missing_count} bài chưa có trên web hoặc bị lỗi...", "INFO")
            self.start(mode)
        else:
            self.log("✅ Tất cả bài báo đều đã được xào, đăng và có mặt đầy đủ trên Web!", "SUCCESS")
