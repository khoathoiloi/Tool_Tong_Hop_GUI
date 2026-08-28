# -*- coding: utf-8 -*-
import os
import json
import threading
import openpyxl
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from core.logger import UILogger
from modules.shiftlink_shortener.shortener import run_shorten_automation, fetch_domains_from_web

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

class ShiftLinkShortenerView(ttk.Frame):
    def __init__(self, parent, root):
        super().__init__(parent)
        self.root = root
        self.is_running = False
        self.stop_requested = False
        self.app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.user_data_dir = os.path.join(self.app_dir, "user_data")
        self.domain_cfg_file = os.path.join(self.app_dir, "user_domains.json")
        self.domains_list = self._load_saved_domains()
        self._build_ui()

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

    def _save_domains(self):
        try:
            with open(self.domain_cfg_file, "w", encoding="utf-8") as f:
                json.dump(self.domains_list, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _build_ui(self):
        # Header banner
        header = tk.Frame(self, bg="#1e1e2e", pady=6)
        header.pack(fill=tk.X)
        tk.Label(header, text="🔗 SHIFTLINK AUTOMATION - RÚT GỌN LINK TỰ ĐỘNG", font=("Segoe UI", 13, "bold"), bg="#1e1e2e", fg="#89b4fa").pack(side=tk.LEFT, padx=10)
        tk.Label(header, text="Tự động rút gọn link từ file Excel, phân bổ domain & tạo slug thông minh", font=("Segoe UI", 9), bg="#1e1e2e", fg="#a6adc8").pack(side=tk.LEFT, padx=5)

        content = tk.Frame(self, bg="#1e1e2e", padx=10, pady=5)
        content.pack(fill=tk.BOTH, expand=True)

        # 1. File Excel & Cấu hình Sheet
        grp_src = tk.LabelFrame(content, text=" 1. Nguồn File Excel & Cấu hình Sheet ", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#cdd6f4", padx=8, pady=6)
        grp_src.pack(fill=tk.X, pady=(0, 6))

        r_file = tk.Frame(grp_src, bg="#24273a")
        r_file.pack(fill=tk.X, pady=2)
        tk.Label(r_file, text="File Excel:", width=18, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        self.entry_excel = tk.Entry(r_file, font=("Segoe UI", 9), bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
        self.entry_excel.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        tk.Button(r_file, text="Chọn File Excel...", font=("Segoe UI", 9), bg="#45475a", fg="#cdd6f4", relief="flat", padx=10, command=self._browse_excel).pack(side=tk.RIGHT)

        r_sheet = tk.Frame(grp_src, bg="#24273a")
        r_sheet.pack(fill=tk.X, pady=3)
        tk.Label(r_sheet, text="Sheet cần xử lý:", width=18, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        self.cbo_sheet = ttk.Combobox(r_sheet, values=["(Tất cả các sheet)"], state="readonly", width=30)
        self.cbo_sheet.current(0)
        self.cbo_sheet.pack(side=tk.LEFT, padx=(0, 15))

        # 2. Cấu hình Domain & Trình Duyệt
        grp_opt = tk.LabelFrame(content, text=" 2. Cấu hình Tên Miền Rút Gọn & Trình Duyệt ", font=("Segoe UI", 9, "bold"), bg="#24273a", fg="#cdd6f4", padx=8, pady=6)
        grp_opt.pack(fill=tk.X, pady=(0, 6))

        r_opt1 = tk.Frame(grp_opt, bg="#24273a")
        r_opt1.pack(fill=tk.X, pady=2)
        tk.Label(r_opt1, text="Tên miền rút gọn:", width=18, anchor="w", bg="#24273a", fg="#cdd6f4").pack(side=tk.LEFT)
        
        self.cbo_domain = ttk.Combobox(r_opt1, values=self.domains_list, state="readonly", width=28)
        if self.domains_list:
            self.cbo_domain.current(0)
        self.cbo_domain.pack(side=tk.LEFT, padx=(0, 8))

        # Nút nạp domain từ web
        self.btn_fetch_domains = tk.Button(
            r_opt1,
            text="🔄 Đồng Bộ Từ Web",
            font=("Segoe UI", 8, "bold"),
            bg="#585b70",
            fg="#89b4fa",
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._fetch_domains_web
        )
        self.btn_fetch_domains.pack(side=tk.LEFT, padx=(0, 15))

        self.chk_browser_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r_opt1, text="Hiển thị trình duyệt Chrome", variable=self.chk_browser_var, bg="#24273a", fg="#cdd6f4", selectcolor="#313244", activebackground="#24273a", activeforeground="#89b4fa").pack(side=tk.LEFT)

        # Progress bar
        self.progress = ttk.Progressbar(content, orient="horizontal", mode="determinate")
        self.progress.pack(fill=tk.X, pady=(2, 4))

        # Log Terminal
        log_frame = tk.Frame(content, bg="#11111b", bd=1, relief="solid")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.log_text = tk.Text(log_frame, font=("Consolas", 9), bg="#11111b", fg="#cdd6f4", relief="flat", height=6)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text["yscrollcommand"] = sb.set

        self.logger = UILogger(self.log_text, self.root)

        # Action bar
        btn_bar = tk.Frame(content, bg="#1e1e2e")
        btn_bar.pack(fill=tk.X)
        self.lbl_status = tk.Label(btn_bar, text="Sẵn sàng", font=("Segoe UI", 9), bg="#1e1e2e", fg="#a6adc8")
        self.lbl_status.pack(side=tk.LEFT)

        self.btn_stop = tk.Button(btn_bar, text="🛑 DỪNG", font=("Segoe UI", 9, "bold"), bg="#f38ba8", fg="#11111b", relief="flat", padx=15, pady=6, state=tk.DISABLED, command=self._stop_processing)
        self.btn_stop.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_start = tk.Button(btn_bar, text="🚀 BẮT ĐẦU RÚT GỌN LINK", font=("Segoe UI", 10, "bold"), bg="#89b4fa", fg="#11111b", relief="flat", padx=20, pady=6, cursor="hand2", command=self._start_shorten)
        self.btn_start.pack(side=tk.RIGHT)

    def _browse_excel(self):
        f = filedialog.askopenfilename(title="Chọn File Excel Cần Rút Gọn Link", filetypes=[("Excel Files", "*.xlsx *.xls"), ("All Files", "*.*")])
        if f:
            self.entry_excel.delete(0, tk.END)
            self.entry_excel.insert(0, f)
            self._load_sheets(f)

    def _load_sheets(self, excel_path):
        try:
            wb = openpyxl.load_workbook(excel_path, read_only=True)
            sheet_names = wb.sheetnames
            vals = ["(Tất cả các sheet)"] + sheet_names
            self.cbo_sheet["values"] = vals
            self.cbo_sheet.current(0)
            self.logger.info(f"Đã nạp {len(sheet_names)} Sheet từ file: {os.path.basename(excel_path)}")
        except Exception as e:
            self.logger.error(f"Lỗi đọc sheet Excel: {e}")

    def _fetch_domains_web(self):
        self.btn_fetch_domains.config(state=tk.DISABLED)
        self.logger.info("⏳ Đang đồng bộ danh sách tên miền từ tài khoản web...")
        
        def _worker():
            try:
                def _log_cb(msg, lvl="INFO"):
                    self.logger.log(msg, lvl)
                
                def _stop_check():
                    return False

                fetched = fetch_domains_from_web(self.user_data_dir, _log_cb, _stop_check)
                if fetched:
                    self.domains_list = fetched
                    self.cbo_domain["values"] = self.domains_list
                    self.cbo_domain.current(0)
                    self._save_domains()
                    self.logger.success(f"🎉 Đã cập nhật đúng {len(self.domains_list)} tên miền của web!")
                    messagebox.showinfo("Thành công", f"Đã đồng bộ đúng {len(fetched)} tên miền từ web!\n\n" + "\n".join(f"• {d}" for d in fetched))
                else:
                    self.logger.warning("Không lấy được tên miền từ web.")
            except Exception as e:
                self.logger.error(f"Lỗi đồng bộ từ web: {e}")
            finally:
                self.btn_fetch_domains.config(state=tk.NORMAL)

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_processing(self):
        if self.is_running:
            self.stop_requested = True
            self.logger.warning("Đang dừng tiến trình rút gọn...")
            self.btn_stop.config(state=tk.DISABLED)

    def _start_shorten(self):
        excel_path = self.entry_excel.get().strip()
        if not excel_path or not os.path.exists(excel_path):
            self.logger.error("Vui lòng chọn File Excel hợp lệ!")
            return

        selected_domain = self.cbo_domain.get().strip() or "nextpart2.online"
        show_browser = self.chk_browser_var.get()
        chosen_sheet_opt = self.cbo_sheet.get()
        target_sheets = None if chosen_sheet_opt == "(Tất cả các sheet)" else [chosen_sheet_opt]

        self.logger.clear()
        self.logger.info("--- BẮT ĐẦU TIẾN TRÌNH RÚT GỌN LINK SHIFTLINK ---")
        self.logger.info(f"Tên miền đã chọn: {selected_domain}")

        self.is_running = True
        self.stop_requested = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress["value"] = 0

        def _worker():
            try:
                def _log_cb(msg, lvl="INFO"):
                    self.logger.log(msg, lvl)

                def _prog_cb(cur, total):
                    pct = int(cur / total * 100) if total > 0 else 0
                    self.progress["value"] = pct
                    self.lbl_status.config(text=f"Tiến độ: {cur}/{total} link ({pct}%)")

                def _stop_check():
                    return self.stop_requested

                ok, out_file = run_shorten_automation(
                    excel_path=excel_path,
                    selected_domain=selected_domain,
                    show_browser=show_browser,
                    target_sheet_names=target_sheets,
                    user_data_dir=self.user_data_dir,
                    log_cb=_log_cb,
                    progress_cb=_prog_cb,
                    stop_check_cb=_stop_check
                )

                if ok and out_file:
                    self.progress["value"] = 100
                    self.logger.success("🎉 RÚT GỌN LINK HOÀN TẤT!")
                    self.logger.highlight(f"📁 File kết quả: {out_file}")
                    messagebox.showinfo("Hoàn tất", f"Đã rút gọn link thành công!\n\nFile kết quả:\n{out_file}")
            except Exception as e:
                self.logger.error(f"Lỗi: {e}")
                messagebox.showerror("Lỗi", f"Lỗi trong quá trình rút gọn: {e}")
            finally:
                self.is_running = False
                self.btn_start.config(state=tk.NORMAL)
                self.btn_stop.config(state=tk.DISABLED)

        threading.Thread(target=_worker, daemon=True).start()