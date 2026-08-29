# -*- coding: utf-8 -*-
import os
import time
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core.logger import UILogger
from core.cuda_env import get_gpu_info
from core.ffmpeg_finder import find_ffmpeg
from modules.ai_whisper_srt.engine import extract_audio, segment_words_to_subtitles, write_srt_file

class AiWhisperSrtView(ttk.Frame):
    def __init__(self, parent, root):
        super().__init__(parent)
        self.root = root
        self.ffmpeg_bin = find_ffmpeg()
        self.is_running = False
        self.stop_requested = False
        self.active_model = None
        self.active_model_name = None
        self.active_device = None
        self.active_compute_type = None
        self._build_ui()

    def _build_ui(self):
        # Header banner
        header = tk.Frame(self, bg='#1e1e2e', pady=6)
        header.pack(fill=tk.X)
        tk.Label(header, text='⚡ AI FASTER-WHISPER VIDEO TO SRT GENERATOR', font=('Segoe UI', 13, 'bold'), bg='#1e1e2e', fg='#a6e3a1').pack(side=tk.LEFT, padx=10)
        gpu_info = get_gpu_info()
        gpu_text = '🟢 GPU: ' + gpu_info['detail'] if gpu_info['has_cuda'] else '🟡 ' + gpu_info['detail']
        tk.Label(header, text=gpu_text, font=('Segoe UI', 9, 'bold'), bg='#1e1e2e', fg='#f9e2af' if not gpu_info['has_cuda'] else '#a6e3a1').pack(side=tk.RIGHT, padx=10)

        content = tk.Frame(self, bg='#1e1e2e', padx=10, pady=5)
        content.pack(fill=tk.BOTH, expand=True)

        # 1. Nguồn Video
        grp_src = tk.LabelFrame(content, text=' 1. Nguồn Video ', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4', padx=8, pady=6)
        grp_src.pack(fill=tk.X, pady=(0, 6))

        self.src_mode_var = tk.StringVar(value='folder')
        mode_bar = tk.Frame(grp_src, bg='#24273a')
        mode_bar.pack(fill=tk.X, pady=(0, 4))
        tk.Radiobutton(mode_bar, text='Chọn Thư mục Video (Quét hàng loạt)', variable=self.src_mode_var, value='folder', command=self._toggle_src_mode, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#a6e3a1').pack(side=tk.LEFT, padx=(0, 15))
        tk.Radiobutton(mode_bar, text='Chọn 1 File Video đơn lẻ', variable=self.src_mode_var, value='file', command=self._toggle_src_mode, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#a6e3a1').pack(side=tk.LEFT)

        r_path = tk.Frame(grp_src, bg='#24273a')
        r_path.pack(fill=tk.X, pady=2)
        self.entry_src_path = tk.Entry(r_path, font=('Segoe UI', 9), bg='#313244', fg='#cdd6f4', insertbackground='#cdd6f4', relief='flat')
        self.entry_src_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        self.btn_browse_src = tk.Button(r_path, text='Chọn Thư Mục...', font=('Segoe UI', 9), bg='#45475a', fg='#cdd6f4', relief='flat', padx=10, command=self._browse_src)
        self.btn_browse_src.pack(side=tk.RIGHT)

        # 2. Cấu hình AI Model & Phần Cứng
        grp_ai = tk.LabelFrame(content, text=' 2. Cấu hình AI Model & Tham số Subtitle ', font=('Segoe UI', 9, 'bold'), bg='#24273a', fg='#cdd6f4', padx=8, pady=6)
        grp_ai.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Model, Device, Compute
        r_ai1 = tk.Frame(grp_ai, bg='#24273a')
        r_ai1.pack(fill=tk.X, pady=2)
        
        tk.Label(r_ai1, text='Model Whisper:', bg='#24273a', fg='#cdd6f4').pack(side=tk.LEFT, padx=(0, 5))
        self.cbo_model = ttk.Combobox(r_ai1, values=['large-v3-turbo (Khuyên dùng - Siêu tốc)', 'large-v3 (Độ chính xác cao nhất)', 'medium', 'small', 'base', 'tiny'], state='readonly', width=30)
        self.cbo_model.current(0)
        self.cbo_model.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r_ai1, text='Thiết bị:', bg='#24273a', fg='#cdd6f4').pack(side=tk.LEFT, padx=(0, 5))
        gpu_avail = get_gpu_info()['has_cuda']
        self.cbo_device = ttk.Combobox(r_ai1, values=['cuda', 'cpu'], state='readonly', width=8)
        self.cbo_device.current(0 if gpu_avail else 1)
        self.cbo_device.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r_ai1, text='Định dạng tính:', bg='#24273a', fg='#cdd6f4').pack(side=tk.LEFT, padx=(0, 5))
        self.cbo_compute = ttk.Combobox(r_ai1, values=['float16', 'int8_float16', 'int8', 'float32'], state='readonly', width=12)
        self.cbo_compute.current(0 if gpu_avail else 2)
        self.cbo_compute.pack(side=tk.LEFT)

        # Row 2: Ngôn ngữ & Tùy chọn âm thanh
        r_ai2 = tk.Frame(grp_ai, bg='#24273a')
        r_ai2.pack(fill=tk.X, pady=3)

        tk.Label(r_ai2, text='Ngôn ngữ:', bg='#24273a', fg='#cdd6f4').pack(side=tk.LEFT, padx=(0, 5))
        self.cbo_lang = ttk.Combobox(r_ai2, values=['vi (Tiếng Việt)', 'en (Tiếng Anh)', 'Auto (Tự động phát hiện)', 'zh (Tiếng Trung)', 'ja (Tiếng Nhật)'], state='readonly', width=20)
        self.cbo_lang.current(0)
        self.cbo_lang.pack(side=tk.LEFT, padx=(0, 15))

        self.chk_norm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r_ai2, text='Kích âm lượng giọng nhỏ (DynAudNorm)', variable=self.chk_norm_var, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#a6e3a1').pack(side=tk.LEFT, padx=(0, 10))

        self.chk_vad_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r_ai2, text='Lọc khoảng lặng VAD', variable=self.chk_vad_var, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#a6e3a1').pack(side=tk.LEFT, padx=(0, 10))

        self.chk_skip_existing_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r_ai2, text='Bỏ qua video đã có .srt', variable=self.chk_skip_existing_var, bg='#24273a', fg='#cdd6f4', selectcolor='#313244', activebackground='#24273a', activeforeground='#a6e3a1').pack(side=tk.LEFT)

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

        self.btn_start = tk.Button(btn_bar, text='⚡ BẮT ĐẦU TẠO PHỤ ĐỀ', font=('Segoe UI', 10, 'bold'), bg='#a6e3a1', fg='#11111b', relief='flat', padx=20, pady=6, cursor='hand2', command=self._start_processing)
        self.btn_start.pack(side=tk.RIGHT)

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

    def _get_model(self, model_name, device, compute_type):
        from faster_whisper import WhisperModel
        if (self.active_model is None or 
            self.active_model_name != model_name or 
            self.active_device != device or 
            self.active_compute_type != compute_type):
            
            self.logger.info('Đang nạp AI Model [' + model_name + '] trên thiết bị [' + device + '] (' + compute_type + ')...')
            try:
                self.active_model = WhisperModel(model_name, device=device, compute_type=compute_type)
                self.active_model_name = model_name
                self.active_device = device
                self.active_compute_type = compute_type
                self.logger.success('✅ Nạp Model thành công!')
            except Exception as e:
                if device == 'cuda':
                    self.logger.warning('⚠️ Lỗi nạp CUDA GPU: ' + str(e) + '. Đang tự động chuyển sang CPU float32...')
                    self.active_model = WhisperModel(model_name, device='cpu', compute_type='float32')
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
        self.logger.info('--- BẮT ĐẦU TIẾN TRÌNH TẠO PHỤ ĐỀ AI ---')

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

        raw_model_str = self.cbo_model.get().split()[0]
        device = self.cbo_device.get()
        compute_type = self.cbo_compute.get()
        raw_lang = self.cbo_lang.get().split()[0]
        language = None if raw_lang == 'Auto' else raw_lang
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
                model = self._get_model(raw_model_str, device, compute_type)
                total = len(target_videos)
                processed = 0
                skipped = 0

                for idx, vpath in enumerate(target_videos, 1):
                    if self.stop_requested:
                        self.logger.warning(' Tiến trình đã được dừng bởi người dùng.')
                        break

                    srt_path = vpath.with_suffix('.srt')
                    if skip_existing and srt_path.exists() and srt_path.stat().st_size > 0:
                        self.logger.info('[' + str(idx) + '/' + str(total) + '] [-] Bỏ qua (Đã có .srt): ' + vpath.name)
                        skipped += 1
                        self.progress['value'] = int(idx / total * 100)
                        continue

                    self.logger.info('[' + str(idx) + '/' + str(total) + '] ⚡ Đang xử lý: ' + vpath.name)
                    t0 = time.time()

                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
                        tmp_audio_path = Path(tmp_audio.name)

                    try:
                        ok = extract_audio(vpath, tmp_audio_path, self.ffmpeg_bin, boost_vocals=boost_vocals)
                        if not ok:
                            self.logger.error('Lỗi trích xuất audio từ: ' + vpath.name)
                            continue

                        vad_params = dict(min_silence_duration_ms=400) if use_vad else None
                        try:
                            segments, info = model.transcribe(
                                str(tmp_audio_path),
                                language=language,
                                vad_filter=use_vad,
                                vad_parameters=vad_params,
                                word_timestamps=True
                            )
                        except Exception as vad_err:
                            if use_vad and ("onnx" in str(vad_err).lower() or "silero" in str(vad_err).lower() or "no_suchfile" in str(vad_err).lower()):
                                self.logger.warning('⚠️ Không thể tải VAD ONNX model, đang tự động tạo phụ đề không lọc VAD...')
                                segments, info = model.transcribe(
                                    str(tmp_audio_path),
                                    language=language,
                                    vad_filter=False,
                                    word_timestamps=True
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
                            self.logger.success('   -> [✓] Đã tạo xong: ' + srt_path.name + ' (' + str(len(subtitles)) + ' câu, ' + ('%.1f' % elapsed) + 's)')
                            processed += 1
                        else:
                            self.logger.warning('   -> [!] Không phát hiện lời thoại trong: ' + vpath.name)
                    finally:
                        if tmp_audio_path.exists():
                            try: tmp_audio_path.unlink()
                            except: pass

                    self.progress['value'] = int(idx / total * 100)

                self.progress['value'] = 100
                self.logger.success('🎉 HOÀN THÀNH TẠO PHỤ ĐỀ CHO ' + str(processed) + ' VIDEO! (Bỏ qua: ' + str(skipped) + ')')
                messagebox.showinfo('Hoàn thành', 'Đã xử lý xong ' + str(processed) + ' video!')
            except Exception as e:
                self.logger.error('Lỗi trong quá trình tạo phụ đề: ' + str(e))
                messagebox.showerror('Lỗi', 'Lỗi: ' + str(e))
            finally:
                self.is_running = False
                self.btn_start.config(state=tk.NORMAL)
                self.btn_stop.config(state=tk.DISABLED)

        threading.Thread(target=_worker, daemon=True).start()
