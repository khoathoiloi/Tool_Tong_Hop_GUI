# -*- coding: utf-8 -*-
import os
import sys
import time
import queue
import threading
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import concurrent.futures

from core.logger import UILogger
from core.cuda_env import get_gpu_info, setup_cuda_dlls
from core.ffmpeg_finder import find_ffmpeg
from modules.ai_whisper_srt.engine import extract_audio, segment_words_to_subtitles, write_srt_file
from modules.ai_whisper_srt.model_manager import (
    SUPPORTED_MODELS, 
    get_models_base_dir, 
    is_model_downloaded, 
    get_all_models_status, 
    download_model_to_local
)

class AiWhisperSrtView:
    def __new__(cls, *args, **kwargs):
        return AIWhisperSRTView(*args, **kwargs)

class AIWhisperSRTView(tk.Frame):
    def __init__(self, parent, root, app_dir=None):
        super().__init__(parent, bg='#1e1e2e')
        self.root = root
        if app_dir is None:
            try:
                from core.updater import get_app_root_dir
                app_dir = get_app_root_dir()
            except Exception:
                app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.app_dir = app_dir
        self.ffmpeg_bin = find_ffmpeg()
        self.active_model = None
        self.active_model_name = None
        self.active_device = None
        self.active_compute_type = None
        self.is_running = False
        self.stop_requested = False
        self.is_downloading_models = False

        setup_cuda_dlls()
        self._init_ui()

    def _init_ui(self):
        content = tk.Frame(self, bg='#1e1e2e', padx=15, pady=10)
        content.pack(fill=tk.BOTH, expand=True)

        # Tiêu đề & Thông tin GPU RTX 3060
        header_frame = tk.Frame(content, bg='#1e1e2e')
        header_frame.pack(fill=tk.X, pady=(0, 8))

        lbl_title = tk.Label(header_frame, text='🎬 TẠO PHỤ ĐỀ AI TỰ ĐỘNG (FASTER-WHISPER GPU)', font=('Segoe UI', 13, 'bold'), bg='#1e1e2e', fg='#89b4fa')
        lbl_title.pack(side=tk.LEFT)

        gpu_info = get_gpu_info()
        gpu_badge_text = f"🚀 GPU: {gpu_info.get('detail', 'NVIDIA CUDA Ready')}"
        gpu_color = '#a6e3a1' if gpu_info.get('has_cuda') else '#f9e2af'
        self.lbl_gpu_badge = tk.Label(header_frame, text=gpu_badge_text, font=('Segoe UI', 9, 'bold'), bg='#313244', fg=gpu_color, padx=8, pady=2)
        self.lbl_gpu_badge.pack(side=tk.RIGHT)

        # 1. Nguồn Video
        grp_src = tk.LabelFrame(content, text=' 1. Nguồn Video (Hỗ trợ 1 File hoặc Thư Mục chứa nhiều Video) ', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4', padx=8, pady=4)
        grp_src.pack(fill=tk.X, pady=(0, 6))

        r_src_mode = tk.Frame(grp_src, bg='#24273a')
        r_src_mode.pack(fill=tk.X, pady=2)
        self.src_mode_var = tk.StringVar(value='folder')
        tk.Radiobutton(r_src_mode, text='Quét Cả Thư Mục', variable=self.src_mode_var, value='folder', bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#89b4fa', command=self._toggle_src_mode).pack(side=tk.LEFT, padx=(0, 15))
        tk.Radiobutton(r_src_mode, text='Chọn 1 File Video', variable=self.src_mode_var, value='file', bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#89b4fa', command=self._toggle_src_mode).pack(side=tk.LEFT)

        r_path = tk.Frame(grp_src, bg='#24273a')
        r_path.pack(fill=tk.X, pady=2)
        self.entry_src_path = tk.Entry(r_path, font=('Segoe UI', 9), bg='#313244', fg='#cdd6f4', insertbackground='#cdd6f4', relief='flat')
        self.entry_src_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        self.btn_browse_src = tk.Button(r_path, text='Chọn Thư Mục...', font=('Segoe UI', 9), bg='#45475a', fg='#cdd6f4', relief='flat', padx=10, command=self._browse_src)
        self.btn_browse_src.pack(side=tk.RIGHT)

        # 2. Cấu hình AI Model & Tăng Tốc Đa Luồng GPU
        grp_ai = tk.LabelFrame(content, text=' 2. Cấu Hình Tối Ưu Cho RTX 3060 (Chuyên Biệt Tiếng Anh - Đa Luồng GPU) ', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4', padx=8, pady=5)
        grp_ai.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Model, Threads, Hardware Device
        r_ai1 = tk.Frame(grp_ai, bg='#24273a')
        r_ai1.pack(fill=tk.X, pady=2)
        
        tk.Label(r_ai1, text='Model AI:', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4').pack(side=tk.LEFT, padx=(0, 4))
        self.cbo_model = ttk.Combobox(r_ai1, values=[
            'large-v3-turbo (Khuyên dùng - Siêu tốc & Chuẩn nhất)',
            'large-v3 (Mô hình lớn đầy đủ)',
            'medium'
        ], state='readonly', width=38)
        self.cbo_model.current(0)
        self.cbo_model.pack(side=tk.LEFT, padx=(0, 15))
        self.cbo_model.bind('<<ComboboxSelected>>', lambda e: self._update_model_status_label())

        tk.Label(r_ai1, text='Số Luồng Xử Lý:', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4').pack(side=tk.LEFT, padx=(0, 4))
        self.cbo_threads = ttk.Combobox(r_ai1, values=['2 Luồng Song Song (Khuyên dùng RTX 3060)', '4 Luồng Song Song (Tốc độ tối đa)', '1 Luồng Tuần Tự'], state='readonly', width=32)
        self.cbo_threads.current(0)
        self.cbo_threads.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r_ai1, text='Thiết Bị:', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4').pack(side=tk.LEFT, padx=(0, 4))
        self.cbo_device = ttk.Combobox(r_ai1, values=['cuda (GPU NVIDIA - Ép Chuẩn)', 'cpu'], state='readonly', width=22)
        self.cbo_device.current(0)
        self.cbo_device.pack(side=tk.LEFT)

        # Row 2: Ngôn ngữ (Cố định Tiếng Anh) & Tùy chọn xử lý âm thanh
        r_ai2 = tk.Frame(grp_ai, bg='#24273a')
        r_ai2.pack(fill=tk.X, pady=3)

        tk.Label(r_ai2, text='Ngôn Ngữ:', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#a6adc8').pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(r_ai2, text='🇺🇸 Tiếng Anh (English - en) [Cố định chuẩn xác 100%]', font=('Segoe UI', 9, 'bold'), bg='#313244', fg='#a6e3a1', padx=6, pady=1).pack(side=tk.LEFT, padx=(0, 15))

        self.chk_norm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r_ai2, text='Kích âm lượng giọng nhỏ (DynAudNorm)', variable=self.chk_norm_var, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#a6e3a1').pack(side=tk.LEFT, padx=(0, 10))

        self.chk_vad_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r_ai2, text='Lọc khoảng lặng VAD', variable=self.chk_vad_var, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#a6e3a1').pack(side=tk.LEFT, padx=(0, 10))

        self.chk_skip_existing_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r_ai2, text='Bỏ qua video đã có .srt', variable=self.chk_skip_existing_var, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#a6e3a1').pack(side=tk.LEFT)

        # 3. Quản Lý & Tải Trọn Gói AI Model 1-Click (Offline Model Hub)
        grp_models = tk.LabelFrame(content, text=' 3. Trung Tâm Tải Trọn Gói AI Model 1-Click (Lưu Offline Dùng Vĩnh Viễn) ', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#fab387', padx=8, pady=4)
        grp_models.pack(fill=tk.X, pady=(0, 6))

        r_m_bar = tk.Frame(grp_models, bg='#24273a')
        r_m_bar.pack(fill=tk.X, pady=2)

        self.lbl_model_cur_status = tk.Label(r_m_bar, text='Đang kiểm tra trạng thái model...', font=('Segoe UI', 9), bg='#24273a', fg='#cdd6f4')
        self.lbl_model_cur_status.pack(side=tk.LEFT)

        tk.Button(r_m_bar, text='📂 Mở Thư Mục models/', font=('Segoe UI', 8, 'bold'), bg='#45475a', fg='#cdd6f4', relief='flat', padx=8, pady=2, command=self._open_models_dir).pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_download_current = tk.Button(r_m_bar, text='⬇️ Tải Model Đang Chọn', font=('Segoe UI', 8, 'bold'), bg='#89b4fa', fg='#11111b', relief='flat', padx=10, pady=2, command=self._download_selected_model_action)
        self.btn_download_current.pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_download_all = tk.Button(r_m_bar, text='⚡ TẢI TẤT CẢ MODEL 1-CLICK', font=('Segoe UI', 9, 'bold'), bg='#fab387', fg='#11111b', relief='flat', padx=12, pady=2, cursor='hand2', command=self._download_all_models_action)
        self.btn_download_all.pack(side=tk.RIGHT)

        # Progress bar
        self.progress = ttk.Progressbar(content, orient='horizontal', mode='determinate')
        self.progress.pack(fill=tk.X, pady=(2, 4))

        # Log terminal
        log_frame = tk.Frame(content, bg='#11111b', bd=1, relief='solid')
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.log_text = tk.Text(log_frame, font=('Consolas', 9), bg='#11111b', fg='#cdd6f4', relief='flat', height=6)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text['yscrollcommand'] = sb.set

        self.logger = UILogger(self.log_text, self.root)

        # Action bar
        btn_bar = tk.Frame(content, bg='#1e1e2e')
        btn_bar.pack(fill=tk.X)
        self.lbl_status = tk.Label(btn_bar, text='Sẵn sàng', font=('Segoe UI', 9), bg='#1e1e2e', fg='#a6adc8')
        self.lbl_status.pack(side=tk.LEFT)

        self.btn_stop = tk.Button(btn_bar, text='🛑 DỪNG LẠI', font=('Segoe UI', 9, 'bold'), bg='#f38ba8', fg='#11111b', relief='flat', padx=15, pady=6, state=tk.DISABLED, command=self._stop_processing)
        self.btn_stop.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_start = tk.Button(btn_bar, text='⚡ BẮT ĐẦU TẠO PHỤ ĐỀ ĐA LUỒNG', font=('Segoe UI', 10, 'bold'), bg='#a6e3a1', fg='#11111b', relief='flat', padx=20, pady=6, cursor='hand2', command=self._start_processing)
        self.btn_start.pack(side=tk.RIGHT)

        self._update_model_status_label()

    def _get_selected_model_name(self) -> str:
        return self.cbo_model.get().split()[0].strip()

    def _update_model_status_label(self):
        m_name = self._get_selected_model_name()
        is_dl = is_model_downloaded(m_name)
        if is_dl:
            self.lbl_model_cur_status.config(
                text=f"Model [{m_name}]: ✅ ĐÃ TẢI SẴN (Sẵn sàng chạy 100% Offline)",
                fg='#a6e3a1'
            )
            self.btn_download_current.config(text='✅ Đã Có Trong Máy', state=tk.DISABLED, bg='#45475a', fg='#a6adc8')
        else:
            meta = SUPPORTED_MODELS.get(m_name, {})
            sz_str = f"{meta.get('size_mb', '~1600')} MB"
            self.lbl_model_cur_status.config(
                text=f"Model [{m_name}]: ⬇️ CHƯA TẢI ({sz_str}) - Bấm tải để chạy Offline",
                fg='#f9e2af'
            )
            self.btn_download_current.config(text=f'⬇️ Tải {m_name}', state=tk.NORMAL, bg='#89b4fa', fg='#11111b')

    def _open_models_dir(self):
        p = get_models_base_dir()
        if os.path.exists(p):
            os.startfile(p)

    def _download_selected_model_action(self):
        if self.is_downloading_models:
            messagebox.showwarning("Thông báo", "Tiến trình tải model khác đang chạy!")
            return
        m_name = self._get_selected_model_name()
        self._start_download_thread([m_name])

    def _download_all_models_action(self):
        if self.is_downloading_models:
            messagebox.showwarning("Thông báo", "Tiến trình tải model đang chạy!")
            return
        all_models = list(SUPPORTED_MODELS.keys())
        msg = f"Bạn có muốn tải tất cả {len(all_models)} model ({', '.join(all_models)}) về thư mục models/ để dùng vĩnh viễn không?"
        if messagebox.askyesno("Tải Tất Cả Model", msg):
            self._start_download_thread(all_models)

    def _start_download_thread(self, models_to_download):
        self.is_downloading_models = True
        self.btn_download_all.config(state=tk.DISABLED)
        self.btn_download_current.config(state=tk.DISABLED)
        self.progress['value'] = 0

        def _safe_ui_log(msg, lvl='INFO'):
            try:
                self.logger.log(msg, lvl)
            except Exception:
                pass

        def _worker():
            success_count = 0
            skipped_count = 0
            failed_count = 0
            try:
                total = len(models_to_download)
                _safe_ui_log(f"--- BẮT ĐẦU TẢI {total} AI MODEL VỀ THƯ MỤC models/ ---", "HIGHLIGHT")
                for idx, m_name in enumerate(models_to_download, 1):
                    try:
                        if is_model_downloaded(m_name):
                            _safe_ui_log(f"[{idx}/{total}] [✓] Model [{m_name}] đã có sẵn trong máy, bỏ qua.", "INFO")
                            skipped_count += 1
                            self.progress['value'] = int(idx / total * 100)
                            continue

                        _safe_ui_log(f"[{idx}/{total}] ⏳ Đang tải Model [{m_name}]...", "INFO")
                        ok = download_model_to_local(m_name, log_cb=_safe_ui_log)
                        if ok:
                            success_count += 1
                            _safe_ui_log(f"[{idx}/{total}] 🎉 Tải thành công Model [{m_name}]!", "SUCCESS")
                        else:
                            failed_count += 1
                            _safe_ui_log(f"[{idx}/{total}] ❌ Tải thất bại Model [{m_name}].", "ERROR")
                    except Exception as model_err:
                        failed_count += 1
                        _safe_ui_log(f"[{idx}/{total}] ❌ Lỗi xử lý Model [{m_name}]: {model_err}", "ERROR")

                    self.progress['value'] = int(idx / total * 100)

                summary_msg = f"Tiến trình kết thúc! Thành công: {success_count}/{total}, Bỏ qua: {skipped_count}/{total}, Thất bại: {failed_count}/{total}."
                if failed_count == 0:
                    _safe_ui_log(f"✅ {summary_msg}", "SUCCESS")
                    messagebox.showinfo("Thành Công", f"Tất cả Model đã sẵn sàng trong thư mục models/!\n({summary_msg})")
                else:
                    _safe_ui_log(f"⚠️ {summary_msg}", "WARNING")
                    messagebox.showwarning("Cảnh Báo", f"Có {failed_count} model tải không thành công.\n({summary_msg})")
            except Exception as e:
                _safe_ui_log(f"Lỗi tiến trình tải: {e}", "ERROR")
            finally:
                self.is_downloading_models = False
                self.btn_download_all.config(state=tk.NORMAL)
                self._update_model_status_label()

        threading.Thread(target=_worker, daemon=True).start()

    def _toggle_src_mode(self):
        if self.src_mode_var.get() == 'folder':
            self.btn_browse_src.config(text='Chọn Thư Mục...')
        else:
            self.btn_browse_src.config(text='Chọn File Video...')

    def _browse_src(self):
        if self.src_mode_var.get() == 'folder':
            d = filedialog.askdirectory(title='Chọn Thư Mục Chứa Video')
            if d:
                self.entry_src_path.delete(0, tk.END)
                self.entry_src_path.insert(0, d)
        else:
            f = filedialog.askopenfilename(title='Chọn File Video', filetypes=[('Video Files', '*.mp4 *.mkv *.mov *.avi *.webm *.ts *.flv'), ('All Files', '*.*')])
            if f:
                self.entry_src_path.delete(0, tk.END)
                self.entry_src_path.insert(0, f)

    def _stop_processing(self):
        if self.is_running:
            self.stop_requested = True
            self.logger.warning('Đang yêu cầu dừng tiến trình...')
            self.btn_stop.config(state=tk.DISABLED)

    def _get_model(self, model_name, device, compute_type, num_threads=2):
        from faster_whisper import WhisperModel
        models_dir = str(get_models_base_dir())
        
        if (self.active_model is None or 
            self.active_model_name != model_name or 
            self.active_device != device or 
            self.active_compute_type != compute_type):
            
            self.logger.info(f'Đang nạp AI Model [{model_name}] trên thiết bị [{device}] ({compute_type})...')
            try:
                self.active_model = WhisperModel(
                    model_name, 
                    device=device, 
                    compute_type=compute_type,
                    download_root=models_dir,
                    cpu_threads=4,
                    num_workers=max(2, num_threads)
                )
                self.active_model_name = model_name
                self.active_device = device
                self.active_compute_type = compute_type
                self.logger.success('✅ Nạp Model thành công!')
            except Exception as e:
                if device == 'cuda':
                    self.logger.warning(f'⚠️ Lỗi nạp CUDA GPU: {e}. Đang tự động chuyển sang CPU...')
                    self.active_model = WhisperModel(
                        model_name, 
                        device='cpu', 
                        compute_type='float32',
                        download_root=models_dir,
                        cpu_threads=4,
                        num_workers=max(2, num_threads)
                    )
                    self.active_model_name = model_name
                    self.active_device = 'cpu'
                    self.active_compute_type = 'float32'
                    self.logger.success('✅ Nạp Model trên CPU thành công!')
                else:
                    raise e
        return self.active_model

    def _start_processing(self):
        src_path_str = self.entry_src_path.get().strip()
        if not src_path_str or not os.path.exists(src_path_str):
            self.logger.error('Vui lòng chọn File video hoặc Thư mục video hợp lệ!')
            return

        self.logger.clear()
        self.logger.info('--- BẮT ĐẦU TIẾN TRÌNH TẠO PHỤ ĐỀ AI ĐA LUỒNG ---')

        # Thu thập danh sách video
        target_videos = []
        video_exts = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.ts', '.flv', '.m4v'}
        if os.path.isfile(src_path_str):
            target_videos.append(Path(src_path_str))
        else:
            p_dir = Path(src_path_str)
            for root, _, files in os.walk(p_dir):
                for f in files:
                    if Path(f).suffix.lower() in video_exts:
                        target_videos.append(Path(root) / f)

        if not target_videos:
            self.logger.error('Không tìm thấy bất kỳ file video nào trong nguồn đã chọn!')
            return

        self.logger.info('Tổng số video tìm thấy: ' + str(len(target_videos)))

        raw_model_str = self._get_selected_model_name()
        
        # Thiết bị & Định dạng tính (Mặc định GPU CUDA float16 cho RTX 3060)
        device = 'cuda' if 'cuda' in self.cbo_device.get().lower() else 'cpu'
        compute_type = 'float16' if device == 'cuda' else 'float32'

        # Số luồng
        threads_str = self.cbo_threads.get()
        num_threads = 4 if '4' in threads_str else (1 if '1' in threads_str else 2)

        boost_vocals = self.chk_norm_var.get()
        use_vad = self.chk_vad_var.get()
        skip_existing = self.chk_skip_existing_var.get()

        self.is_running = True
        self.stop_requested = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress['value'] = 0

        def _worker():
            try:
                model = self._get_model(raw_model_str, device, compute_type, num_threads=num_threads)
                total = len(target_videos)
                processed_count = 0
                skipped_count = 0
                lock = threading.Lock()

                # Bộ lọc danh sách video cần xử lý
                tasks = []
                for vpath in target_videos:
                    srt_path = vpath.with_suffix('.srt')
                    if skip_existing and srt_path.exists() and srt_path.stat().st_size > 0:
                        skipped_count += 1
                    else:
                        tasks.append(vpath)

                if skipped_count > 0:
                    self.logger.info(f"[-] Đã bỏ qua {skipped_count} video đã có file .srt.")

                if not tasks:
                    self.logger.success("🎉 Tất cả video đã có sẵn file .srt!")
                    self.progress['value'] = 100
                    return

                self.logger.info(f"🚀 Bắt đầu xử lý song song {len(tasks)} video với {num_threads} luồng trên {device.upper()}...")

                def _process_one_video(vpath: Path, item_idx: int):
                    if self.stop_requested:
                        return False
                    srt_path = vpath.with_suffix('.srt')
                    t0 = time.time()

                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
                        tmp_audio_path = Path(tmp_audio.name)

                    try:
                        ok = extract_audio(vpath, tmp_audio_path, self.ffmpeg_bin, boost_vocals=boost_vocals)
                        if not ok:
                            self.logger.error(f'[{item_idx}/{total}] Lỗi trích xuất audio từ: {vpath.name}')
                            return False

                        vad_params = dict(min_silence_duration_ms=400) if use_vad else None
                        try:
                            segments, info = model.transcribe(
                                str(tmp_audio_path),
                                language='en',
                                vad_filter=use_vad,
                                vad_parameters=vad_params,
                                word_timestamps=True,
                                beam_size=5,
                                temperature=0.0,
                                condition_on_previous_text=False
                            )
                        except Exception as vad_err:
                            if use_vad and ("onnx" in str(vad_err).lower() or "silero" in str(vad_err).lower() or "no_suchfile" in str(vad_err).lower()):
                                segments, info = model.transcribe(
                                    str(tmp_audio_path),
                                    language='en',
                                    vad_filter=False,
                                    word_timestamps=True,
                                    beam_size=5,
                                    temperature=0.0,
                                    condition_on_previous_text=False
                                )
                            else:
                                raise vad_err

                        all_words = []
                        for seg in segments:
                            if hasattr(seg, 'words') and seg.words:
                                all_words.extend(seg.words)

                        if all_words:
                            subtitles = segment_words_to_subtitles(all_words)
                            write_srt_file(subtitles, srt_path)
                            elapsed = time.time() - t0
                            self.logger.success(f'[{item_idx}/{total}] -> [✓] Xong: {srt_path.name} ({len(subtitles)} câu, {elapsed:.1f}s)')
                            return True
                        else:
                            self.logger.warning(f'[{item_idx}/{total}] -> [!] Không phát hiện lời thoại: {vpath.name}')
                            return False
                    except Exception as e:
                        self.logger.error(f'[{item_idx}/{total}] Lỗi xử lý {vpath.name}: {e}')
                        return False
                    finally:
                        if tmp_audio_path.exists():
                            try: tmp_audio_path.unlink()
                            except: pass

                # Chạy song song bằng ThreadPoolExecutor
                with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                    future_to_video = {
                        executor.submit(_process_one_video, vp, i): vp 
                        for i, vp in enumerate(tasks, 1)
                    }

                    for future in concurrent.futures.as_completed(future_to_video):
                        if self.stop_requested:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        res = future.result()
                        with lock:
                            if res:
                                processed_count += 1
                            done_count = processed_count + skipped_count
                            self.progress['value'] = int(done_count / total * 100)

                self.progress['value'] = 100
                self.logger.success(f'🎉 HOÀN THÀNH XUẤT SRT CHO {processed_count} VIDEO! (Bỏ qua: {skipped_count})')
                messagebox.showinfo('Hoàn thành', f'Đã xử lý xong {processed_count} video!')
            except Exception as e:
                self.logger.error('Lỗi trong quá trình tạo phụ đề: ' + str(e))
                messagebox.showerror('Lỗi', 'Lỗi: ' + str(e))
            finally:
                self.is_running = False
                self.btn_start.config(state=tk.NORMAL)
                self.btn_stop.config(state=tk.DISABLED)
                self._update_model_status_label()

        threading.Thread(target=_worker, daemon=True).start()
        
AiWhisperSrtView = AIWhisperSRTView