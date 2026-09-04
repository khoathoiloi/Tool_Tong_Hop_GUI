# -*- coding: utf-8 -*-
"""
MasterToolHub Bootstrap Updater (Standalone Auto-Updater)
Độc lập hoàn toàn, hỗ trợ GUI, SHA256 Checksum, Safe Download Retry, Backup & Rollback
"""
import os
import sys
import re
import time
import json
import shutil
import hashlib
import tempfile
import argparse
import datetime
import threading
import subprocess
import urllib.request
import urllib.error
import ssl
import tkinter as tk
from tkinter import ttk, messagebox

# Cấu hình Theme đồng bộ với Master Hub
THEME = {
    "bg": "#1e1e2e",
    "card": "#24273a",
    "border": "#313244",
    "fg": "#cdd6f4",
    "fg_sub": "#a6adc8",
    "accent": "#89b4fa",
    "highlight": "#cba6f7",
    "success": "#a6e3a1",
    "warning": "#f9e2af",
    "error": "#f38ba8"
}

# Các thư mục / file User Data tuyệt đối không được xóa hoặc ghi đè
PROTECTED_USER_DATA = {
    "models",
    "user_data",
    "user_domains.json",
    "backup",
    "logs",
    "projects",
    "output"
}

class UpdaterLogger:
    def __init__(self, log_file_path: str = None, text_widget: tk.Text = None, root: tk.Tk = None):
        self.log_file_path = log_file_path
        self.text_widget = text_widget
        self.root = root
        if self.log_file_path:
            os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)

    def log(self, message: str, level: str = "INFO"):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{now_str}] [{level}] {message}\n"
        
        # Ghi vào file log
        if self.log_file_path:
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(log_line)
            except Exception:
                pass
                
        # Hiển thị lên UI nếu có widget
        if self.text_widget and self.root:
            def _ui_update():
                try:
                    self.text_widget.insert(tk.END, f"[{now_str.split()[1]}] ", "TIME")
                    self.text_widget.insert(tk.END, f"{message}\n", level)
                    self.text_widget.see(tk.END)
                except Exception:
                    pass
            self.root.after(0, _ui_update)

class MasterToolUpdaterApp(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.target_dir = os.path.abspath(args.target_dir or os.getcwd())
        self.package_url = (args.package_url or "").strip()
        self.package_sha256 = (args.package_sha256 or "").strip().lower()
        self.to_version = (args.to_version or "").lstrip("vV").strip() or "Latest"
        self.target_pid = args.pid
        self.relaunch_exe = args.relaunch_exe or "MasterToolHub.exe"

        # Tự động phát hiện from_version nếu chưa có
        from_v = (args.from_version or "").lstrip("vV").strip()
        if not from_v or from_v.lower() == "current":
            self.from_version = self._detect_current_version()
        else:
            self.from_version = from_v
        
        # Setup đường dẫn thư mục tạm và log
        self.temp_base = os.path.join(tempfile.gettempdir(), "MasterToolUpdater")
        self.download_dir = os.path.join(self.temp_base, "downloads")
        self.staging_dir = os.path.join(self.temp_base, "staging")
        self.log_file = os.path.join(self.target_dir, "logs", "updater.log")
        self.state_file = os.path.join(self.target_dir, "update_state.json")
        self.backup_dir = os.path.join(self.target_dir, "backup", f"v{self.from_version}")

        # Setup GUI Window
        self.title("🚀 MasterToolHub Updater - Đang Cập Nhật Hệ Thống")
        self.geometry("620x440")
        self.minsize(560, 380)
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        
        # Icon
        icon_candidate = os.path.join(self.target_dir, "app_icon.ico")
        if os.path.exists(icon_candidate):
            try: self.iconbitmap(icon_candidate)
            except Exception: pass

        self._build_ui()
        self.logger = UpdaterLogger(self.log_file, self.txt_log, self)
        
        # Bắt đầu luồng cập nhật sau khi GUI render
        self.after(500, self._start_update_thread)

    def _detect_current_version(self) -> str:
        """Tự động phát hiện phiên bản hiện tại từ file state, tên folder hoặc version file"""
        # 1. Thử đọc từ update_state.json
        state_file = os.path.join(self.target_dir, "update_state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    st = json.load(f)
                    if st.get("to_version") and st.get("to_version") != "Latest":
                        return st["to_version"]
                    if st.get("from_version") and st.get("from_version") != "Current":
                        return st["from_version"]
            except Exception:
                pass

        # 2. Thử bóc tách từ tên thư mục (ví dụ MasterToolHub_v2.5.1 -> 2.5.1)
        folder_name = os.path.basename(self.target_dir)
        m = re.search(r'v?(\d+\.\d+(?:\.\d+)?)', folder_name, re.IGNORECASE)
        if m:
            return m.group(1)

        # 3. Thử đọc file version.txt nếu có
        ver_file = os.path.join(self.target_dir, "version.txt")
        if os.path.exists(ver_file):
            try:
                with open(ver_file, "r", encoding="utf-8") as f:
                    return f.read().strip().lstrip("vV")
            except Exception:
                pass

        return "2.5.1"

    def _fetch_latest_release_info(self) -> dict:
        """Tự động truy vấn gói cập nhật mới nhất từ GitHub Manifest hoặc Releases API"""
        repo_name = "khoathoiloi/Tool_Tong_Hop_GUI"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        # 1. Thử đọc update.json trên GitHub main branch
        manifest_url = f"https://raw.githubusercontent.com/{repo_name}/main/update.json"
        try:
            req = urllib.request.Request(manifest_url, headers={"User-Agent": "MasterToolHub-BootstrapUpdater"})
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    pkg_url = data.get("package_url") or data.get("download_url")
                    if pkg_url:
                        return {
                            "package_url": pkg_url,
                            "package_sha256": (data.get("package_sha256") or data.get("sha256") or "").strip().lower(),
                            "latest_version": data.get("latest_version", "2.7.5").lstrip("vV").strip(),
                        }
        except Exception as e:
            self.logger.log(f"Không thể đọc update.json ({e}), chuyển sang GitHub Releases API...", "WARNING")

        # 2. Fallback sang GitHub Releases API
        api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
        try:
            req = urllib.request.Request(api_url, headers={
                "User-Agent": "MasterToolHub-BootstrapUpdater",
                "Accept": "application/vnd.github.v3+json"
            })
            with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    tag = data.get("tag_name", "").lstrip("vV").strip()
                    for a in data.get("assets", []):
                        aname = a.get("name", "").lower()
                        if aname.endswith(".zip") or (aname.startswith("mastertoolhub") and aname.endswith(".exe")):
                            return {
                                "package_url": a.get("browser_download_url"),
                                "package_sha256": "",
                                "latest_version": tag
                            }
        except Exception as e:
            self.logger.log(f"Lỗi truy vấn GitHub Releases API: {e}", "ERROR")

        return {}

    def _update_header_version(self):
        try:
            self.lbl_version_header.config(text=f"Đang nâng cấp từ v{self.from_version}  ➔  v{self.to_version}")
        except Exception:
            pass

    def _build_ui(self):
        # Header Box
        header = tk.Frame(self, bg=THEME["card"], pady=12, padx=16)
        header.pack(fill=tk.X)
        
        tk.Label(
            header,
            text="⚡ MASTER HUB AUTO-UPDATER",
            font=("Segoe UI", 13, "bold"),
            bg=THEME["card"],
            fg=THEME["accent"]
        ).pack(anchor="w")
        
        self.lbl_version_header = tk.Label(
            header,
            text=f"Đang nâng cấp từ v{self.from_version}  ➔  v{self.to_version}",
            font=("Segoe UI", 9, "bold"),
            bg=THEME["card"],
            fg=THEME["success"]
        )
        self.lbl_version_header.pack(anchor="w", pady=(2, 0))

        content = tk.Frame(self, bg=THEME["bg"], padx=16, pady=12)
        content.pack(fill=tk.BOTH, expand=True)

        # Status & Progress Area
        self.lbl_status = tk.Label(
            content,
            text="Đang chuẩn bị tiến trình cập nhật...",
            font=("Segoe UI", 9, "bold"),
            bg=THEME["bg"],
            fg=THEME["fg"]
        )
        self.lbl_status.pack(anchor="w", pady=(0, 4))

        self.lbl_detail = tk.Label(
            content,
            text="Vui lòng không tắt máy tính hoặc ngắt kết nối...",
            font=("Segoe UI", 8),
            bg=THEME["bg"],
            fg=THEME["fg_sub"]
        )
        self.lbl_detail.pack(anchor="w", pady=(0, 6))

        # Progress bar
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Update.Horizontal.TProgressbar",
            thickness=16,
            troughcolor=THEME["card"],
            background=THEME["accent"],
            darkcolor=THEME["accent"],
            lightcolor=THEME["accent"],
            bordercolor=THEME["border"]
        )
        
        self.progress = ttk.Progressbar(
            content,
            style="Update.Horizontal.TProgressbar",
            orient="horizontal",
            mode="determinate"
        )
        self.progress.pack(fill=tk.X, pady=(0, 10))

        # Log Terminal Box
        log_frame = tk.Frame(content, bg=THEME["border"], padx=1, pady=1)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.txt_log = tk.Text(
            log_frame,
            font=("Consolas", 8),
            bg=THEME["card"],
            fg=THEME["fg"],
            insertbackground=THEME["fg"],
            relief="flat",
            wrap="word"
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        
        self.txt_log.tag_config("TIME", foreground=THEME["fg_sub"])
        self.txt_log.tag_config("INFO", foreground=THEME["fg"])
        self.txt_log.tag_config("SUCCESS", foreground=THEME["success"], font=("Consolas", 8, "bold"))
        self.txt_log.tag_config("WARNING", foreground=THEME["warning"])
        self.txt_log.tag_config("ERROR", foreground=THEME["error"], font=("Consolas", 8, "bold"))
        self.txt_log.tag_config("HIGHLIGHT", foreground=THEME["highlight"], font=("Consolas", 8, "bold"))

        # Footer Buttons
        footer = tk.Frame(self, bg=THEME["bg"], padx=16, pady=8)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_action = tk.Button(
            footer,
            text="Đang Cập Nhật...",
            font=("Segoe UI", 9, "bold"),
            bg=THEME["border"],
            fg=THEME["fg_sub"],
            relief="flat",
            padx=14,
            pady=4,
            state=tk.DISABLED,
            command=self._on_btn_action
        )
        self.btn_action.pack(side=tk.RIGHT)

    def _set_status(self, text, detail="", progress_val=None):
        self.lbl_status.config(text=text)
        if detail:
            self.lbl_detail.config(text=detail)
        if progress_val is not None:
            self.progress["value"] = progress_val

    def _on_btn_action(self):
        self.destroy()

    def _set_state(self, state_name: str, extra_info: dict = None):
        data = {
            "state": state_name,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "timestamp": datetime.datetime.now().isoformat(),
            "target_dir": self.target_dir
        }
        if extra_info:
            data.update(extra_info)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _start_update_thread(self):
        threading.Thread(target=self._run_update_pipeline, daemon=True).start()

    def _run_update_pipeline(self):
        self.logger.log(f"=== BẮT ĐẦU QUY TRÌNH NÂNG CẤP AUTO-UPDATER ===", "HIGHLIGHT")
        self.logger.log(f"Thư mục cài đặt: {self.target_dir}", "INFO")
        self.logger.log(f"Nâng cấp: v{self.from_version} -> v{self.to_version}", "INFO")

        # BƯỚC 0: Tự động truy vấn gói cập nhật từ GitHub nếu chạy độc lập (package_url trống)
        if not self.package_url:
            self._set_status("🌐 Đang kiểm tra bản cập nhật mới từ GitHub...", "Đang kết nối tới GitHub để lấy thông tin phát hành...", 5)
            self.logger.log("Chưa có URL gói cập nhật, đang tự động kết nối GitHub...", "INFO")
            info = self._fetch_latest_release_info()
            if info and info.get("package_url"):
                self.package_url = info["package_url"]
                self.package_sha256 = info.get("package_sha256", self.package_sha256)
                if info.get("latest_version"):
                    self.to_version = info["latest_version"]
                self.after(0, self._update_header_version)
                self.logger.log(f"Đã lấy link cập nhật thành công: v{self.to_version} ({self.package_url})", "SUCCESS")
            else:
                self.logger.log("Không thể lấy đường dẫn tải gói cập nhật từ GitHub!", "ERROR")
                self._handle_failure("DOWNLOAD_FAILED", "Không thể lấy đường dẫn tải gói cập nhật từ GitHub. Vui lòng kiểm tra kết nối mạng và thử lại sau.")
                return

        # BƯỚC 1: Đợi ứng dụng chính thoát hoàn toàn và giải phóng File Lock
        self._set_status("⏳ Đang đợi ứng dụng cũ đóng...", "Đang kiểm tra và giải phóng khóa file hệ thống...", 8)
        if not self._wait_for_process_exit(self.target_pid, timeout=12):
            self.logger.log("Cảnh báo: Không thể đóng hoàn toàn ứng dụng cũ qua PID, đang tiến hành đóng an toàn...", "WARNING")
            self._kill_process_by_name("MasterToolHub.exe")
            time.sleep(1.5)

        if not self._verify_file_locks():
            self.logger.log("Lỗi: Các tệp tin hệ thống vẫn đang bị khóa bởi tiến trình khác.", "ERROR")
            self._handle_failure("FILE_LOCKED", "Không thể cập nhật vì tệp tin đang bị một ứng dụng khác khóa. Vui lòng thử lại sau.")
            return

        # BƯỚC 2: Tải gói cập nhật với cơ chế Retry & Exponential Backoff
        self._set_status("📥 Đang tải bản cập nhật mới từ GitHub...", "Đang kết nối và tải gói cài đặt an toàn...", 12)
        zip_file = self._download_package_with_retry(self.package_url, max_retries=3)
        if not zip_file:
            self._handle_failure("DOWNLOAD_FAILED", "Không thể tải gói cập nhật từ GitHub. Vui lòng kiểm tra kết nối mạng và thử lại sau.")
            return

        # BƯỚC 3: Xác thực toàn vẹn gói cập nhật qua SHA256 Checksum
        self._set_status("🛡️ Đang xác thực mã bảo mật SHA256...", "Kiểm tra tính toàn vẹn của tệp tải về...", 45)
        if not self._verify_sha256(zip_file, self.package_sha256):
            if os.path.exists(zip_file):
                try: os.remove(zip_file)
                except Exception: pass
            self._handle_failure("CHECKSUM_MISMATCH", "Tệp cập nhật tải về không hợp lệ hoặc bị lỗi đường truyền (SHA256 không khớp). Bản cũ vẫn được giữ nguyên an toàn.")
            return

        # BƯỚC 4: Sao lưu ứng dụng hiện tại trước khi cài đặt
        self._set_status("💾 Đang tạo bản sao lưu an toàn...", f"Lưu trữ bản v{self.from_version} vào backup/...", 55)
        if not self._backup_current_installation():
            self.logger.log("Cảnh báo: Không thể tạo bản sao lưu hoàn chỉnh, nhưng vẫn tiếp tục cài đặt...", "WARNING")

        # BƯỚC 5: Giải nén & Cài đặt gói cập nhật
        self._set_status("📦 Đang giải nén & cài đặt bản mới...", "Đang thay thế tệp tin chương trình (Bảo vệ dữ liệu người dùng)...", 70)
        self._set_state("installing")
        
        extracted_root = self._extract_package(zip_file)
        if not extracted_root:
            self._trigger_rollback("EXTRACT_FAILED", "Lỗi giải nén gói cập nhật. Đang khôi phục lại phiên bản cũ...")
            return

        if not self._install_package_files(extracted_root):
            self._trigger_rollback("INSTALL_FAILED", "Lỗi trong quá trình sao chép tệp mới. Đang tự động Rollback về phiên bản cũ...")
            return

        # BƯỚC 6: Kiểm tra xác minh sau cài đặt (Post-Verification)
        self._set_status("🔍 Đang xác minh tính toàn vẹn sau cài đặt...", "Kiểm tra cấu trúc file ứng dụng mới...", 90)
        if not self._verify_installation():
            self._trigger_rollback("VERIFY_FAILED", "Xác minh phiên bản mới thất bại (Thiếu file thực thi hoặc DLL). Đang Rollback về bản cũ...")
            return

        # BƯỚC 7: Hoàn thành & Tự khởi động lại ứng dụng mới
        self._set_state("completed")
        self._set_status("🎉 CẬP NHẬT HOÀN TẤT THÀNH CÔNG!", f"Đã nâng cấp lên phiên bản v{self.to_version}! Đang khởi động lại...", 100)
        self.logger.log(f"✅ NÂNG CẤP THÀNH CÔNG LÊN PHIÊN BẢN v{self.to_version}!", "SUCCESS")

        # Dọn dẹp file tạm
        self._cleanup_temp()

        # Khởi chạy ứng dụng mới
        self.after(1200, self._relaunch_application)

    def _wait_for_process_exit(self, pid: int, timeout: float = 10.0) -> bool:
        if not pid or pid <= 0:
            return True
        self.logger.log(f"Đang đợi tiến trình PID {pid} đóng...", "INFO")
        start_t = time.time()
        while time.time() - start_t < timeout:
            if not self._is_pid_running(pid):
                self.logger.log(f"Tiến trình PID {pid} đã thoát an toàn.", "INFO")
                return True
            time.sleep(0.5)
        return False

    def _is_pid_running(self, pid: int) -> bool:
        if os.name == "nt":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
            if h:
                code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                ctypes.windll.kernel32.CloseHandle(h)
                return code.value == 259 # STILL_ACTIVE
            return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    def _kill_process_by_name(self, proc_name: str):
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/F", "/IM", proc_name, "/T"], capture_output=True, timeout=5)
            except Exception:
                pass

    def _verify_file_locks(self) -> bool:
        """Kiểm tra xem các file then chốt có bị khóa ghi không"""
        key_files = [
            os.path.join(self.target_dir, self.relaunch_exe),
            os.path.join(self.target_dir, "MasterToolHub.exe")
        ]
        for kf in key_files:
            if os.path.exists(kf):
                try:
                    with open(kf, "a+b") as f:
                        pass
                except IOError as e:
                    self.logger.log(f"Tệp đang bị khóa: {kf} ({e})", "WARNING")
                    return False
        return True

    def _download_package_with_retry(self, url: str, max_retries: int = 3) -> str:
        if not url:
            self.logger.log("Lỗi: Đường dẫn tải gói cập nhật (URL) trống!", "ERROR")
            return None

        os.makedirs(self.download_dir, exist_ok=True)
        dest_zip = os.path.join(self.download_dir, "update_package.zip")
        if os.path.exists(dest_zip):
            try: os.remove(dest_zip)
            except Exception: pass

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        for attempt in range(1, max_retries + 1):
            try:
                self.logger.log(f"Tải gói cập nhật (Lần thử {attempt}/{max_retries}): {url}", "INFO")
                req = urllib.request.Request(url, headers={"User-Agent": "MasterToolHub-BootstrapUpdater"})
                
                with urllib.request.urlopen(req, context=ctx, timeout=90) as resp, open(dest_zip, "wb") as out_f:
                    total_size = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    block_size = 131072
                    start_time = time.time()

                    while True:
                        buf = resp.read(block_size)
                        if not buf:
                            break
                        downloaded += len(buf)
                        out_f.write(buf)

                        if total_size > 0:
                            pct = 10 + int((downloaded / total_size) * 35) # 10% -> 45%
                            elapsed = max(0.1, time.time() - start_time)
                            speed_mb = (downloaded / (1024 * 1024)) / elapsed
                            cur_mb = downloaded / (1024 * 1024)
                            tot_mb = total_size / (1024 * 1024)
                            
                            self._set_status(
                                f"📥 Đang tải bản cập nhật: {int((downloaded/total_size)*100)}%",
                                f"Đã tải: {cur_mb:.1f} MB / {tot_mb:.1f} MB ({speed_mb:.2f} MB/s)",
                                pct
                            )

                if os.path.exists(dest_zip) and os.path.getsize(dest_zip) > 1024:
                    self.logger.log(f"Tải về thành công! Dung lượng: {os.path.getsize(dest_zip)/(1024*1024):.2f} MB", "SUCCESS")
                    return dest_zip

            except Exception as e:
                self.logger.log(f"Lần thử {attempt} thất bại: {e}", "WARNING")
                if attempt < max_retries:
                    backoff = attempt * 2
                    self.logger.log(f"Đang đợi {backoff}s trước khi thử lại...", "INFO")
                    time.sleep(backoff)

        return None

    def _verify_sha256(self, file_path: str, expected_sha256: str) -> bool:
        if not expected_sha256:
            self.logger.log("Bỏ qua kiểm tra SHA256 (Không có mã hash trong manifest release).", "INFO")
            return True

        self.logger.log("Đang tính toán SHA256 của tệp nén...", "INFO")
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(1048576):
                    sha256.update(chunk)
            computed = sha256.hexdigest().lower()
            if computed == expected_sha256:
                self.logger.log(f"✅ Checksum SHA256 chính xác: {computed}", "SUCCESS")
                return True
            else:
                self.logger.log(f"❌ SHA256 không khớp! Thực tế: {computed} - Mong đợi: {expected_sha256}", "ERROR")
                return False
        except Exception as e:
            self.logger.log(f"Lỗi khi đọc mã SHA256: {e}", "ERROR")
            return False

    def _backup_current_installation(self) -> bool:
        """Sao lưu các tệp application cũ (Bỏ qua tuyệt đối User Data)"""
        try:
            if os.path.exists(self.backup_dir):
                shutil.rmtree(self.backup_dir, ignore_errors=True)
            os.makedirs(self.backup_dir, exist_ok=True)

            self.logger.log(f"Đang tạo thư mục sao lưu: {self.backup_dir}", "INFO")
            
            for item in os.listdir(self.target_dir):
                if item in PROTECTED_USER_DATA:
                    continue # Bảo vệ tuyệt đối User Data
                
                src = os.path.join(self.target_dir, item)
                dst = os.path.join(self.backup_dir, item)
                
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

            self.logger.log("Sao lưu phiên bản cũ hoàn tất!", "SUCCESS")
            return True
        except Exception as e:
            self.logger.log(f"Lỗi tạo bản sao lưu: {e}", "WARNING")
            return False

    def _extract_package(self, zip_path: str) -> str:
        """Giải nén và tìm thư mục gốc chứa file chương trình"""
        try:
            if os.path.exists(self.staging_dir):
                shutil.rmtree(self.staging_dir, ignore_errors=True)
            os.makedirs(self.staging_dir, exist_ok=True)

            import zipfile
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(self.staging_dir)

            # Tìm thư mục chứa MasterToolHub.exe hoặc core/modules
            for root, dirs, files in os.walk(self.staging_dir):
                if "MasterToolHub.exe" in files or ("core" in dirs and "modules" in dirs):
                    return root

            return self.staging_dir
        except Exception as e:
            self.logger.log(f"Lỗi giải nén: {e}", "ERROR")
            return None

    def _install_package_files(self, source_dir: str) -> bool:
        """Sao chép tệp mới vào thư mục ứng dụng (bảo vệ User Data)"""
        try:
            self.logger.log(f"Đang sao chép tệp từ: {source_dir} -> {self.target_dir}", "INFO")
            
            for root, dirs, files in os.walk(source_dir):
                rel_dir = os.path.relpath(root, source_dir)
                dest_dir = self.target_dir if rel_dir == "." else os.path.join(self.target_dir, rel_dir)
                
                top_folder = rel_dir.split(os.sep)[0] if rel_dir != "." else ""
                if top_folder in PROTECTED_USER_DATA:
                    continue # Bỏ qua ghi đè thư mục User Data

                os.makedirs(dest_dir, exist_ok=True)

                for f in files:
                    src_file = os.path.join(root, f)
                    dst_file = os.path.join(dest_dir, f)
                    
                    if rel_dir == "." and f in PROTECTED_USER_DATA:
                        continue # Bỏ qua ghi đè file cấu hình người dùng
                        
                    # Thử ghi đè file với retry
                    copied = False
                    for _ in range(3):
                        try:
                            shutil.copy2(src_file, dst_file)
                            copied = True
                            break
                        except PermissionError:
                            time.sleep(0.5)
                    
                    if not copied:
                        self.logger.log(f"Không thể ghi đè tệp: {dst_file}", "ERROR")
                        return False

            self.logger.log("Sao chép toàn bộ tệp phiên bản mới thành công!", "SUCCESS")
            return True
        except Exception as e:
            self.logger.log(f"Lỗi trong quá trình cài đặt: {e}", "ERROR")
            return False

    def _verify_installation(self) -> bool:
        """Xác minh ứng dụng mới có đầy đủ file sau cài đặt"""
        exe_path = os.path.join(self.target_dir, "MasterToolHub.exe")
        core_path = os.path.join(self.target_dir, "core")
        internal_path = os.path.join(self.target_dir, "_internal")

        if os.path.exists(exe_path) and os.path.getsize(exe_path) > 1024:
            return True
        if os.path.exists(core_path) or os.path.exists(internal_path):
            return True

        self.logger.log("Xác minh thất bại: Không tìm thấy MasterToolHub.exe hợp lệ sau cập nhật!", "ERROR")
        return False

    def _trigger_rollback(self, error_code: str, user_msg: str):
        self._set_state("rollback", {"error_code": error_code})
        self._set_status("⚠️ Đang khôi phục lại phiên bản cũ...", "Đang Rollback dữ liệu an toàn...", 85)
        self.logger.log(f"Kích hoạt Rollback do lỗi: {error_code}", "WARNING")

        try:
            if os.path.exists(self.backup_dir):
                for item in os.listdir(self.backup_dir):
                    src = os.path.join(self.backup_dir, item)
                    dst = os.path.join(self.target_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                self.logger.log("Khôi phục phiên bản cũ thành công (Rollback OK)!", "SUCCESS")
        except Exception as e:
            self.logger.log(f"Lỗi trong quá trình Rollback: {e}", "ERROR")

        self._cleanup_temp()
        self._handle_failure(error_code, user_msg)

    def _handle_failure(self, error_code: str, message: str):
        self._set_state("failed", {"error_code": error_code})
        self._set_status("❌ CẬP NHẬT THẤT BẠI", message, 0)
        self.logger.log(f"Kết thúc thất bại: {error_code}", "ERROR")
        
        self.btn_action.config(
            text="Đóng Cửa Sổ",
            state=tk.NORMAL,
            bg=THEME["error"],
            fg="#ffffff"
        )
        messagebox.showerror("Cập Nhật Thất Bại", f"{message}\n\nChi tiết xem tại: logs/updater.log")

    def _cleanup_temp(self):
        try:
            if os.path.exists(self.temp_base):
                shutil.rmtree(self.temp_base, ignore_errors=True)
        except Exception:
            pass

    def _relaunch_application(self):
        exe_target = os.path.join(self.target_dir, self.relaunch_exe)
        if not os.path.exists(exe_target):
            exe_target = os.path.join(self.target_dir, "MasterToolHub.exe")
        if not os.path.exists(exe_target):
            exe_target = os.path.join(self.target_dir, "run_app.bat")

        self.logger.log(f"Đang khởi chạy lại ứng dụng: {exe_target}", "SUCCESS")
        
        try:
            if os.name == "nt":
                subprocess.Popen([exe_target], cwd=self.target_dir, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
            else:
                subprocess.Popen([exe_target], cwd=self.target_dir, start_new_session=True)
        except Exception as e:
            self.logger.log(f"Không thể tự khởi động lại: {e}", "WARNING")

        self.destroy()
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="MasterToolHub Bootstrap Standalone Updater")
    parser.add_argument("--target-dir", type=str, default="", help="Thư mục gốc của ứng dụng cần cập nhật")
    parser.add_argument("--package-url", type=str, default="", help="URL tải file zip bản phát hành mới")
    parser.add_argument("--package-sha256", type=str, default="", help="Mã băm SHA256 của file zip")
    parser.add_argument("--to-version", type=str, default="", help="Phiên bản mục tiêu")
    parser.add_argument("--from-version", type=str, default="", help="Phiên bản hiện tại")
    parser.add_argument("--pid", type=int, default=0, help="PID của tiến trình cũ cần đợi thoát")
    parser.add_argument("--relaunch-exe", type=str, default="MasterToolHub.exe", help="Tên file thực thi cần khởi chạy lại")
    args = parser.parse_args()

    # Mutex để ngăn chặn 2 Updater chạy đồng thời
    if os.name == "nt":
        import ctypes
        mutex_name = "Global\\MasterToolHubUpdaterMutex_v1"
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        last_err = ctypes.windll.kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183
        if last_err == ERROR_ALREADY_EXISTS:
            print("Một tiến trình Updater khác đang chạy!")
            sys.exit(0)

    app = MasterToolUpdaterApp(args)
    app.mainloop()

if __name__ == "__main__":
    main()