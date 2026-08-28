# -*- coding: utf-8 -*-
import os
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core.logger import UILogger
from modules.extract_title.extractor import process_folder

class ExtractTitleView(ttk.Frame):
    def __init__(self, parent, root):
        super().__init__(parent)
        self.root = root
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg='#1e1e2e', pady=6)
        header.pack(fill=tk.X)
        tk.Label(header, text='📝 TRÍCH XUẤT TIÊU ĐỀ ĐÃ ĐĂNG -> TẠO FILE TITLE.TXT', font=('Segoe UI', 13, 'bold'), bg='#1e1e2e', fg='#f9e2af').pack(side=tk.LEFT, padx=10)
        tk.Label(header, text='Tự động đọc link-da-dung.txt/link-da-dang.txt và tạo title.txt trong từng folder con', font=('Segoe UI', 9), bg='#1e1e2e', fg='#a6adc8').pack(side=tk.LEFT, padx=5)

        content = tk.Frame(self, bg='#1e1e2e', padx=10, pady=5)
        content.pack(fill=tk.BOTH, expand=True)

        # 1. Chọn thư mục cha
        grp_src = tk.LabelFrame(content, text=' 1. Thư mục Kho Chứa Các Folder Con Video ', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4', padx=8, pady=6)
        grp_src.pack(fill=tk.X, pady=(0, 6))

        r_path = tk.Frame(grp_src, bg='#24273a')
        r_path.pack(fill=tk.X, pady=2)
        self.entry_root = tk.Entry(r_path, font=('Segoe UI', 9), bg='#313244', fg='#cdd6f4', insertbackground='#cdd6f4', relief='flat')
        self.entry_root.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        tk.Button(r_path, text='Chọn Thư Mục Kho...', font=('Segoe UI', 9), bg='#45475a', fg='#cdd6f4', relief='flat', padx=10, command=self._browse_root).pack(side=tk.RIGHT)

        r_opt = tk.Frame(grp_src, bg='#24273a')
        r_opt.pack(fill=tk.X, pady=(4, 0))
        self.chk_overwrite_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r_opt, text='Ghi đè nếu đã tồn tại file title.txt', variable=self.chk_overwrite_var, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#f9e2af').pack(side=tk.LEFT)

        # 2. Bảng xem trước kết quả
        grp_tbl = tk.LabelFrame(content, text=' 2. Danh sách Thư mục & Tiêu đề ', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4', padx=8, pady=6)
        grp_tbl.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        tree_frame = tk.Frame(grp_tbl, bg='#181825')
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ('stt', 'folder', 'status', 'title')
        self.tree = ttk.Treeview(tree_frame, columns=cols, show='headings', selectmode='browse')
        self.tree.heading('stt', text='STT')
        self.tree.heading('folder', text='Tên Thư Mục Con')
        self.tree.heading('status', text='Trạng Thái')
        self.tree.heading('title', text='Tiêu Đề Trích Xuất')

        self.tree.column('stt', width=45, anchor='center')
        self.tree.column('folder', width=180, anchor='w')
        self.tree.column('status', width=110, anchor='center')
        self.tree.column('title', width=360, anchor='w')

        sb_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Progress bar
        self.progress = ttk.Progressbar(content, orient='horizontal', mode='determinate')
        self.progress.pack(fill=tk.X, pady=(2, 4))

        # Log
        log_frame = tk.Frame(content, bg='#11111b', bd=1, relief='solid')
        log_frame.pack(fill=tk.X, pady=(0, 6))
        self.log_text = tk.Text(log_frame, font=('Consolas', 9), bg='#11111b', fg='#cdd6f4', relief='flat', height=4)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text['yscrollcommand'] = sb.set

        self.logger = UILogger(self.log_text, self.root)

        # Buttons
        btn_bar = tk.Frame(content, bg='#1e1e2e')
        btn_bar.pack(fill=tk.X)
        self.lbl_stat = tk.Label(btn_bar, text='Sẵn sàng', font=('Segoe UI', 9), bg='#1e1e2e', fg='#a6adc8')
        self.lbl_stat.pack(side=tk.LEFT)

        self.btn_run = tk.Button(btn_bar, text='🔍 QUÉT & TẠO FILE TITLE.TXT', font=('Segoe UI', 10, 'bold'), bg='#f9e2af', fg='#11111b', relief='flat', padx=20, pady=6, cursor='hand2', command=self._start_extract)
        self.btn_run.pack(side=tk.RIGHT)

    def _browse_root(self):
        d = filedialog.askdirectory(title='Chọn Thư Mục Kho Chứa Các Folder Con Video')
        if d:
            self.entry_root.delete(0, tk.END)
            self.entry_root.insert(0, d)

    def _start_extract(self):
        root_dir_str = self.entry_root.get().strip()
        if not root_dir_str or not os.path.exists(root_dir_str):
            self.logger.error('Vui lòng chọn Thư mục kho hợp lệ!')
            return

        self.logger.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

        root_path = Path(root_dir_str)
        subfolders = [f for f in root_path.iterdir() if f.is_dir()]
        if not subfolders:
            subfolders = [root_path]

        total = len(subfolders)
        self.logger.info('Bắt đầu quét ' + str(total) + ' thư mục con...')
        self.btn_run.config(state=tk.DISABLED)
        self.progress['value'] = 0

        def _worker():
            success_count = 0
            skip_count = 0
            overwrite = self.chk_overwrite_var.get()

            for idx, folder in enumerate(subfolders, 1):
                ok, res_msg = process_folder(folder, overwrite=overwrite)
                
                status_text = '✅ Thành công' if ok else '❌ Lỗi'
                title_text = res_msg if ok else res_msg
                
                self.tree.insert('', tk.END, values=(idx, folder.name, status_text, title_text))
                self.tree.yview_moveto(1.0)

                if ok:
                    success_count += 1
                    self.logger.success('[' + str(idx) + '/' + str(total) + '] [✓] ' + folder.name + ' -> ' + res_msg)
                else:
                    skip_count += 1
                    self.logger.warning('[' + str(idx) + '/' + str(total) + '] [-] ' + folder.name + ': ' + res_msg)

                self.progress['value'] = int(idx / total * 100)

            self.progress['value'] = 100
            self.logger.success('🎉 HOÀN TẤT! Thành công: ' + str(success_count) + '/' + str(total) + ' folder (Bỏ qua: ' + str(skip_count) + ')')
            self.lbl_stat.config(text='Hoàn tất: ' + str(success_count) + '/' + str(total) + ' folder.')
            self.btn_run.config(state=tk.NORMAL)
            messagebox.showinfo('Hoàn thành', 'Đã xử lý xong ' + str(total) + ' folder con!\nThành công: ' + str(success_count))

        threading.Thread(target=_worker, daemon=True).start()
