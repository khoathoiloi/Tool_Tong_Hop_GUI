# -*- coding: utf-8 -*-
"""
modules/article_rewriter/view.py
Giao diện người dùng Tab Xào Bài Báo (AI Article Rewriter & CDP CMS Publisher)
Chuẩn Dark Theme Catppuccin Macchiato đồng bộ với MasterToolHub.
"""
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Dict, Any

from core.theme import THEME
from core.logger import UILogger
from .config import ArticleRewriterConfig
from .auth_manager import AuthManager
from .worker import ArticleWorker, ArticleItem

class ArticleRewriterView(ttk.Frame):
    def __init__(self, parent, root, app_dir: str):
        super().__init__(parent, style="TFrame")
        self.root = root
        self.app_dir = app_dir
        self.cfg_mgr = ArticleRewriterConfig(app_dir)
        self.worker = None

        self._init_variables()
        self._build_ui()
        self._load_values_to_ui()
        self._update_status_badges()

    def _init_variables(self):
        # AI Provider vars (Gemini & OpenAI / 9Router)
        self.v_ai_provider = tk.StringVar(value="Google Gemini")
        self.v_gemini_key = tk.StringVar()
        self.v_gemini_model = tk.StringVar(value="gemini-3.7-flash")
        self.v_openai_base_url = tk.StringVar(value="https://api.9router.com/v1")
        self.v_openai_key = tk.StringVar()
        self.v_openai_model = tk.StringVar(value="gpt-4o-mini")
        self.v_ai_lang = tk.StringVar(value="English")
        self.v_custom_prompt = tk.StringVar()

        # Website vars
        self.v_base_url = tk.StringVar(value="https://jesusvibe.danhngon.pro")
        self.v_login_url = tk.StringVar(value="https://jesusvibe.danhngon.pro/login")
        self.v_username = tk.StringVar()
        self.v_password = tk.StringVar()
        self.v_csrf_token = tk.StringVar()
        self.v_cookie = tk.StringVar()

        # Post vars
        self.v_embed_pos = tk.StringVar(value="Sau đoạn đầu")
        self.v_embed_code = tk.StringVar()
        self.v_keep_old_embed = tk.BooleanVar(value=True)
        self.v_art_display = tk.BooleanVar(value=True)
        self.v_art_home = tk.BooleanVar(value=True)
        self.v_art_top = tk.BooleanVar(value=True)
        self.v_force_post = tk.BooleanVar(value=False)

        # Performance vars
        self.v_threads = tk.StringVar(value="3")
        self.v_delay = tk.StringVar(value="5")

        # Stats
        self.v_stat_total = tk.StringVar(value="0")
        self.v_stat_success = tk.StringVar(value="0")
        self.v_stat_failed = tk.StringVar(value="0")

    def _build_ui(self):
        # Main container with 2 columns
        self.grid_columnconfigure(0, weight=3) # Main working area
        self.grid_columnconfigure(1, weight=2) # Settings sidebar
        self.grid_rowconfigure(0, weight=1)

        # ----------------- LEFT AREA: Workspace -----------------
        left_frame = tk.Frame(self, bg=THEME["bg_main"], padx=15, pady=15)
        left_frame.grid(row=0, column=0, sticky="nsew")
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(2, weight=1) # Treeview expands
        left_frame.grid_rowconfigure(4, weight=1) # Log expands

        # 1. Header & Status Badges
        header_frame = tk.Frame(left_frame, bg=THEME["bg_main"])
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        lbl_title = tk.Label(
            header_frame,
            text="📰 Xào Bài Báo Tự Động (AI Gemini & CDP CMS)",
            font=("Segoe UI", 14, "bold"),
            bg=THEME["bg_main"],
            fg=THEME["accent"]
        )
        lbl_title.pack(side=tk.LEFT)

        # Badge Frame
        self.badge_frame = tk.Frame(header_frame, bg=THEME["bg_main"])
        self.badge_frame.pack(side=tk.RIGHT)

        self.lbl_badge_gemini = tk.Label(self.badge_frame, text="Gemini: ?", font=("Segoe UI", 9, "bold"), bg=THEME["card"], fg=THEME["fg_sub"], padx=8, pady=3)
        self.lbl_badge_gemini.pack(side=tk.LEFT, padx=3)

        self.lbl_badge_auth = tk.Label(self.badge_frame, text="Auth: ?", font=("Segoe UI", 9, "bold"), bg=THEME["card"], fg=THEME["fg_sub"], padx=8, pady=3)
        self.lbl_badge_auth.pack(side=tk.LEFT, padx=3)

        # 2. Input Box Area
        input_card = tk.Frame(left_frame, bg=THEME["card"], padx=12, pady=10, highlightbackground=THEME["border"], highlightthickness=1)
        input_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        input_card.grid_columnconfigure(0, weight=1)

        input_header = tk.Frame(input_card, bg=THEME["card"])
        input_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        tk.Label(input_header, text="📝 Nhập Nội Dung Bài Báo (Cách nhau bằng dòng '---' nếu nhiều bài):", font=("Segoe UI", 10, "bold"), bg=THEME["card"], fg=THEME["fg_text"]).pack(side=tk.LEFT)

        btn_load_file = tk.Button(input_header, text="📂 Chọn File .txt/.docx", font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], activebackground=THEME["accent"], relief="flat", cursor="hand2", padx=8, pady=2, command=self._on_choose_file)
        btn_load_file.pack(side=tk.RIGHT, padx=4)

        btn_add_to_queue = tk.Button(input_header, text="➕ Thêm Vào Hàng Đợi", font=("Segoe UI", 9, "bold"), bg=THEME["accent"], fg="#1e1e2e", activebackground=THEME["accent_hover"], relief="flat", cursor="hand2", padx=10, pady=2, command=self._on_add_to_queue)
        btn_add_to_queue.pack(side=tk.RIGHT)

        self.txt_input = tk.Text(input_card, height=4, font=("Segoe UI", 10), bg=THEME["input"], fg=THEME["fg_text"], insertbackground=THEME["fg_text"], relief="flat", padx=8, pady=6)
        self.txt_input.grid(row=1, column=0, sticky="ew")

        # 3. Queue / Treeview Area
        queue_card = tk.Frame(left_frame, bg=THEME["card"], padx=12, pady=10, highlightbackground=THEME["border"], highlightthickness=1)
        queue_card.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        queue_card.grid_columnconfigure(0, weight=1)
        queue_card.grid_rowconfigure(1, weight=1)

        queue_hdr = tk.Frame(queue_card, bg=THEME["card"])
        queue_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        tk.Label(queue_hdr, text="📋 Danh Sách Bài Viết Trong Hàng Đợi:", font=("Segoe UI", 10, "bold"), bg=THEME["card"], fg=THEME["fg_text"]).pack(side=tk.LEFT)

        # Stats labels
        self.lbl_stats = tk.Label(queue_hdr, text="Tổng: 0 | Thành công: 0 | Lỗi: 0", font=("Segoe UI", 9, "bold"), bg=THEME["card"], fg=THEME["accent"])
        self.lbl_stats.pack(side=tk.RIGHT)

        cols = ("id", "status", "title", "result", "error")
        self.tree = ttk.Treeview(queue_card, columns=cols, show="headings", height=6)
        self.tree.heading("id", text="#")
        self.tree.heading("status", text="Trạng Thái")
        self.tree.heading("title", text="Tiêu Đề Mới")
        self.tree.heading("result", text="Kết Quả / ID")
        self.tree.heading("error", text="Chi Tiết / Lỗi")

        self.tree.column("id", width=40, anchor="center")
        self.tree.column("status", width=90, anchor="center")
        self.tree.column("title", width=220)
        self.tree.column("result", width=90, anchor="center")
        self.tree.column("error", width=180)

        tree_scroll = ttk.Scrollbar(queue_card, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.grid(row=1, column=0, sticky="nsew")
        tree_scroll.grid(row=1, column=1, sticky="ns")

        # 4. Action Buttons Toolbar
        action_bar = tk.Frame(left_frame, bg=THEME["bg_main"])
        action_bar.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        self.btn_auth = tk.Button(
            action_bar,
            text="🔐 Lấy Cookie/Token (CDP)",
            font=("Segoe UI", 9, "bold"),
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#b4befe",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
            command=self._on_auth_cdp
        )
        self.btn_auth.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_rewrite_only = tk.Button(
            action_bar,
            text="✨ Xào Bài (Chỉ AI)",
            font=("Segoe UI", 9, "bold"),
            bg="#cba6f7",
            fg="#1e1e2e",
            activebackground="#f5c2e7",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
            command=lambda: self._on_start_worker("rewrite_only")
        )
        self.btn_rewrite_only.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_rewrite_and_post = tk.Button(
            action_bar,
            text="🚀 Xào & Đăng Tự Động",
            font=("Segoe UI", 9, "bold"),
            bg=THEME["success"],
            fg="#1e1e2e",
            activebackground="#a6e3a1",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=6,
            command=lambda: self._on_start_worker("rewrite_and_post")
        )
        self.btn_rewrite_and_post.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_retry = tk.Button(
            action_bar,
            text="🔄 Thử Lại Bài Lỗi",
            font=("Segoe UI", 9),
            bg=THEME["input"],
            fg=THEME["fg_text"],
            activebackground=THEME["border"],
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._on_retry_failed
        )
        self.btn_retry.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop = tk.Button(
            action_bar,
            text="⏹ Dừng",
            font=("Segoe UI", 9, "bold"),
            bg=THEME["danger"],
            fg="#1e1e2e",
            activebackground="#f38ba8",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
            state=tk.DISABLED,
            command=self._on_stop_worker
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 6))

        btn_clear = tk.Button(
            action_bar,
            text="🗑 Xóa Danh Sách",
            font=("Segoe UI", 9),
            bg=THEME["card"],
            fg=THEME["fg_sub"],
            activebackground=THEME["input"],
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=6,
            command=self._on_clear_queue
        )
        btn_clear.pack(side=tk.RIGHT)

        # 5. Real-time Terminal Log Area
        log_card = tk.Frame(left_frame, bg=THEME["card"], padx=12, pady=10, highlightbackground=THEME["border"], highlightthickness=1)
        log_card.grid(row=4, column=0, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        tk.Label(log_card, text="📟 Nhật Ký Hoạt Động (Terminal Log):", font=("Segoe UI", 9, "bold"), bg=THEME["card"], fg=THEME["fg_sub"]).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.log_text = tk.Text(log_card, height=6, font=("Consolas", 9), bg=THEME["log"], fg=THEME["fg_text"], insertbackground=THEME["fg_text"], relief="flat", padx=8, pady=6)
        log_scroll = ttk.Scrollbar(log_card, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.grid(row=1, column=0, sticky="nsew")
        log_scroll.grid(row=1, column=1, sticky="ns")

        self.logger = UILogger(self.log_text, self.root)

        # ----------------- RIGHT AREA: Settings Sidebar -----------------
        right_frame = tk.Frame(self, bg=THEME["sidebar"], padx=15, pady=15, highlightbackground=THEME["border"], highlightthickness=1)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)

        # Canvas & Scrollbar for settings if needed
        canvas = tk.Canvas(right_frame, bg=THEME["sidebar"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=THEME["sidebar"])

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        scrollable_frame.grid_columnconfigure(0, weight=1)

        # Section 1: Cài đặt AI (Multi-Provider: Gemini & 9Router)
        sec_ai = tk.LabelFrame(scrollable_frame, text=" 🤖 Cấu Hình AI (Gemini / 9Router) ", font=("Segoe UI", 10, "bold"), bg=THEME["sidebar"], fg=THEME["accent"], padx=10, pady=8)
        sec_ai.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        sec_ai.grid_columnconfigure(1, weight=1)

        tk.Label(sec_ai, text="Nhà cung cấp:", font=("Segoe UI", 9, "bold"), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=0, column=0, sticky="w", pady=3)
        self.cb_provider = ttk.Combobox(sec_ai, textvariable=self.v_ai_provider, values=["Google Gemini", "OpenAI / 9Router"], font=("Segoe UI", 9), state="readonly")
        self.cb_provider.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=3)
        self.cb_provider.bind("<<ComboboxSelected>>", lambda e: self._on_provider_changed())

        # Subframe cho Google Gemini
        self.frame_gemini = tk.Frame(sec_ai, bg=THEME["sidebar"])
        self.frame_gemini.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.frame_gemini.grid_columnconfigure(1, weight=1)

        tk.Label(self.frame_gemini, text="Gemini Key:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=0, column=0, sticky="w", pady=3)
        self.ent_gemini_key = tk.Entry(self.frame_gemini, textvariable=self.v_gemini_key, show="*", font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat")
        self.ent_gemini_key.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=3)

        tk.Label(self.frame_gemini, text="Gemini Model:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=1, column=0, sticky="w", pady=3)
        model_sub = tk.Frame(self.frame_gemini, bg=THEME["sidebar"])
        model_sub.grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=3)
        model_sub.grid_columnconfigure(0, weight=1)

        self.cb_gemini_model = ttk.Combobox(
            model_sub,
            textvariable=self.v_gemini_model,
            values=["gemini-3.7-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
            font=("Segoe UI", 9)
        )
        self.cb_gemini_model.grid(row=0, column=0, sticky="ew")

        self.btn_refresh_models = tk.Button(
            model_sub,
            text="🔄 Lấy Model",
            font=("Segoe UI", 8, "bold"),
            bg=THEME["card"],
            fg=THEME["accent"],
            activebackground=THEME["border"],
            relief="flat",
            cursor="hand2",
            padx=4,
            pady=1,
            command=self._on_refresh_models
        )
        self.btn_refresh_models.grid(row=0, column=1, padx=(4, 0))

        # Subframe cho OpenAI / 9Router
        self.frame_openai = tk.Frame(sec_ai, bg=THEME["sidebar"])
        self.frame_openai.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.frame_openai.grid_columnconfigure(1, weight=1)

        tk.Label(self.frame_openai, text="Base URL:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=0, column=0, sticky="w", pady=3)
        tk.Entry(self.frame_openai, textvariable=self.v_openai_base_url, font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat").grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=3)

        tk.Label(self.frame_openai, text="9Router Key:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=1, column=0, sticky="w", pady=3)
        self.ent_openai_key = tk.Entry(self.frame_openai, textvariable=self.v_openai_key, show="*", font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat")
        self.ent_openai_key.grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=3)

        tk.Label(self.frame_openai, text="Model:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=2, column=0, sticky="w", pady=3)
        cb_openai_model = ttk.Combobox(self.frame_openai, textvariable=self.v_openai_model, values=["gpt-4o-mini", "gpt-4o", "deepseek-chat", "deepseek-v3", "claude-3-5-sonnet", "gemini-1.5-flash", "gemini-2.0-flash", "qwen-2.5-72b"], font=("Segoe UI", 9))
        cb_openai_model.grid(row=2, column=1, sticky="ew", padx=(5, 0), pady=3)

        # Ngôn ngữ dịch bài chung
        lang_frame = tk.Frame(sec_ai, bg=THEME["sidebar"])
        lang_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        lang_frame.grid_columnconfigure(1, weight=1)

        tk.Label(lang_frame, text="Ngôn Ngữ Đích:", font=("Segoe UI", 9, "bold"), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=0, column=0, sticky="w", pady=3)
        cb_lang = ttk.Combobox(lang_frame, textvariable=self.v_ai_lang, values=["English", "Tiếng Việt", "Japanese", "Spanish", "French", "German"], font=("Segoe UI", 9), state="readonly")
        cb_lang.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=3)

        # Nút Test Kết Nối AI
        self.btn_test_ai = tk.Button(
            sec_ai,
            text="🧪 Kiểm Tra Kết Nối AI (Test Model)",
            font=("Segoe UI", 9, "bold"),
            bg=THEME["card"],
            fg=THEME["accent"],
            activebackground=THEME["border"],
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self._on_test_ai
        )
        self.btn_test_ai.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 2))

        # Section 2: Cài đặt Website CMS
        sec_web = tk.LabelFrame(scrollable_frame, text=" 🌐 Cấu Hình Website CMS ", font=("Segoe UI", 10, "bold"), bg=THEME["sidebar"], fg=THEME["accent"], padx=10, pady=8)
        sec_web.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        sec_web.grid_columnconfigure(1, weight=1)

        tk.Label(sec_web, text="Base URL:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=0, column=0, sticky="w", pady=3)
        tk.Entry(sec_web, textvariable=self.v_base_url, font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat").grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=3)

        tk.Label(sec_web, text="Login URL:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=1, column=0, sticky="w", pady=3)
        tk.Entry(sec_web, textvariable=self.v_login_url, font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat").grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=3)

        tk.Label(sec_web, text="Tài khoản:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=2, column=0, sticky="w", pady=3)
        tk.Entry(sec_web, textvariable=self.v_username, font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat").grid(row=2, column=1, sticky="ew", padx=(5, 0), pady=3)

        tk.Label(sec_web, text="Mật khẩu:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=3, column=0, sticky="w", pady=3)
        tk.Entry(sec_web, textvariable=self.v_password, show="*", font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat").grid(row=3, column=1, sticky="ew", padx=(5, 0), pady=3)

        # Section 3: Tùy chọn Xuất Bản & Embed
        sec_post = tk.LabelFrame(scrollable_frame, text=" ⚙️ Tùy Chọn Xuất Bản & Embed ", font=("Segoe UI", 10, "bold"), bg=THEME["sidebar"], fg=THEME["accent"], padx=10, pady=8)
        sec_post.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        sec_post.grid_columnconfigure(1, weight=1)

        tk.Label(sec_post, text="Vị trí Embed:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=0, column=0, sticky="w", pady=3)
        cb_embed = ttk.Combobox(sec_post, textvariable=self.v_embed_pos, values=["Sau đoạn đầu", "Đầu bài", "Cuối bài", "Giữa bài"], font=("Segoe UI", 9), state="readonly")
        cb_embed.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=3)

        tk.Label(sec_post, text="Mã Embed:", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=1, column=0, sticky="w", pady=3)
        tk.Entry(sec_post, textvariable=self.v_embed_code, font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat").grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=3)

        chk_frame = tk.Frame(sec_post, bg=THEME["sidebar"])
        chk_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        tk.Checkbutton(chk_frame, text="Hiển thị", variable=self.v_art_display, bg=THEME["sidebar"], fg=THEME["fg_text"], selectcolor=THEME["input"], activebackground=THEME["sidebar"]).pack(side=tk.LEFT, padx=(0, 8))
        tk.Checkbutton(chk_frame, text="Trang chủ", variable=self.v_art_home, bg=THEME["sidebar"], fg=THEME["fg_text"], selectcolor=THEME["input"], activebackground=THEME["sidebar"]).pack(side=tk.LEFT, padx=(0, 8))
        tk.Checkbutton(chk_frame, text="Ghim top", variable=self.v_art_top, bg=THEME["sidebar"], fg=THEME["fg_text"], selectcolor=THEME["input"], activebackground=THEME["sidebar"]).pack(side=tk.LEFT)

        tk.Checkbutton(sec_post, text="⚡ Bỏ qua chống trùng (Force Post)", variable=self.v_force_post, bg=THEME["sidebar"], fg=THEME["warning"], selectcolor=THEME["input"], activebackground=THEME["sidebar"]).grid(row=3, column=0, columnspan=2, sticky="w", pady=2)

        # Section 4: Hiệu năng
        sec_perf = tk.LabelFrame(scrollable_frame, text=" ⚡ Hiệu Năng & Luồng ", font=("Segoe UI", 10, "bold"), bg=THEME["sidebar"], fg=THEME["accent"], padx=10, pady=8)
        sec_perf.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        sec_perf.grid_columnconfigure(1, weight=1)

        tk.Label(sec_perf, text="Số Luồng (Threads):", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(sec_perf, textvariable=self.v_threads, values=["1", "2", "3", "5", "8"], width=6, font=("Segoe UI", 9), state="readonly").grid(row=0, column=1, sticky="w", padx=(5, 0), pady=3)

        tk.Label(sec_perf, text="Nghỉ giữa bài (Delay s):", font=("Segoe UI", 9), bg=THEME["sidebar"], fg=THEME["fg_text"]).grid(row=1, column=0, sticky="w", pady=3)
        tk.Entry(sec_perf, textvariable=self.v_delay, width=8, font=("Segoe UI", 9), bg=THEME["input"], fg=THEME["fg_text"], relief="flat").grid(row=1, column=1, sticky="w", padx=(5, 0), pady=3)

        # Save Config Button
        btn_save = tk.Button(
            scrollable_frame,
            text="💾 Lưu Cấu Hình",
            font=("Segoe UI", 10, "bold"),
            bg=THEME["accent"],
            fg="#1e1e2e",
            activebackground=THEME["accent_hover"],
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
            command=self._on_save_config
        )
        btn_save.grid(row=4, column=0, sticky="ew", pady=(0, 15))

    def _on_provider_changed(self):
        prov = self.v_ai_provider.get()
        if "OpenAI" in prov or "9Router" in prov:
            self.frame_gemini.grid_remove()
            self.frame_openai.grid()
        else:
            self.frame_openai.grid_remove()
            self.frame_gemini.grid()
        self._update_status_badges()

    def _load_values_to_ui(self):
        ai = self.cfg_mgr.get("ai", {})
        prov = ai.get("provider", "gemini")
        if "openai" in prov or "9router" in prov:
            self.v_ai_provider.set("OpenAI / 9Router")
        else:
            self.v_ai_provider.set("Google Gemini")

        gemini_legacy = self.cfg_mgr.get("gemini", {})
        self.v_gemini_key.set(ai.get("gemini_api_key") or gemini_legacy.get("api_key", ""))
        loaded_model = ai.get("gemini_model") or gemini_legacy.get("model", "gemini-3.7-flash")
        if "3.5" in loaded_model or loaded_model in ("gemini-1.5-flash", ""):
            loaded_model = "gemini-3.7-flash"
        self.v_gemini_model.set(loaded_model)
        self.v_openai_base_url.set(ai.get("openai_base_url", "https://api.9router.com/v1"))
        self.v_openai_key.set(ai.get("openai_api_key", ""))
        self.v_openai_model.set(ai.get("openai_model", "gpt-4o-mini"))
        self.v_ai_lang.set(ai.get("language") or gemini_legacy.get("language", "English"))
        self.v_custom_prompt.set(ai.get("custom_prompt") or gemini_legacy.get("custom_prompt", ""))

        w = self.cfg_mgr.get("website", {})
        self.v_base_url.set(w.get("base_url", "https://jesusvibe.danhngon.pro"))
        self.v_login_url.set(w.get("login_url", "https://jesusvibe.danhngon.pro/login"))
        self.v_username.set(w.get("username", ""))
        self.v_password.set(w.get("password", ""))
        self.v_csrf_token.set(w.get("token", ""))
        self.v_cookie.set(w.get("cookie", ""))

        a = self.cfg_mgr.get("article", {})
        self.v_embed_pos.set(a.get("embed_pos", "Sau đoạn đầu"))
        self.v_embed_code.set(a.get("embed_code", ""))
        self.v_keep_old_embed.set(a.get("keep_old_embed", True))
        self.v_art_display.set(a.get("art_display", True))
        self.v_art_home.set(a.get("art_home", True))
        self.v_art_top.set(a.get("art_top", True))

        p = self.cfg_mgr.get("performance", {})
        self.v_threads.set(str(p.get("n_threads", 3)))
        self.v_delay.set(str(p.get("delay", 5)))

        self._on_provider_changed()

    def _collect_config_from_ui(self) -> Dict[str, Any]:
        prov_raw = self.v_ai_provider.get()
        provider_code = "openai_9router" if ("openai" in prov_raw.lower() or "9router" in prov_raw.lower()) else "gemini"

        return {
            "ai": {
                "provider": provider_code,
                "gemini_api_key": self.v_gemini_key.get().strip(),
                "gemini_model": self.v_gemini_model.get().strip(),
                "openai_base_url": self.v_openai_base_url.get().strip(),
                "openai_api_key": self.v_openai_key.get().strip(),
                "openai_model": self.v_openai_model.get().strip(),
                "language": self.v_ai_lang.get().strip(),
                "custom_prompt": self.v_custom_prompt.get().strip()
            },
            "gemini": {
                "api_key": self.v_gemini_key.get().strip(),
                "model": self.v_gemini_model.get().strip(),
                "language": self.v_ai_lang.get().strip(),
                "custom_prompt": self.v_custom_prompt.get().strip()
            },
            "website": {
                "base_url": self.v_base_url.get().strip(),
                "login_url": self.v_login_url.get().strip(),
                "username": self.v_username.get().strip(),
                "password": self.v_password.get(),
                "token": self.v_csrf_token.get().strip(),
                "cookie": self.v_cookie.get().strip(),
                "create_url": ""
            },
            "article": {
                "embed_pos": self.v_embed_pos.get().strip(),
                "embed_code": self.v_embed_code.get().strip(),
                "keep_old_embed": self.v_keep_old_embed.get(),
                "art_display": self.v_art_display.get(),
                "art_home": self.v_art_home.get(),
                "art_top": self.v_art_top.get()
            },
            "performance": {
                "n_threads": int(self.v_threads.get() or 3),
                "delay": int(self.v_delay.get() or 5)
            },
            "browser": {
                "chrome_path": ""
            }
        }

    def _on_save_config(self):
        cfg = self._collect_config_from_ui()
        self.cfg_mgr.save(cfg)
        self._update_status_badges()
        self.logger.success("Đã lưu cấu hình thành công!")
        messagebox.showinfo("Cấu Hình", "Đã lưu cài đặt Module Xào Bài Báo!")

    def _update_status_badges(self):
        prov = self.v_ai_provider.get()
        if "OpenAI" in prov or "9Router" in prov:
            if self.v_openai_key.get().strip():
                self.lbl_badge_gemini.configure(text="9Router: Đã Có Key", fg=THEME["success"])
            else:
                self.lbl_badge_gemini.configure(text="9Router: Chưa Có Key", fg=THEME["warning"])
        else:
            if self.v_gemini_key.get().strip():
                self.lbl_badge_gemini.configure(text="Gemini: Đã Có Key", fg=THEME["success"])
            else:
                self.lbl_badge_gemini.configure(text="Gemini: Chưa Có Key", fg=THEME["warning"])

        # Check Auth Session
        if self.v_cookie.get().strip() or self.v_csrf_token.get().strip():
            self.lbl_badge_auth.configure(text="Auth: Đã Có Session", fg=THEME["success"])
        else:
            self.lbl_badge_auth.configure(text="Auth: Chưa Đăng Nhập", fg=THEME["warning"])

    def _on_choose_file(self):
        file_path = filedialog.askopenfilename(
            title="Chọn File Bài Viết",
            filetypes=[("Text & Word Files", "*.txt;*.docx"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not file_path:
            return
        try:
            if file_path.endswith(".docx"):
                try:
                    import docx
                    doc = docx.Document(file_path)
                    text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                except Exception:
                    self.logger.error("Chưa cài thư viện python-docx để đọc file .docx, vui lòng chọn file .txt")
                    return
            else:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()

            self.txt_input.delete("1.0", tk.END)
            self.txt_input.insert("1.0", text)
            self.logger.info(f"Đã nạp nội dung từ file: {os.path.basename(file_path)}")
        except Exception as e:
            self.logger.error(f"Lỗi đọc file: {e}")

    def _on_add_to_queue(self):
        raw_text = self.txt_input.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("Cảnh Báo", "Vui lòng nhập hoặc nạp nội dung bài viết trước!")
            return

        articles = [a.strip() for a in raw_text.split("---") if a.strip()]
        if not articles:
            articles = [raw_text]

        existing_count = len(self.tree.get_children())
        for i, art in enumerate(articles):
            item_id = existing_count + i + 1
            preview_title = art.split("\n")[0][:40] + ("..." if len(art.split("\n")[0]) > 40 else "")
            self.tree.insert("", "end", iid=str(item_id), values=(item_id, "Pending", preview_title, "-", "-"))

        self.txt_input.delete("1.0", tk.END)
        self.logger.info(f"Đã thêm {len(articles)} bài viết vào hàng đợi!")
        self._update_queue_stats()

    def _update_queue_stats(self):
        children = self.tree.get_children()
        total = len(children)
        success = sum(1 for c in children if self.tree.item(c)["values"][1] == "Success")
        failed = sum(1 for c in children if self.tree.item(c)["values"][1] == "Failed")
        self.lbl_stats.configure(text=f"Tổng: {total} | Thành công: {success} | Lỗi: {failed}")

    def _on_clear_queue(self):
        if self.worker and self.worker.is_running:
            messagebox.showwarning("Cảnh Báo", "Tiến trình đang chạy, vui lòng dừng trước khi xóa danh sách!")
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.logger.info("Đã làm sạch hàng đợi bài viết.")
        self._update_queue_stats()

    def _on_auth_cdp(self):
        """Khởi chạy luồng lấy Cookie/Token qua CDP"""
        self.btn_auth.configure(state=tk.DISABLED)
        self.logger.info("Khởi chạy tiến trình lấy Cookie/CSRF Token qua Chrome DevTools...")

        def _auth_thread():
            auth_mgr = AuthManager(log_cb=self._safe_log)
            cfg = self._collect_config_from_ui()
            web = cfg.get("website", {})
            ok, s_data, msg = auth_mgr.fetch_session_via_cdp(
                login_url=web.get("login_url", ""),
                user=web.get("username", ""),
                password=web.get("password", ""),
                base_url=web.get("base_url", "")
            )

            def _on_auth_done():
                self.btn_auth.configure(state=tk.NORMAL)
                if ok and s_data:
                    self.v_csrf_token.set(s_data.get("token", ""))
                    self.v_cookie.set(s_data.get("cookie", ""))
                    self.cfg_mgr.save(self._collect_config_from_ui())
                    self._update_status_badges()
                    self.logger.success("✅ Đã cập nhật và lưu Token/Cookie phiên làm việc mới!")
                    messagebox.showinfo("Thành Công", "Đã lấy và lưu Session/Cookie thành công!")
                else:
                    self.logger.error(f"Thất bại khi lấy Token/Cookie: {msg}")
                    messagebox.showerror("Thất Bại", f"Không thể lấy Session: {msg}")

            self.root.after(0, _on_auth_done)

    def _on_refresh_models(self):
        """Dynamic Model Discovery: Lấy danh sách model từ Google API"""
        key = self.v_gemini_key.get().strip()
        if not key:
            messagebox.showwarning("Cảnh Báo", "Vui lòng nhập Gemini Key trước khi lấy danh sách model!")
            return

        self.btn_refresh_models.configure(state=tk.DISABLED, text="⏳...")
        self.logger.info("Đang kết nối Google API để lấy danh sách Model mới nhất...")

        def _fetch_thread():
            try:
                ok, models, msg = GeminiEngine.fetch_available_models(key)
            except Exception as e:
                ok, models, msg = False, [], f"Lỗi không xác định: {e}"

            def _done():
                self.btn_refresh_models.configure(state=tk.NORMAL, text="🔄 Lấy Model")
                if ok and models:
                    self.cb_gemini_model["values"] = models
                    if self.v_gemini_model.get() not in models:
                        self.v_gemini_model.set(models[0])
                    self.logger.success(f"✓ Đã nạp thành công {len(models)} model từ Google API!")
                    messagebox.showinfo(
                        "Thành Công",
                        f"✓ Đã lấy được {len(models)} model khả dụng từ Google API:\n\n" + "\n".join(models[:8]) + ("\n..." if len(models) > 8 else "")
                    )
                else:
                    self.logger.error(f"❌ Không thể lấy danh sách model: {msg}")
                    messagebox.showerror("Thất Bại", f"Lỗi lấy model từ Google API:\n{msg}")

            self.root.after(0, _done)

        threading.Thread(target=_fetch_thread, daemon=True).start()

    def _on_test_ai(self):
        """Kiểm tra nhanh API Key và Model trước khi chạy thực tế"""
        cfg = self._collect_config_from_ui()
        ai_cfg = cfg.get("ai", {})
        prov = ai_cfg.get("provider", "gemini")

        if prov in ("openai", "openai_9router", "9router"):
            key = ai_cfg.get("openai_api_key", "").strip()
            model = ai_cfg.get("openai_model", "gpt-4o-mini").strip()
            base_url = ai_cfg.get("openai_base_url", "https://api.9router.com/v1").strip()
            label = "9Router/OpenAI"
        else:
            key = ai_cfg.get("gemini_api_key", "").strip()
            model = ai_cfg.get("gemini_model", "gemini-3.7-flash").strip()
            base_url = ""
            label = "Google Gemini"

        if not key:
            messagebox.showwarning("Cảnh Báo", f"Vui lòng nhập API Key cho {label} trước khi test!")
            return

        self.btn_test_ai.configure(state=tk.DISABLED, text="⏳ Đang kiểm tra...")
        self.logger.info(f"Bắt đầu kiểm tra kết nối {label} (Model: {model})...")

        def _test_thread():
            try:
                engine = GeminiEngine(
                    provider=prov,
                    api_key=key,
                    model=model,
                    base_url=base_url,
                    log_cb=self._safe_log
                )
                ok, msg = engine.validate_connection()
            except Exception as e:
                ok, msg = False, f"Lỗi không xác định: {e}"

            def _on_test_done():
                self.btn_test_ai.configure(state=tk.NORMAL, text="🧪 Kiểm Tra Kết Nối AI (Test Model)")
                if ok:
                    self.logger.success(f"✓ {label} connection successful: {msg}")
                    messagebox.showinfo("Kết Nối Thành Công", f"✓ {label} khả dụng!\n\nModel: {model}\nChi tiết: {msg}")
                else:
                    self.logger.error(f"❌ {label} connection failed: {msg}")
                    messagebox.showerror("Kết Nối Thất Bại", f"❌ Kiểm tra {label} thất bại!\n\nModel: {model}\nNguyên nhân: {msg}")

            self.root.after(0, _on_test_done)

        threading.Thread(target=_test_thread, daemon=True).start()

    def _on_start_worker(self, mode: str):
        children = self.tree.get_children()
        if not children:
            messagebox.showwarning("Cảnh Báo", "Hàng đợi đang trống! Vui lòng thêm bài viết vào hàng đợi trước.")
            return

        cfg = self._collect_config_from_ui()
        ai_cfg = cfg.get("ai", {})
        prov = ai_cfg.get("provider", "gemini")

        if prov in ("openai", "openai_9router", "9router"):
            key = ai_cfg.get("openai_api_key", "").strip()
            model = ai_cfg.get("openai_model", "gpt-4o-mini").strip()
            base_url = ai_cfg.get("openai_base_url", "https://api.9router.com/v1").strip()
            label = "9Router/OpenAI"
            if not key:
                messagebox.showwarning("Cảnh Báo", "Chưa nhập 9Router API Key trong bảng Cài đặt bên phải!")
                return
        else:
            key = ai_cfg.get("gemini_api_key", "").strip()
            model = ai_cfg.get("gemini_model", "gemini-3.7-flash").strip()
            base_url = ""
            label = "Google Gemini"
            if not key:
                messagebox.showwarning("Cảnh Báo", "Chưa nhập Gemini API Key trong bảng Cài đặt bên phải!")
                return

        # Lưu cấu hình hiện tại
        self.cfg_mgr.save(cfg)

        # Validate nhanh trước khi khởi chạy 3 thread
        self.logger.info(f"Đang kiểm tra tính khả dụng của Model [{model}] ({label})...")
        engine = GeminiEngine(provider=prov, api_key=key, model=model, base_url=base_url, log_cb=self._safe_log)
        val_ok, val_msg = engine.validate_connection()
        if not val_ok:
            self.logger.error(f"❌ {label} model unavailable: {model} -> {val_msg}")
            messagebox.showerror(
                "Lỗi Model/API Key",
                f"❌ Không thể bắt đầu hàng đợi do Model '{model}' không khả dụng!\n\nChi tiết: {val_msg}\n\nVui lòng kiểm tra lại Key hoặc đổi Model khác."
            )
            return

        # Lấy danh sách nội dung từ Treeview
        contents = []
        for c in children:
            item_vals = self.tree.item(c)["values"]
            contents.append(item_vals[2])

        self.btn_rewrite_only.configure(state=tk.DISABLED)
        self.btn_rewrite_and_post.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)

        self.worker = ArticleWorker(
            app_dir=self.app_dir,
            config_data=cfg,
            log_cb=self._safe_log,
            on_item_updated=self._on_worker_item_updated,
            on_finished=self._on_worker_finished
        )
        self.worker.set_items(contents, force_post=self.v_force_post.get())
        self.worker.start(mode=mode)

    def _on_worker_item_updated(self, item: ArticleItem):
        def _update_ui():
            item_id_str = str(item.id)
            if self.tree.exists(item_id_str):
                self.tree.item(
                    item_id_str,
                    values=(
                        item.id,
                        item.status,
                        item.title or item.content[:40],
                        item.result_id or "-",
                        item.error or "-"
                    )
                )
            self._update_queue_stats()
        self.root.after(0, _update_ui)

    def _on_worker_finished(self):
        def _finished_ui():
            self.btn_rewrite_only.configure(state=tk.NORMAL)
            self.btn_rewrite_and_post.configure(state=tk.NORMAL)
            self.btn_stop.configure(state=tk.DISABLED)
            self._update_queue_stats()
        self.root.after(0, _finished_ui)

    def _on_stop_worker(self):
        if self.worker:
            self.worker.stop()
            self.btn_stop.configure(state=tk.DISABLED)

    def _on_retry_failed(self):
        if self.worker and not self.worker.is_running:
            self.btn_rewrite_only.configure(state=tk.DISABLED)
            self.btn_rewrite_and_post.configure(state=tk.DISABLED)
            self.btn_stop.configure(state=tk.NORMAL)
            self.worker.retry_failed(mode="rewrite_and_post")
        else:
            messagebox.showinfo("Thông Báo", "Không có bài nào bị lỗi hoặc tiến trình đang chạy!")

    def _safe_log(self, msg: str, level: str = "INFO"):
        lvl = level.upper()
        if lvl == "SUCCESS" or lvl == "OK":
            self.logger.success(msg)
        elif lvl == "WARNING" or lvl == "WARN":
            self.logger.warning(msg)
        elif lvl == "ERROR" or lvl == "ERR":
            self.logger.error(msg)
        else:
            self.logger.info(msg)
