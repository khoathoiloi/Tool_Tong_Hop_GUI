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
import random
import urllib.parse
import threading
from html import unescape as html_unescape
from typing import List, Dict, Any, Callable, Tuple
import requests

from .text_utils import clean_mojibake_and_typography
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

        # Đảm bảo giải mã UTF-8 chuẩn xác, tránh lỗi font / mojibake khi thiếu header charset
        try:
            html = r.content.decode("utf-8", errors="replace")
        except Exception:
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
        title = clean_mojibake_and_typography(title)

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

        text_only = clean_mojibake_and_typography(text_only)

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


def write_result_to_source_file(file_path: str, new_title: str, new_link: str, orig_title: str = "") -> Tuple[bool, str]:
    """
    Dán tiêu đề mới và đường link mới của bài báo vào file .txt ban đầu đã được lấy.
    Tự động xóa tiêu đề cũ trong file để tránh bị nhầm lẫn giữa tiêu đề cũ và mới.
    """
    if not file_path or not os.path.exists(file_path):
        return False, f"Đường dẫn file không tồn tại: {file_path}"
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 1. Làm sạch khối kết quả cũ nếu đã có để tránh trùng lặp khi chạy lại
        block_pattern = re.compile(r'\n*-{10,}\s*\[KẾT QUẢ XÀO BÀI MỚI\].*?-{10,}', re.S)
        content_clean = block_pattern.sub('', content).strip()

        # 2. Xóa tiêu đề cũ trong file .txt để tránh nhầm lẫn
        lines = content_clean.splitlines()
        new_lines = []
        orig_clean = orig_title.strip().lower() if orig_title else ""

        for line in lines:
            stripped = line.strip()
            if not stripped:
                new_lines.append("")
                continue

            # Xóa các dòng có tiền tố tiêu đề (Tiêu đề, Tiêu đề đã đăng, Title, Tiêu đề cũ, Tiêu đề gốc, v.v.)
            if re.match(r'^(tiêu\s*đề(\s*(đã\s*đăng|gốc|cũ|bài\s*viết))?|title|original\s*title)\s*:', stripped, re.I):
                continue

            # Xóa dòng nếu trùng khớp với tiêu đề bài báo gốc (orig_title)
            if orig_clean and len(orig_clean) >= 5:
                line_lower = stripped.lower()
                if line_lower == orig_clean or orig_clean in line_lower:
                    continue

            new_lines.append(line)

        content_clean = "\n".join(new_lines).strip()
        content_clean = re.sub(r'\n{3,}', '\n\n', content_clean)

        clean_title = clean_mojibake_and_typography(new_title)
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        new_block = (
            "\n\n"
            "--------------------------------------------------\n"
            "[KẾT QUẢ XÀO BÀI MỚI]\n"
            f"Tiêu đề mới: {clean_title}\n"
            f"Link báo mới: {new_link}\n"
            f"Thời gian xào & đăng: {now_str}\n"
            "--------------------------------------------------"
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content_clean + new_block + "\n")
        return True, ""
    except Exception as e:
        return False, f"Lỗi ghi file {os.path.basename(file_path)}: {str(e)}"


def art_youtube_id(url: str) -> str:
    """Trích xuất YouTube video ID từ URL bất kỳ"""
    if not url:
        return ""
    m = re.search(r'(?:youtube\.com/(?:watch\?v=|embed/|shorts/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})', str(url), re.I)
    return m.group(1) if m else ""


def art_embed_html(source: str, autoplay: bool = False) -> str:
    """Tạo mã HTML responsive iframe từ link YouTube, iframe thô hoặc video URL"""
    source = str(source or "").strip()
    if not source:
        return ""
    if source.lower().startswith("<iframe") and "</iframe>" in source.lower():
        return (
            '<div style="text-align:center;margin:18px 0">'
            '<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;border-radius:8px">'
            f'{source}</div></div>'
        )
    yid = art_youtube_id(source)
    if yid:
        auto_param = "&autoplay=1&mute=1" if autoplay else ""
        src = f"https://www.youtube.com/embed/{yid}?rel=0&modestbranding=1&playsinline=1{auto_param}"
        return (
            '<div style="text-align:center;margin:18px 0">'
            '<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;border-radius:8px">'
            f'<iframe src="{src}" style="position:absolute;top:0;left:0;width:100%;height:100%;border:0" '
            'title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
            'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen loading="lazy"></iframe></div></div>'
        )
    if source.lower().startswith("http"):
        return (
            '<div style="text-align:center;margin:18px 0">'
            '<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;border-radius:8px">'
            f'<iframe src="{source}" style="position:absolute;top:0;left:0;width:100%;height:100%;border:0" '
            'frameborder="0" allowfullscreen loading="lazy"></iframe></div></div>'
        )
    return ""


def art_build_html(
    description: str,
    image_urls: List[str] = None,
    embed_source: str = "",
    embed_pos: str = "Sau đoạn đầu"
) -> str:
    """
    Ghép bài viết mới dạng HTML theo chuẩn Golden ToolXaoBaiBao_V3:
    - Rải đều toàn bộ hình ảnh minh họa xen kẽ giữa các đoạn văn.
    - Nhúng video / iframe responsive tại vị trí người dùng cấu hình.
    """
    text = (description or "").strip()
    if not text:
        return ""

    blocks = [b.strip() for b in re.split(r'\n{2,}', text) if b.strip()]
    while blocks and blocks[0].lstrip().startswith('# ') and not blocks[0].lstrip().startswith('## '):
        blocks = blocks[1:]

    imgs = [u.strip() for u in (image_urls or []) if u and str(u).strip().startswith('http')]
    embed_html = art_embed_html(embed_source) if embed_source else ""

    def _img(u):
        return f'<p style="text-align:center"><img src="{u}" alt="" style="max-width:100%;height:auto;border-radius:8px" /></p>'

    def _blk(b):
        b = b.strip()
        if not b:
            return ""
        if b.startswith("### "):
            return f"<h3>{b[4:].strip()}</h3>"
        elif b.startswith("## "):
            return f"<h2>{b[3:].strip()}</h2>"
        elif b.startswith("# "):
            return f"<h1>{b[2:].strip()}</h1>"
        elif b.startswith(("- ", "* ")):
            lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
            items = "".join([f"<li>{re.sub(r'^[-*]\s*', '', ln)}</li>" for ln in lines])
            return f"<ul>{items}</ul>"
        elif re.match(r'^\d+[.)]\s+', b):
            lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
            items = "".join([f"<li>{re.sub(r'^\d+[.)]\s*', '', ln)}</li>" for ln in lines])
            return f"<ol>{items}</ol>"
        elif b.startswith("<p>") or b.startswith("<div>") or b.startswith("<h"):
            return b
        else:
            return f"<p>{b}</p>"

    def _place_embed(_out):
        if not embed_html:
            return "\n".join(_out)

        pos_val = str(embed_pos or "after_first").strip().lower()
        if "đầu" in pos_val or "dau" in pos_val or "top" in pos_val:
            pos = "top"
        elif "cuối" in pos_val or "cuoi" in pos_val or "bottom" in pos_val or "end" in pos_val:
            pos = "bottom"
        elif "cả" in pos_val or "both" in pos_val:
            pos = "both"
        else:
            pos = "after_first"

        if pos in ("top", "both"):
            _out = [embed_html] + _out

        if pos == "after_first":
            _i = 0
            for _k, _h in enumerate(_out):
                if _h.startswith("<p>"):
                    _i = _k + 1
                    break
            _out = _out[:_i] + [embed_html] + _out[_i:]

        if pos in ("bottom", "both"):
            _i = len(_out)
            for _k in range(len(_out) - 1, -1, -1):
                if _out[_k].startswith("<p>"):
                    _i = _k + 1
                    break
            _out = _out[:_i] + [embed_html] + _out[_i:]

        return "\n".join(_out)

    if not blocks:
        if imgs:
            return _place_embed([_img(imgs[0])])
        return _place_embed([])

    # Phân bổ ảnh vào các vị trí ngẫu nhiên ở khoảng giữa thân bài
    # Bỏ qua đoạn 1 (tránh dồn ứ với ảnh bìa Thumbnail) và đoạn cuối cùng
    n_blocks = len(blocks)
    n_imgs = min(len(imgs), 6)

    chosen_positions = set()
    if n_blocks >= 4 and n_imgs > 0:
        # Vùng giữa thân bài: từ sau đoạn 2 (index 1) đến trước đoạn cuối (index n_blocks - 2)
        eligible = list(range(1, n_blocks - 1))
        k_place = min(n_imgs, len(eligible))
        seg_size = len(eligible) / k_place
        for s_i in range(k_place):
            start_idx = int(s_i * seg_size)
            end_idx = int((s_i + 1) * seg_size)
            sub = eligible[start_idx:end_idx]
            if sub:
                chosen_positions.add(random.choice(sub))
            else:
                chosen_positions.add(eligible[min(start_idx, len(eligible) - 1)])
    elif n_blocks in (2, 3) and n_imgs > 0:
        chosen_positions.add(1 if n_blocks == 3 else 0)
    elif n_blocks == 1 and n_imgs > 0:
        chosen_positions.add(0)

    out = []
    img_idx = 0
    for i, b in enumerate(blocks):
        out.append(_blk(b))
        if i in chosen_positions and img_idx < len(imgs):
            out.append(_img(imgs[img_idx]))
            img_idx += 1

    return _place_embed(out)


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
            model = ai_cfg.get("openai_model", "bao")
            base_url = ai_cfg.get("openai_base_url", "http://127.0.0.1:20128/v1")
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
            orig_cover_image = ""
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
                orig_cover_image = parsed_data.get("cover_image", "")
                orig_images = parsed_data.get("content_images", [])
                orig_iframes = parsed_data.get("iframes", [])
                if not orig_cover_image and orig_images:
                    orig_cover_image = orig_images[0]
                self.log(f"📄 [T{thread_id}] [Bài #{item.id:03d}] Bóc tách thành công: '{item.orig_title[:50]}...' ({len(text_to_rewrite)} ký tự, {len(orig_images)} ảnh)", "INFO")

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

            # Ghép hình ảnh và mã Embed vào bài viết mới dạng HTML hoàn chỉnh
            embed_to_use = art_cfg.get("embed_code", "").strip()
            if not embed_to_use and art_cfg.get("keep_old_embed", True) and orig_iframes:
                embed_to_use = orig_iframes[0]

            final_body = art_build_html(
                description=body,
                image_urls=orig_images,
                embed_source=embed_to_use,
                embed_pos=art_cfg.get("embed_pos", "Sau đoạn đầu")
            )
            item.body = final_body

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
            if orig_images or orig_cover_image:
                self.log(f"🖼️ [T{thread_id}] [Bài #{item.id:03d}] Đã ghép {len(orig_images)} ảnh vào bài, Thumbnail: {orig_cover_image[:65]}...", "INFO")

            post_ok, art_link, post_err = publisher.post_article(
                title=title,
                body=final_body,
                image_path=orig_cover_image,
                art_display=art_cfg.get("art_display", True),
                art_home=art_cfg.get("art_home", True),
                art_top=art_cfg.get("art_top", True),
                embed_code="", # Đã được xử lý nhúng trong final_body qua art_build_html
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
                    w_ok, w_err = write_result_to_source_file(item.source_file, title, art_link, orig_title=item.orig_title)
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
