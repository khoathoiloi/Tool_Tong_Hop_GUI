# -*- coding: utf-8 -*-
from pathlib import Path

def extract_title_from_content(content: str) -> str:
    for line in content.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        lower_line = line_str.lower()
        if lower_line.startswith('tiêu đề đã đăng:'):
            parts = line_str.split(':', 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
        elif lower_line.startswith('tiêu đề link youtube:') or lower_line.startswith('tiêu đề:'):
            parts = line_str.split(':', 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return ''

def process_folder(subfolder: Path, overwrite: bool = True):
    target_names = ['link-da-dung.txt', 'link-da-dang.txt']
    txt_file = None
    for name in target_names:
        candidate = subfolder / name
        if candidate.exists():
            txt_file = candidate
            break
            
    if not txt_file:
        return False, 'Không có file link-da-dung.txt hoặc link-da-dang.txt'

    out_title_file = subfolder / 'title.txt'
    if not overwrite and out_title_file.exists() and out_title_file.stat().st_size > 0:
        return True, '[Bỏ qua - Đã có sẵn title.txt]'

    try:
        content = txt_file.read_text(encoding='utf-8', errors='ignore')
        title = extract_title_from_content(content)
        if not title:
            return False, 'Không tìm thấy dòng Tiêu đề trong file ' + txt_file.name
        
        out_title_file.write_text(title + '\n', encoding='utf-8')
        return True, title
    except Exception as e:
        return False, 'Lỗi đọc/ghi: ' + str(e)
