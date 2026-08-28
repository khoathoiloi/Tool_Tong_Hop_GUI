# -*- coding: utf-8 -*-
import os
import re
import subprocess
import tempfile
from pathlib import Path
from core.cuda_env import setup_cuda_dlls
from core.ffmpeg_finder import find_ffmpeg

setup_cuda_dlls()

def format_timestamp(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    if secs >= 60:
        mins += 1
        secs = 0
    if mins >= 60:
        hrs += 1
        mins = 0
    return '%02d:%02d:%02d,%03d' % (hrs, mins, secs, millis)

def extract_audio(video_path: Path, output_audio_path: Path, ffmpeg_bin: str, boost_vocals: bool = True) -> bool:
    af_filter = 'dynaudnorm=f=75:g=15:m=15.0:r=0.9' if boost_vocals else 'anull'
    cmd = [
        ffmpeg_bin,
        '-y',
        '-threads', '0',
        '-i', str(video_path),
        '-vn',
        '-af', af_filter,
        '-acodec', 'pcm_s16le',
        '-ar', '16000',
        '-ac', '1',
        str(output_audio_path)
    ]
    creationflags = 0
    if os.name == 'nt':
        creationflags = subprocess.CREATE_NO_WINDOW
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
    return res.returncode == 0 and os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 0

def segment_words_to_subtitles(words, max_chars=36, max_words=7):
    subtitles = []
    current_chunk = []
    current_chars = 0

    for w in words:
        word_text = w.word.strip()
        if not word_text:
            continue

        w_len = len(word_text)
        new_len = current_chars + (1 if current_chars > 0 else 0) + w_len

        split_condition = (
            len(current_chunk) >= max_words or
            (current_chars > 0 and new_len > max_chars) or
            (current_chunk and (w.start - current_chunk[-1].end > 0.65)) or
            (current_chunk and re.search(r'[.?!,;:]$', current_chunk[-1].word.strip()))
        )

        if split_condition and current_chunk:
            start_t = current_chunk[0].start
            end_t = current_chunk[-1].end
            text = ' '.join(item.word.strip() for item in current_chunk)
            subtitles.append((start_t, end_t, text))
            current_chunk = []
            current_chars = 0

        current_chunk.append(w)
        current_chars += (1 if current_chars > 0 else 0) + w_len

    if current_chunk:
        start_t = current_chunk[0].start
        end_t = current_chunk[-1].end
        text = ' '.join(item.word.strip() for item in current_chunk)
        subtitles.append((start_t, end_t, text))

    return subtitles

def write_srt_file(subtitles, srt_path):
    with open(srt_path, 'w', encoding='utf-8') as f:
        for idx, (start_t, end_t, text) in enumerate(subtitles, start=1):
            if end_t <= start_t:
                end_t = start_t + 0.5
            start_str = format_timestamp(start_t)
            end_str = format_timestamp(end_t)
            clean_text = text.strip()
            if clean_text:
                f.write(str(idx) + '\n' + start_str + ' --> ' + end_str + '\n' + clean_text + '\n\n')
