# -*- coding: utf-8 -*-
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from core.cuda_env import setup_cuda_dlls, get_gpu_info
from core.theme import THEME
from core.updater import APP_VERSION, GITHUB_REPO, check_for_updates

from modules.excel_fanpage.view import ExcelFanpageView
from modules.ai_whisper_srt.view import AiWhisperSrtView
from modules.extract_title.view import ExtractTitleView
from modules.shiftlink_shortener.view import ShiftLinkShortenerView
from modules.settings.view import SettingsView

class MasterToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        setup_cuda_dlls()
        
        self.title(f"🚀 BỘ CÔNG CỤ TỔNG HỢP FANPAGE & MEDIA (MASTER ALL-IN-ONE v{APP_VERSION})")
        self.geometry("1120x800")
        self.minsize(980, 680)
        self.configure(bg=THEME["bg"])

        # Icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self._setup_styles()
        self._build_layout()
        self._show_view("excel_fanpage")
        self._check_update_background()

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        
        # Styles for ttk widgets
        style.configure("TProgressbar",
            thickness=14,
            troughcolor=THEME["card"],
            background=THEME["accent"],
            darkcolor=THEME["accent"],
            lightcolor=THEME["accent"],
            bordercolor=THEME["border"]
        )
        style.configure("Treeview",
            background=THEME["card"],
            foreground=THEME["fg"],
            fieldbackground=THEME["card"],
            rowheight=26,
            font=("Segoe UI", 9)
        )
        style.map("Treeview", background=[('selected', THEME["highlight"])], foreground=[('selected', '#ffffff')])
        style.configure("Treeview.Heading",
            background=THEME["border"],
            foreground=THEME["fg"],
            font=("Segoe UI", 9, "bold")
        )

    def _build_layout(self):
        # 1. Left Sidebar
        self.sidebar = tk.Frame(self, bg=THEME["sidebar"], width=230)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # Brand / Logo Header
        brand_frame = tk.Frame(self.sidebar, bg=THEME["sidebar"], pady=14)
        brand_frame.pack(fill=tk.X)
        tk.Label(brand_frame, text="⚡ MASTER HUB", font=("Segoe UI", 14, "bold"), bg=THEME["sidebar"], fg=THEME["accent"]).pack()
        tk.Label(brand_frame, text=f"All-In-One Unified Suite v{APP_VERSION}", font=("Segoe UI", 8), bg=THEME["sidebar"], fg=THEME["fg_sub"]).pack(pady=(2, 0))

        tk.Frame(self.sidebar, height=1, bg=THEME["border"]).pack(fill=tk.X, padx=10, pady=(0, 10))

        # Nav Buttons
        self.nav_buttons = {}
        nav_items = [
            ("excel_fanpage", "📊 Tạo Excel Fanpage"),
            ("ai_whisper_srt", "⚡ AI Faster-Whisper SRT"),
            ("extract_title", "📝 Trích Xuất Title.txt"),
            ("shiftlink_shortener", "🔗 Rút Gọn Link ShiftLink"),
            ("settings", "⚙️ Cài Đặt & Cập Nhật"),
        ]

        for view_name, label_text in nav_items:
            btn = tk.Button(
                self.sidebar,
                text=f"  {label_text}",
                font=("Segoe UI", 9, "bold"),
                anchor="w",
                bg=THEME["sidebar"],
                fg=THEME["fg"],
                activebackground=THEME["card"],
                activeforeground=THEME["accent"],
                relief="flat",
                padx=14,
                pady=10,
                cursor="hand2",
                command=lambda v=view_name: self._show_view(v)
            )
            btn.pack(fill=tk.X, padx=6, pady=2)
            self.nav_buttons[view_name] = btn

        # Sidebar Footer Status
        footer_frame = tk.Frame(self.sidebar, bg=THEME["sidebar"])
        footer_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        gpu_info = get_gpu_info()
        gpu_color = THEME["success"] if gpu_info["has_cuda"] else THEME["warning"]
        gpu_short = gpu_info["device_name"] if gpu_info["has_cuda"] else "CPU Mode"
        
        self.lbl_gpu_footer = tk.Label(footer_frame, text=f"🟢 {gpu_short}", font=("Segoe UI", 8, "bold"), bg=THEME["sidebar"], fg=gpu_color, anchor="w")
        self.lbl_gpu_footer.pack(fill=tk.X)
        self.lbl_ver_footer = tk.Label(footer_frame, text=f"Build: v{APP_VERSION} (Ổ E:\\)", font=("Segoe UI", 8), bg=THEME["sidebar"], fg=THEME["fg_sub"], anchor="w")
        self.lbl_ver_footer.pack(fill=tk.X)

        # 2. Main Content View Area
        self.content_container = tk.Frame(self, bg=THEME["bg"])
        self.content_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.views = {
            "excel_fanpage": ExcelFanpageView(self.content_container, self),
            "ai_whisper_srt": AiWhisperSrtView(self.content_container, self),
            "extract_title": ExtractTitleView(self.content_container, self),
            "shiftlink_shortener": ShiftLinkShortenerView(self.content_container, self),
            "settings": SettingsView(self.content_container, self)
        }

    def _show_view(self, name):
        for v_name, view in self.views.items():
            if v_name == name:
                view.pack(fill=tk.BOTH, expand=True)
            else:
                view.pack_forget()

        for v_name, btn in self.nav_buttons.items():
            if v_name == name:
                btn.configure(bg=THEME["border"], fg=THEME["accent"])
            else:
                btn.configure(bg=THEME["sidebar"], fg=THEME["fg"])

    def _check_update_background(self):
        """Kiểm tra cập nhật ngầm không block giao diện khi mở app"""
        def _worker():
            try:
                info = check_for_updates(APP_VERSION, GITHUB_REPO)
                if info.get("has_update"):
                    latest_v = info.get("latest_version")
                    self.lbl_ver_footer.config(
                        text=f"🚀 Có bản mới: v{latest_v}!",
                        fg=THEME["accent"]
                    )
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

if __name__ == "__main__":
    app = MasterToolApp()
    app.mainloop()