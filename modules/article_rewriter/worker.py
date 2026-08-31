# -*- coding: utf-8 -*-
"""
modules/article_rewriter/worker.py
Quản lý Hàng Đợi bài viết, xử lý đa luồng (Multi-threading), cô lập lỗi (Error Isolation), và Dừng an toàn (Safe Stop).
"""
import time
import threading
import queue
from typing import List, Dict, Any, Callable
from .gemini_engine import GeminiEngine
from .cms_publisher import CMSPublisher
from .history_manager import HistoryManager

class ArticleItem:
    def __init__(self, item_id: int, content: str, force_post: bool = False):
        self.id = item_id
        self.content = content.strip()
        self.status = "Pending" # Pending, Rewriting, Posting, Success, Failed, Cancelled
        self.title = ""
        self.body = ""
        self.result_id = ""
        self.error = ""
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
        self._threads: List[threading.Thread] = []

    def set_items(self, contents: List[str], force_post: bool = False):
        self.items = [ArticleItem(i + 1, c, force_post) for i, c in enumerate(contents) if c.strip()]

    def start(self, mode: str = "rewrite_and_post"):
        """
        Bắt đầu xử lý hàng đợi bài viết.
        mode: 'rewrite_only' hoặc 'rewrite_and_post'
        """
        if self.is_running:
            return

        self.stop_requested = False
        self.is_running = True
        self.task_queue = queue.Queue()

        # Đẩy các item Pending vào queue
        pending_count = 0
        for item in self.items:
            if item.status in ("Pending", "Failed"):
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
        self.log(f"🚀 Khởi chạy {n_threads} luồng xử lý cho {pending_count} bài viết...", "INFO")

        self._threads = []
        for i in range(n_threads):
            t = threading.Thread(target=self._worker_loop, args=(i + 1, mode), daemon=True)
            self._threads.append(t)
            t.start()

        # Thread giám sát hoàn thành
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
                self.log(f"⚠️ Bài #{item.id:03d} đã từng được đăng trước đó! (Bỏ qua)", "WARNING")
                item.status = "Success"
                item.error = "Đã đăng trước đó (Skip duplicate)"
                self.on_item_updated(item)
                self.task_queue.task_done()
                continue

            # Bước 1: AI Rewrite
            item.status = "Rewriting"
            self.on_item_updated(item)
            provider_label = "9Router/OpenAI" if provider in ("openai", "openai_9router", "9router") else "Google Gemini"
            self.log(f"[T{thread_id}] [Bài #{item.id:03d}] Bắt đầu xào bài qua AI ({provider_label} - {model})...", "INFO")

            target_lang = ai_cfg.get("language") or self.config.get("gemini", {}).get("language", "English")
            custom_prompt = ai_cfg.get("custom_prompt") or self.config.get("gemini", {}).get("custom_prompt", "")

            ok, title, body, err = ai_engine.rewrite_article(
                original_text=item.content,
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
                self.log(f"✅ [T{thread_id}] [Bài #{item.id:03d}] Đã xào xong (Không đăng)!", "SUCCESS")
                self.on_item_updated(item)
                self.task_queue.task_done()
                time.sleep(delay_sec)
                continue

            # Bước 2: Post lên CMS
            item.status = "Posting"
            self.on_item_updated(item)
            self.log(f"[T{thread_id}] [Bài #{item.id:03d}] Đang đăng bài lên CMS...", "INFO")

            post_ok, art_id, post_err = publisher.post_article(
                title=title,
                body=body,
                art_display=art_cfg.get("art_display", True),
                art_home=art_cfg.get("art_home", True),
                art_top=art_cfg.get("art_top", True),
                embed_code=art_cfg.get("embed_code", ""),
                embed_pos=art_cfg.get("embed_pos", "Sau đoạn đầu")
            )

            if post_ok:
                item.status = "Success"
                item.result_id = art_id
                self.history_mgr.mark_posted(item.content, title, art_id)
                self.log(f"🎉 [T{thread_id}] [Bài #{item.id:03d}] Hoàn thành xuất bản thành công! ID: {art_id}", "SUCCESS")
            else:
                item.status = "Failed"
                item.error = f"Lỗi CMS: {post_err}"
                self.log(f"❌ [T{thread_id}] [Bài #{item.id:03d}] Đăng bài thất bại: {post_err}", "ERROR")

            self.on_item_updated(item)
            self.task_queue.task_done()
            time.sleep(delay_sec)

    def _monitor_completion(self):
        for t in self._threads:
            t.join()
        self.is_running = False
        self.log("🏁 Tất cả tiến trình xử lý đã kết thúc!", "SUCCESS")
        self.on_finished()

    def stop(self):
        if not self.is_running:
            return
        self.log("⏹ Đang yêu cầu dừng an toàn... Đợi các luồng hiện tại hoàn thành lượt...", "WARNING")
        self.stop_requested = True

    def retry_failed(self, mode: str = "rewrite_and_post"):
        for item in self.items:
            if item.status in ("Failed", "Cancelled"):
                item.status = "Pending"
                item.error = ""
                self.on_item_updated(item)
        self.start(mode)
