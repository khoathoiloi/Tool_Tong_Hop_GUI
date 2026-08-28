# -*- coding: utf-8 -*-
import os
import re
from pathlib import Path

def _process_single_folder(folder: Path, domain_filter: str = '', hashtag: str = ''):
    mp4_files = [
        f for f in folder.glob('*.mp4')
        if f.name.lower() != 'video-9x16.mp4'
    ]
    if not mp4_files:
        return None

    txt_file = folder / 'link-da-dang.txt'
    video_file = mp4_files[0]
    first_comment = ''
    title = ''
    raw_link = ''

    if txt_file.exists():
        try:
            content = txt_file.read_text(encoding='utf-8', errors='ignore')
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            candidate_links = []
            for line in lines:
                if line.lower().startswith('link đã đăng:') or line.lower().startswith('link:'):
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        candidate_links.append(parts[1].strip())
                elif line.lower().startswith('tiêu đề đã đăng:'):
                    parts = line.split(':', 1)
                    if len(parts) > 1 and not title:
                        title = parts[1].strip()
                elif line.lower().startswith('tiêu đề link youtube:') or line.lower().startswith('tiêu đề:'):
                    if not title:
                        parts = line.split(':', 1)
                        if len(parts) > 1:
                            title = parts[1].strip()
                else:
                    urls = re.findall(r'https?://[^\s]+', line)
                    for u in urls:
                        candidate_links.append(u.strip())

            if candidate_links:
                if domain_filter:
                    matched = [l for l in candidate_links if domain_filter in l.lower()]
                    raw_link = matched[0] if matched else candidate_links[0]
                else:
                    raw_link = candidate_links[0]
                
                first_comment = f"watch full here 👉: {raw_link}" if raw_link else ""
        except Exception:
            pass

    if not title:
        title = video_file.stem
        if '-' in title and ' ' not in title:
            title = title.replace('-', ' ').title()

    caption = title
    if hashtag:
        tags = []
        for t in re.split(r'[,; ]+', hashtag):
            t = t.strip()
            if not t:
                continue
            if not t.startswith('#'):
                t = '#' + t
            tags.append(t)
        if tags:
            caption = f"{title} {' '.join(tags)}"

    return {
        'folder': folder.name,
        'folder_path': str(folder.resolve()),
        'video_path': str(video_file.resolve()),
        'title': title,
        'caption': caption,
        'raw_link': raw_link,
        'first_comment': first_comment
    }

def scan_and_prepare_data(kho_path_str, domain_filter='', hashtag='', exclude_folders=None):
    kho_path = Path(kho_path_str)
    if not kho_path.exists() or not kho_path.is_dir():
        return []

    domain_filter = domain_filter.strip().lower()
    hashtag = hashtag.strip()
    exclude_set = {str(Path(p).resolve()) for p in exclude_folders} if exclude_folders else set()

    valid_items = []
    
    # 1. Kiểm tra folder được chọn
    item_self = _process_single_folder(kho_path, domain_filter, hashtag)
    if item_self:
        if item_self['folder_path'] not in exclude_set:
            valid_items.append(item_self)

    # 2. Quét các subfolder
    subfolders = sorted([f for f in kho_path.iterdir() if f.is_dir()])
    for folder in subfolders:
        if str(folder.resolve()) in exclude_set:
            continue
        item = _process_single_folder(folder, domain_filter, hashtag)
        if item and item['folder_path'] not in exclude_set:
            valid_items.append(item)

    return valid_items