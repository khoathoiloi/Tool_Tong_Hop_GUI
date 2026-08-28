# -*- coding: utf-8 -*-
import queue
import datetime
import tkinter as tk

class UILogger:
    def __init__(self, text_widget, root):
        self.text_widget = text_widget
        self.root = root
        self.log_queue = queue.Queue()
        self._setup_tags()
        self._poll()

    def _setup_tags(self):
        self.text_widget.tag_config('TIME', foreground='#6c7086')
        self.text_widget.tag_config('INFO', foreground='#cdd6f4')
        self.text_widget.tag_config('SUCCESS', foreground='#a6e3a1', font=('Consolas', 9, 'bold'))
        self.text_widget.tag_config('WARNING', foreground='#f9e2af')
        self.text_widget.tag_config('ERROR', foreground='#f38ba8', font=('Consolas', 9, 'bold'))
        self.text_widget.tag_config('HIGHLIGHT', foreground='#89b4fa', font=('Consolas', 9, 'bold'))

    def log(self, message: str, level: str = 'INFO'):
        now_str = datetime.datetime.now().strftime('%H:%M:%S')
        self.log_queue.put((now_str, message, level))

    def info(self, msg): self.log(msg, 'INFO')
    def success(self, msg): self.log(msg, 'SUCCESS')
    def warning(self, msg): self.log(msg, 'WARNING')
    def error(self, msg): self.log(msg, 'ERROR')
    def highlight(self, msg): self.log(msg, 'HIGHLIGHT')

    def clear(self):
        self.text_widget.delete('1.0', tk.END)

    def _poll(self):
        try:
            while not self.log_queue.empty():
                now_str, message, level = self.log_queue.get_nowait()
                self.text_widget.insert(tk.END, '[' + now_str + '] ', 'TIME')
                self.text_widget.insert(tk.END, str(message) + '\n', level)
                self.text_widget.see(tk.END)
        except Exception:
            pass
        finally:
            self.root.after(100, self._poll)
