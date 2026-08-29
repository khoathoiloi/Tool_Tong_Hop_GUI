# -*- coding: utf-8 -*-
import os
import sys
import threading
import webbrowser
import time
import tkinter as tk
from tkinter import ttk, messagebox
from core.cuda_env import get_gpu_info
from core.ffmpeg_finder import find_ffmpeg
from core.updater import APP_VERSION, GITHUB_REPO, check_for_updates, download_and_apply_update, get_app_root_dir

class SettingsView(ttk.Frame):
    def __init__(self, parent, root):
        super().__init__(parent)
        self.root = root
        self.app_dir = get_app_root_dir()
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg="#1e1e2e", pady=6)
        header.pack(fill=tk.X)
        tk.Label(header, text="⚙️ CÀI ĐẶT HỆ THỐNG & CẬP NHẬT PHẦN MỀM", font=("Segoe UI", 13, "bold"), bg="#1e1e2e", fg="#cba6f7").pack(side=tk.LEFT, padx=10)
        tk.Label(header, text="Thông tin phần cứng, GPU, FFmpeg và tự động cập nhật từ GitHub", font=("Segoe UI", 9), bg="#1e1e2e", fg="#a6adc8").pack(side=tk.LEFT, padx=5)

        content = tk.Frame(self, bg="#1e1e2e", padx=15, pady=8)
        content.pack(fill=tk.BOTH, expand=True)

        # 1. Update Box
        grp_update = tk.LabelFrame(content, text=" 1. Cập Nhật Phần Mềm Tự Động (GitHub Auto-Updater) ", font=("Segoe UI", 10, "bold"), bg="#24273a", fg="#89b4fa", padx=12, pady=8)
        grp_update.pack(fill=tk.X, pady=(0, 8))

        r_up1 = tk.Frame(grp_update, bg="#24273a")
        r_up1.pack(fill=tk.X, pady=2)
        tk.Label(r_up1, text="Phiên bản hiện tại:", width=22, anchor="w", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#a6adc8").pack(side=tk.LEFT)
        tk.Label(r_up1, text=f"v{APP_VERSION} (Bản Mới Nhất)", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#a6e3a1").pack(side=tk.LEFT)

        self.btn_check_update = tk.Button(
            r_up1,
            text="🔄 Kiểm Tra Cập Nhật GitHub",
            font=("Segoe UI", 9, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            relief="flat",
            padx=12,
            pady=3,
            cursor="hand2",
            command=self._check_update_action
        )
        self.btn_check_update.pack(side=tk.RIGHT)

        r_up2 = tk.Frame(grp_update, bg="#24273a")
        r_up2.pack(fill=tk.X, pady=2)
        tk.Label(r_up2, text="Kho lưu trữ GitHub:", width=22, anchor="w", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#a6adc8").pack(side=tk.LEFT)
        lbl_repo = tk.Label(r_up2, text=f"https://github.com/{GITHUB_REPO}", font=("Segoe UI", 9, "underline"), bg="#24273a", fg="#89b4fa", cursor="hand2")
        lbl_repo.pack(side=tk.LEFT)
        lbl_repo.bind("<Button-1>", lambda e: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))

        self.lbl_update_status = tk.Label(grp_update, text="Nhấn 'Kiểm Tra Cập Nhật GitHub' để kiểm tra phiên bản mới nhất.", font=("Segoe UI", 9, "italic"), bg="#24273a", fg="#cdd6f4")
        self.lbl_update_status.pack(anchor="w", pady=(4, 0))

        # 2. Hardware Box
        grp_hw = tk.LabelFrame(content, text=" 2. Thông Tin Phần Cứng & AI Accelerator ", font=("Segoe UI", 10, "bold"), bg="#24273a", fg="#cdd6f4", padx=12, pady=8)
        grp_hw.pack(fill=tk.X, pady=(0, 8))

        gpu = get_gpu_info()
        self._add_info_row(grp_hw, "Card Đồ Họa (GPU):", gpu["detail"], "#a6e3a1" if gpu["has_cuda"] else "#f9e2af")
        self._add_info_row(grp_hw, "Trạng Thái CUDA:", "Khả dụng (NVIDIA Tensor Cores float16 - Sẵn sàng)" if gpu["has_cuda"] else "Không khả dụng (Chạy CPU Mode)", "#a6e3a1" if gpu["has_cuda"] else "#f9e2af")
        
        cpu_cores = os.cpu_count() or 4
        self._add_info_row(grp_hw, "Bộ Xử Lý (CPU):", f"{cpu_cores} Cores / Logical Processors", "#cdd6f4")
        self._add_info_row(grp_hw, "FFmpeg Binary:", find_ffmpeg(), "#89b4fa")
        self._add_info_row(grp_hw, "Môi Trường Python:", f"{sys.version.split()[0]} ({sys.executable})", "#a6adc8")

        # 3. Quick Open Folders
        grp_folders = tk.LabelFrame(content, text=" 3. Phím Tắt Mở Nhanh Thư Mục ", font=("Segoe UI", 10, "bold"), bg="#24273a", fg="#cdd6f4", padx=12, pady=8)
        grp_folders.pack(fill=tk.BOTH, expand=True)

        r_btns = tk.Frame(grp_folders, bg="#24273a")
        r_btns.pack(fill=tk.X, pady=5)

        tk.Button(r_btns, text="📂 Mở Thư Mục Ổ E:\\", font=("Segoe UI", 9, "bold"), bg="#45475a", fg="#cdd6f4", relief="flat", padx=12, pady=6, command=lambda: self._open_dir("E:\\")).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(r_btns, text="📂 Mở Thư Mục Tool E:\\Tool_Tong_Hop_GUI", font=("Segoe UI", 9, "bold"), bg="#45475a", fg="#cdd6f4", relief="flat", padx=12, pady=6, command=lambda: self._open_dir(r"E:\Tool_Tong_Hop_GUI")).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(r_btns, text="📂 Mở Thư Mục User Data Chrome", font=("Segoe UI", 9, "bold"), bg="#45475a", fg="#cdd6f4", relief="flat", padx=12, pady=6, command=lambda: self._open_dir(os.path.join(self.app_dir, "user_data"))).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(r_btns, text="📂 Mở Ổ D:\\", font=("Segoe UI", 9, "bold"), bg="#45475a", fg="#cdd6f4", relief="flat", padx=12, pady=6, command=lambda: self._open_dir("D:\\")).pack(side=tk.LEFT)

    def _add_info_row(self, parent, label, value, val_color="#cdd6f4"):
        row = tk.Frame(parent, bg="#24273a")
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text=label, width=22, anchor="w", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#a6adc8").pack(side=tk.LEFT)
        tk.Label(row, text=value, font=("Segoe UI", 9), bg="#24273a", fg=val_color).pack(side=tk.LEFT)

    def _open_dir(self, path):
        if os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showwarning("Thông báo", f"Thư mục không tồn tại: {path}")

    def _check_update_action(self):
        self.btn_check_update.config(state=tk.DISABLED)
        self.lbl_update_status.config(text="⏳ Đang kết nối tới GitHub Releases để kiểm tra phiên bản mới...", fg="#89b4fa")

        def _worker():
            try:
                info = check_for_updates(APP_VERSION, GITHUB_REPO)
                if info.get("has_update"):
                    latest_v = info.get("latest_version")
                    tag = info.get("tag_name")
                    dl_url = info.get("download_url")
                    body = info.get("body", "")

                    self.lbl_update_status.config(
                        text=f"🎉 Đã có bản cập nhật mới: {tag}! Đang sẵn sàng tải về.",
                        fg="#a6e3a1"
                    )

                    msg = f"ĐÃ TÌM THẤY BẢN CẬP NHẬT MỚI: {tag}\n\nNội dung cập nhật:\n{body}\n\nBạn có muốn tự động tải và cập nhật ngay bây giờ không?"
                    if messagebox.askyesno("Có Bản Cập Nhật Mới!", msg):
                        self._perform_update(dl_url, info.get("html_url"))
                elif info.get("error"):
                    self.lbl_update_status.config(text=f"⚠️ Thông báo: {info.get('error')}", fg="#f9e2af")
                else:
                    self.lbl_update_status.config(text=f"✅ Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION})!", fg="#a6e3a1")
                    messagebox.showinfo("Cập Nhật", f"Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION})!")
            except Exception as e:
                self.lbl_update_status.config(text=f"❌ Lỗi kiểm tra: {e}", fg="#f38ba8")
            finally:
                self.btn_check_update.config(state=tk.NORMAL)

        threading.Thread(target=_worker, daemon=True).start()

    def _perform_update(self, download_url, release_page):
        if not download_url:
            messagebox.showinfo("Tải Bản Cập Nhật", "Mở trang GitHub Releases để tải file cập nhật thủ công.")
            webbrowser.open(release_page or f"https://github.com/{GITHUB_REPO}/releases")
            return

        self.lbl_update_status.config(text="⏳ Đang tải bản cập nhật từ GitHub...", fg="#89b4fa")
        
        def _dl_worker():
            try:
                def _prog(pct, cur, total):
                    self.lbl_update_status.config(
                        text=f"⏳ Đang tải bản cập nhật: {pct}% ({cur // (1024*1024)}MB / {total // (1024*1024)}MB)...",
                        fg="#89b4fa"
                    )

                def _log(msg, lvl="INFO"):
                    self.lbl_update_status.config(text=msg, fg="#a6e3a1" if lvl=="SUCCESS" else "#89b4fa")

                ok = download_and_apply_update(download_url, progress_cb=_prog, log_cb=_log)
                if ok:
                    messagebox.showinfo(
                        "Đang Áp Dụng Cập Nhật",
                        "🎉 ĐÃ TẢI XONG BẢN CẬP NHẬT MỚI!\n\nỨng dụng sẽ tự động đóng và khởi động lại ngay bây giờ để hoàn tất cập nhật."
                    )
                    # Đóng app ngay để nhường quyền ghi đè file cho script cập nhật
                    self.root.destroy()
                    os._exit(0)
                else:
                    self.lbl_update_status.config(text="❌ Tự động cập nhật thất bại, vui lòng tải từ GitHub.", fg="#f38ba8")
                    webbrowser.open(release_page or f"https://github.com/{GITHUB_REPO}/releases")
            except Exception as e:
                self.lbl_update_status.config(text=f"❌ Lỗi: {e}", fg="#f38ba8")

        threading.Thread(target=_dl_worker, daemon=True).start()