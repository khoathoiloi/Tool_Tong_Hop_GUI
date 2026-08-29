# -*- coding: utf-8 -*-
import os
import json
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core.logger import UILogger
from core.theme import THEME
from modules.excel_fanpage.core import scan_and_prepare_data
from modules.excel_fanpage.excel_writer import export_excel_file, DEFAULT_COMMENT_1
from modules.excel_fanpage.config_mgr import ConfigMgr
from modules.shiftlink_shortener.shortener import shorten_multiple_urls

EXACT_8_DOMAINS = [
    "nextpart2.online",
    "fullstoriesdrama.com",
    "reviewphan2.com",
    "fullguide.tips",
    "phimhay.fit",
    "filmgood.shop",
    "nextpartfull.com",
    "nextfullvideo.com"
]

class ExcelFanpageView(ttk.Frame):
    def __init__(self, parent, root):
        super().__init__(parent)
        self.root = root
        self.cfg_mgr = ConfigMgr()
        self.app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.user_data_dir = os.path.join(self.app_dir, "user_data")
        self.domain_cfg_file = os.path.join(self.app_dir, "user_domains.json")
        self.domains_list = self._load_saved_domains()
        self.stop_requested = False
        self._build_ui()
        self._load_config()

    def _load_saved_domains(self):
        if os.path.exists(self.domain_cfg_file):
            try:
                with open(self.domain_cfg_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, list) and saved:
                        return saved
            except Exception:
                pass
        return list(EXACT_8_DOMAINS)

    def _build_ui(self):
        # Header banner
        header = tk.Frame(self, bg="#1e1e2e", pady=6)
        header.pack(fill=tk.X)
        tk.Label(header, text="📊 TẠO FILE EXCEL FANPAGE REELS + TỰ ĐỘNG RÚT GỌN LINK", font=("Segoe UI", 13, "bold"), bg="#1e1e2e", fg="#89b4fa").pack(side=tk.LEFT, padx=10)
        tk.Label(header, text="Chuẩn mới FBPublisher V5 (13 cột có UID & tách Bình luận 1, 2), tự động rút gọn link", font=("Segoe UI", 9), bg="#1e1e2e", fg="#a6adc8").pack(side=tk.LEFT, padx=5)

        content = tk.Frame(self, bg="#1e1e2e", padx=10, pady=4)
        content.pack(fill=tk.BOTH, expand=True)

        # 1. Box Fanpage FB & Loại File Excel
        grp_page = tk.LabelFrame(content, text=" 1. Danh sách Fanpage Facebook & Định Dạng File Xuất ", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#cdd6f4", padx=8, pady=5)
        grp_page.pack(fill=tk.X, pady=(0, 5))

        # Chọn loại file Excel (13 cột Token V5 vs 11 cột Thường)
        r_type = tk.Frame(grp_page, bg="#24273a")
        r_type.pack(fill=tk.X, pady=(0, 4))
        tk.Label(r_type, text="Định dạng xuất:", width=18, anchor="w", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#cba6f7").pack(side=tk.LEFT)
        
        self.excel_type_var = tk.StringVar(value="token")
        tk.Radiobutton(r_type, text="File Excel Token V5 (13 cột chuẩn FBPublisher V5)", variable=self.excel_type_var, value="token", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#a6e3a1", selectcolor="#313244", activebackground="#24273a", activeforeground="#a6e3a1").pack(side=tk.LEFT, padx=(0, 15))
        tk.Radiobutton(r_type, text="File Excel Thường (11 cột)", variable=self.excel_type_var, value="standard", bg="#24273a", fg="#cdd6f4", selectcolor="#313244", activebackground="#24273a", activeforeground="#89b4fa").pack(side=tk.LEFT)

        # Chế độ nhập liệu Page
        self.input_mode_var = tk.StringVar(value="txt")
        mode_bar = tk.Frame(grp_page, bg="#24273a")
        mode_bar.pack(fill=tk.X, pady=(0, 4))
        
        tk.Radiobutton(mode_bar, text="Nhập từ file TXT danh sách Page", variable=self.input_mode_var, value="txt", command=self._toggle_mode, bg="#24273a", fg="#cdd6f4", selectcolor="#313244", activebackground="#24273a", activeforeground="#89b4fa").pack(side=tk.LEFT, padx=(0, 15))
        tk.Radiobutton(mode_bar, text="Nhập trực tiếp danh sách", variable=self.input_mode_var, value="manual", command=self._toggle_mode, bg="#24273a", fg="#cdd6f4", selectcolor="#313244", activebackground="#24273a", activeforeground="#89b4fa").pack(side=tk.LEFT)

        self.frame_txt = tk.Frame(grp_page, bg="#24273a")
        self.frame_txt.pack(fill=tk.X, pady=2)
        self.entry_txt_path = tk.Entry(self.frame_txt, font=("Segoe UI", 9), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
        self.entry_txt_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        tk.Button(self.frame_txt, text="Chọn File TXT...", font=("Segoe UI", 9), bg="#45475a", fg="#cdd6f4", relief="flat", padx=10, command=self._browse_txt).pack(side=tk.RIGHT)

        self.frame_manual = tk.Frame(grp_page, bg="#24273a")
        self.text_manual = tk.Text(self.frame_manual, height=3, font=("Segoe UI", 9), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
        self.text_manual.pack(fill=tk.X)

        # 2. Box Cấu hình Kho Video & Ghép
        grp_cfg = tk.LabelFrame(content, text=" 2. Cấu hình Kho Video & Bình Luận ", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#cdd6f4", padx=8, pady=5)
        grp_cfg.pack(fill=tk.X, pady=(0, 5))

        # Kho video
        r1 = tk.Frame(grp_cfg, bg="#24273a")
        r1.pack(fill=tk.X, pady=2)
        tk.Label(r1, text="Kho Video:", width=22, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        self.entry_kho = tk.Entry(r1, font=("Segoe UI", 9), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
        self.entry_kho.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        tk.Button(r1, text="Chọn Kho...", font=("Segoe UI", 9), bg="#45475a", fg="#cdd6f4", relief="flat", padx=10, command=self._browse_kho).pack(side=tk.RIGHT)

        # Ratio & Anti-duplicate
        r2 = tk.Frame(grp_cfg, bg="#24273a")
        r2.pack(fill=tk.X, pady=2)
        tk.Label(r2, text="Số Page / 1 Video:", width=22, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        self.spin_ratio = tk.Spinbox(r2, from_=1, to=10, width=5, font=("Segoe UI", 9), bg="#313244", fg="#cdd6f4", buttonbackground="#45475a")
        self.spin_ratio.delete(0, tk.END)
        self.spin_ratio.insert(0, "2")
        self.spin_ratio.pack(side=tk.LEFT, padx=(0, 15))

        self.chk_avoid_dup_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r2, text="Tránh lấy trùng video đã đăng", variable=self.chk_avoid_dup_var, bg="#24273a", fg="#cdd6f4", selectcolor="#313244", activebackground="#24273a", activeforeground="#a6e3a1").pack(side=tk.LEFT)
        tk.Button(r2, text="🔄 Reset Bộ Nhớ", font=("Segoe UI", 8), bg="#585b70", fg="#f9e2af", relief="flat", padx=8, pady=1, command=self._reset_history).pack(side=tk.RIGHT)

        # Domain & Hashtag
        r3 = tk.Frame(grp_cfg, bg="#24273a")
        r3.pack(fill=tk.X, pady=2)
        tk.Label(r3, text="Lọc Domain gốc (link-da-dang):", width=26, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        self.entry_domain = tk.Entry(r3, font=("Segoe UI", 9), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
        self.entry_domain.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        r4 = tk.Frame(grp_cfg, bg="#24273a")
        r4.pack(fill=tk.X, pady=2)
        tk.Label(r4, text="Hashtag gắn kèm:", width=26, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        self.entry_tag = tk.Entry(r4, font=("Segoe UI", 9), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
        self.entry_tag.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        # Text Bình luận 1
        r_bl1 = tk.Frame(grp_cfg, bg="#24273a")
        r_bl1.pack(fill=tk.X, pady=2)
        tk.Label(r_bl1, text="Nội dung Bình luận 1 (V5):", width=26, anchor="w", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#89b4fa").pack(side=tk.LEFT)
        self.entry_comment1 = tk.Entry(r_bl1, font=("Segoe UI", 9), bg="#313244", fg="#a6e3a1", insertbackground="#cdd6f4", relief="flat")
        self.entry_comment1.insert(0, DEFAULT_COMMENT_1)
        self.entry_comment1.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        # Output
        r5 = tk.Frame(grp_cfg, bg="#24273a")
        r5.pack(fill=tk.X, pady=2)
        tk.Label(r5, text="Nơi lưu file Excel:", width=26, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        self.entry_out = tk.Entry(r5, font=("Segoe UI", 9), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
        self.entry_out.insert(0, "E:\\")
        self.entry_out.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        tk.Button(r5, text="Chọn Nơi Lưu...", font=("Segoe UI", 9), bg="#45475a", fg="#cdd6f4", relief="flat", padx=10, command=self._browse_out).pack(side=tk.RIGHT)

        # 3. Box Combo Tự Động Rút Gọn Link ShiftLink
        grp_shorten = tk.LabelFrame(content, text=" 3. Tự Động Rút Gọn Link ShiftLink (Gán Vào Bình Luận 2 / Trả Lời) ", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#89b4fa", padx=8, pady=5)
        grp_shorten.pack(fill=tk.X, pady=(0, 5))

        r_sh1 = tk.Frame(grp_shorten, bg="#24273a")
        r_sh1.pack(fill=tk.X, pady=2)

        self.chk_auto_shorten_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            r_sh1,
            text="⚡ Tự động rút gọn link qua ShiftLink gán vào 'Bình luận 2 (Trả lời)'",
            variable=self.chk_auto_shorten_var,
            font=("Segoe UI", 9, "bold"),
            bg="#24273a",
            fg="#a6e3a1",
            selectcolor="#313244",
            activebackground="#24273a",
            activeforeground="#a6e3a1"
        ).pack(side=tk.LEFT, padx=(0, 15))

        self.chk_show_chrome_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            r_sh1,
            text="Hiện trình duyệt Chrome",
            variable=self.chk_show_chrome_var,
            bg="#24273a",
            fg="#cdd6f4",
            selectcolor="#313244",
            activebackground="#24273a",
            activeforeground="#89b4fa"
        ).pack(side=tk.LEFT)

        r_sh2 = tk.Frame(grp_shorten, bg="#24273a")
        r_sh2.pack(fill=tk.X, pady=2)
        tk.Label(r_sh2, text="Tên miền ShiftLink muốn rút gọn:", width=28, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        
        self.cbo_shorten_domain = ttk.Combobox(r_sh2, values=self.domains_list, state="readonly", width=28)
        if self.domains_list:
            self.cbo_shorten_domain.current(0)
        self.cbo_shorten_domain.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r_sh2, text="(Link rút gọn mới sẽ dán thẳng vào Bình Luận 2 / Trả lời)", font=("Segoe UI", 8, "italic"), bg="#24273a", fg="#a6adc8").pack(side=tk.LEFT)

        # Progress bar
        self.progress = ttk.Progressbar(content, orient="horizontal", mode="determinate")
        self.progress.pack(fill=tk.X, pady=(2, 4))

        # Log box
        log_frame = tk.Frame(content, bg="#11111b", bd=1, relief="solid")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.log_text = tk.Text(log_frame, font=("Consolas", 9), bg="#11111b", fg="#cdd6f4", relief="flat", height=5)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text["yscrollcommand"] = sb.set

        self.logger = UILogger(self.log_text, self.root)

        # Action Buttons
        btn_bar = tk.Frame(content, bg="#1e1e2e")
        btn_bar.pack(fill=tk.X)
        self.btn_check = tk.Button(btn_bar, text="🔍 Kiểm Tra Dữ Liệu", font=("Segoe UI", 9, "bold"), bg="#89b4fa", fg="#11111b", relief="flat", padx=15, pady=6, cursor="hand2", command=self._check_data)
        self.btn_check.pack(side=tk.LEFT)

        self.btn_start = tk.Button(btn_bar, text="🚀 TẠO FILE EXCEL (KÈM RÚT GỌN LINK)", font=("Segoe UI", 10, "bold"), bg="#a6e3a1", fg="#11111b", relief="flat", padx=20, pady=6, cursor="hand2", command=self._start_generate)
        self.btn_start.pack(side=tk.RIGHT)

    def _toggle_mode(self):
        if self.input_mode_var.get() == "txt":
            self.frame_manual.pack_forget()
            self.frame_txt.pack(fill=tk.X, pady=2)
        else:
            self.frame_txt.pack_forget()
            self.frame_manual.pack(fill=tk.X, pady=2)

    def _browse_txt(self):
        f = filedialog.askopenfilename(title="Chọn file TXT danh sách Page", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if f:
            self.entry_txt_path.delete(0, tk.END)
            self.entry_txt_path.insert(0, f)

    def _browse_kho(self):
        f = filedialog.askdirectory(title="Chọn Thư Mục Kho Video")
        if f:
            self.entry_kho.delete(0, tk.END)
            self.entry_kho.insert(0, f)

    def _browse_out(self):
        f = filedialog.askdirectory(title="Chọn Nơi Lưu Kết Quả")
        if f:
            self.entry_out.delete(0, tk.END)
            self.entry_out.insert(0, f)

    def _reset_history(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn xóa bộ nhớ các video đã lấy không?"):
            self.cfg_mgr.reset_history()
            self.logger.warning("Đã reset toàn bộ lịch sử video đã lấy.")

    def _get_pages(self):
        if self.input_mode_var.get() == "txt":
            p_txt = self.entry_txt_path.get().strip()
            if not p_txt or not os.path.exists(p_txt):
                self.logger.error("File TXT danh sách page không tồn tại!")
                return None
            try:
                content = Path(p_txt).read_text(encoding="utf-8", errors="ignore")
                pages = [line.strip() for line in content.splitlines() if line.strip()]
                return pages
            except Exception as e:
                self.logger.error("Lỗi đọc file TXT: " + str(e))
                return None
        else:
            content = self.text_manual.get("1.0", tk.END).strip()
            if not content:
                self.logger.error("Chưa nhập danh sách Page!")
                return None
            return [line.strip() for line in content.splitlines() if line.strip()]

    def _save_config(self):
        self.cfg_mgr.save({
            "kho": self.entry_kho.get().strip(),
            "out": self.entry_out.get().strip(),
            "domain": self.entry_domain.get().strip(),
            "tag": self.entry_tag.get().strip(),
            "ratio": self.spin_ratio.get(),
            "txt": self.entry_txt_path.get().strip(),
            "excel_type": self.excel_type_var.get(),
            "comment_1": self.entry_comment1.get().strip(),
            "auto_shorten": self.chk_auto_shorten_var.get(),
            "shorten_domain": self.cbo_shorten_domain.get().strip()
        })

    def _load_config(self):
        data = self.cfg_mgr.load()
        if data:
            if data.get("kho"): self.entry_kho.insert(0, data.get("kho"))
            if data.get("out"):
                self.entry_out.delete(0, tk.END)
                self.entry_out.insert(0, data.get("out"))
            if data.get("domain"): self.entry_domain.insert(0, data.get("domain"))
            if data.get("tag"): self.entry_tag.insert(0, data.get("tag"))
            if data.get("ratio"): self.spin_ratio.delete(0, tk.END); self.spin_ratio.insert(0, str(data.get("ratio")))
            if data.get("txt"): self.entry_txt_path.insert(0, data.get("txt"))
            if data.get("excel_type"): self.excel_type_var.set(data.get("excel_type"))
            if data.get("comment_1"):
                self.entry_comment1.delete(0, tk.END)
                self.entry_comment1.insert(0, data.get("comment_1"))
            if "auto_shorten" in data: self.chk_auto_shorten_var.set(bool(data.get("auto_shorten")))
            if data.get("shorten_domain") and data.get("shorten_domain") in self.domains_list:
                self.cbo_shorten_domain.set(data.get("shorten_domain"))

    def _check_data(self):
        self.logger.clear()
        self.logger.info("--- BẮT ĐẦU KIỂM TRA DỮ LIỆU ---")
        
        excel_type_name = "File Excel Token V5 (13 cột chuẩn FBPublisher V5)" if self.excel_type_var.get() == "token" else "File Excel Thường (11 cột)"
        self.logger.highlight(f"📋 Định dạng file chọn xuất: {excel_type_name}")

        pages = self._get_pages()
        if pages is None: return
        self.logger.info(f"Số lượng Page hợp lệ: {len(pages)}")

        kho = self.entry_kho.get().strip()
        if not kho or not os.path.isdir(kho):
            self.logger.error("Kho video không hợp lệ: " + str(kho))
            return

        exclude = self.cfg_mgr.get_processed_folders() if self.chk_avoid_dup_var.get() else set()
        items = scan_and_prepare_data(kho, self.entry_domain.get().strip(), self.entry_tag.get().strip(), exclude)
        self.logger.info(f"Số video khả dụng trong kho: {len(items)}")
        if exclude:
            self.logger.info(f"Số folder đã được đánh dấu bỏ qua (đã lấy trước đó): {len(exclude)}")

        try:
            ratio = int(self.spin_ratio.get())
        except Exception:
            ratio = 2
        needed_videos = (len(pages) + ratio - 1) // ratio
        self.logger.info(f"Cần {needed_videos} video cho {len(pages)} Page (Tỉ lệ 1 video / {ratio} Page).")
        
        raw_links_count = sum(1 for item in items[:needed_videos] if item.get("raw_link"))
        self.logger.info(f"Số video có sẵn link gốc cần rút gọn: {raw_links_count} / {min(len(items), needed_videos)}")

        if self.chk_auto_shorten_var.get():
            self.logger.highlight(f"⚡ Đang BẬT chế độ Tự động rút gọn link ShiftLink (Tên miền: {self.cbo_shorten_domain.get()})")

        if len(items) >= needed_videos:
            self.logger.success("✅ ĐỦ VIDEO ĐỂ GHÉP TOÀN BỘ DANH SÁCH PAGE!")
        else:
            self.logger.warning(f"⚠️ THIẾU {needed_videos - len(items)} VIDEO! Sẽ ghép được {len(items) * ratio}/{len(pages)} Page.")

    def _start_generate(self):
        self._save_config()
        self.logger.clear()
        self.logger.info("--- BẮT ĐẦU TIẾN TRÌNH TẠO FILE EXCEL FANPAGE ---")
        
        pages = self._get_pages()
        if not pages: return
        
        kho = self.entry_kho.get().strip()
        if not kho or not os.path.isdir(kho):
            self.logger.error("Vui lòng chọn Kho Video hợp lệ!")
            return

        out = self.entry_out.get().strip() or "E:\\"
        
        try:
            ratio = int(self.spin_ratio.get())
        except Exception:
            ratio = 2

        excel_type = self.excel_type_var.get()
        excel_type_label = "File Excel Token V5 (13 cột chuẩn FBPublisher V5)" if excel_type == "token" else "File Excel Thường (11 cột)"
        self.logger.highlight(f"📋 Định dạng file xuất: {excel_type_label}")

        auto_shorten = self.chk_auto_shorten_var.get()
        shorten_domain = self.cbo_shorten_domain.get().strip() or "nextpart2.online"
        show_chrome = self.chk_show_chrome_var.get()
        comment1_text = self.entry_comment1.get().strip() or DEFAULT_COMMENT_1

        self.btn_start.config(state=tk.DISABLED)
        self.btn_check.config(state=tk.DISABLED)
        self.progress["value"] = 5

        def _worker():
            try:
                exclude = self.cfg_mgr.get_processed_folders() if self.chk_avoid_dup_var.get() else set()
                items = scan_and_prepare_data(kho, self.entry_domain.get().strip(), self.entry_tag.get().strip(), exclude)
                
                if not items:
                    self.logger.error("Không tìm thấy video hợp lệ nào trong kho!")
                    return

                needed_videos = (len(pages) + ratio - 1) // ratio
                selected_items = items[:needed_videos]

                # ⚡ NẾU BẬT TỰ ĐỘNG RÚT GỌN LINK
                if auto_shorten:
                    raw_urls_to_shorten = [it["raw_link"] for it in selected_items if it.get("raw_link")]
                    if raw_urls_to_shorten:
                        self.logger.highlight(f"🔗 Đang rút gọn {len(raw_urls_to_shorten)} link qua ShiftLink (Tên miền: {shorten_domain})...")
                        
                        def _log_cb(msg, lvl="INFO"):
                            self.logger.log(msg, lvl)

                        def _prog_shorten(cur, tot):
                            pct = int(cur / tot * 50) + 10
                            self.progress["value"] = pct

                        def _stop_check():
                            return False

                        url_map = shorten_multiple_urls(
                            raw_urls=raw_urls_to_shorten,
                            selected_domain=shorten_domain,
                            show_browser=show_chrome,
                            user_data_dir=self.user_data_dir,
                            log_cb=_log_cb,
                            progress_cb=_prog_shorten,
                            stop_check_cb=_stop_check
                        )

                        shortened_applied = 0
                        for it in selected_items:
                            orig_link = it.get("raw_link", "")
                            if orig_link in url_map:
                                new_short_url = url_map[orig_link]
                                it["raw_link"] = new_short_url
                                it["first_comment"] = f"{comment1_text} {new_short_url}"
                                shortened_applied += 1

                        self.logger.success(f"✅ Đã gán {shortened_applied} link rút gọn mới vào 'Bình luận 2 (Trả lời)'!")
                    else:
                        self.logger.warning("Các folder video không có dòng link gốc trong link-da-dang.txt để rút gọn.")

                # Xuất file Excel với đúng định dạng (13 cột chuẩn V5 hoặc 11 cột)
                def _prog(cur, total, msg):
                    pct = int(cur / total * 40) + 60
                    self.progress["value"] = pct
                    self.logger.info(msg)

                result = export_excel_file(
                    valid_items=selected_items,
                    pages=pages,
                    pages_per_video=ratio,
                    kho_path_str=kho,
                    output_dir_str=out,
                    progress_cb=_prog,
                    excel_type=excel_type,
                    comment1_text=comment1_text
                )
                
                if self.chk_avoid_dup_var.get() and result["used_folders"]:
                    self.cfg_mgr.add_processed_folders(result["used_folders"])

                self.progress["value"] = 100
                self.logger.success("🎉 ĐÃ XUẤT FILE EXCEL THÀNH CÔNG!")
                self.logger.highlight(f"📁 File Excel: {result['excel_path']} ({excel_type_label})")
                self.logger.success(f"✅ Đã xử lý: {result['total_pages_done']} Page ({result['total_videos_used']} video)")
                if result["total_pages_left"] > 0:
                    self.logger.warning(f"⚠️ Page chưa ghép (do thiếu video): {result['total_pages_left']} (Lưu tại: {result['unused_file']})")

                messagebox.showinfo("Thành công", f"ĐÃ TẠO FILE EXCEL VÀ RÚT GỌN LINK THÀNH CÔNG!\n\n📁 File Excel:\n{result['excel_path']}\n\n📋 Loại: {excel_type_label}\n✅ Đã xử lý: {result['total_pages_done']} Page.")
            except Exception as e:
                self.logger.error(f"Lỗi trong quá trình xử lý: {e}")
                messagebox.showerror("Lỗi", f"Lỗi: {e}")
            finally:
                self.btn_start.config(state=tk.NORMAL)
                self.btn_check.config(state=tk.NORMAL)

        threading.Thread(target=_worker, daemon=True).start()