# -*- coding: utf-8 -*-
import os
import re
from pathlib import Path

def _normalize_domain(domain_str: str) -> str:
    """Chuẩn hóa chuỗi domain: bỏ https://, http://, www., và dấu / ở đuôi"""
    if not domain_str:
        return ""
    d = domain_str.strip().lower()
    d = re.sub(r'^https?://', '', d)
    d = re.sub(r'^www\.', '', d)
    d = d.rstrip('/')
    return d

def _extract_from_txt_file(txt_file: Path):
    """
    Trích xuất danh sách links và title từ 1 file .txt
    Trả về dict: {'links': [str], 'title': str}
    """
    links = []
    title = ''
    try:
        content = txt_file.read_text(encoding='utf-8', errors='ignore')
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        for line in lines:
            if line.lower().startswith('link đã đăng:') or line.lower().startswith('link:'):
                parts = line.split(':', 1)
                if len(parts) > 1:
                    u = parts[1].strip()
                    if u and u not in links:
                        links.append(u)
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
                    u_clean = u.strip()
                    if u_clean and u_clean not in links:
                        links.append(u_clean)
    except Exception:
        pass

    return {'links': links, 'title': title}

def _process_single_folder(folder: Path, domain_filter: str = '', hashtag: str = ''):
    mp4_files = [
        f for f in folder.glob('*.mp4')
        if f.name.lower() != 'video-9x16.mp4'
    ]
    if not mp4_files:
        return None

    video_file = mp4_files[0]
    title = ''
    raw_link = ''
    first_comment = ''

    clean_filter = _normalize_domain(domain_filter)

    # 1. Tìm toàn bộ file .txt trong folder, ưu tiên file link-da-dang.txt đầu tiên
    all_txt_files = list(folder.glob('*.txt'))
    priority_order = ['link-da-dang.txt', 'link.txt', 'links.txt', 'url.txt', 'info.txt', 'title.txt']

    def _sort_key(p: Path):
        name_lower = p.name.lower()
        if name_lower in priority_order:
            return priority_order.index(name_lower)
        return len(priority_order) + 1

    sorted_txt_files = sorted(all_txt_files, key=_sort_key)

    # Thu thập tất cả links và title theo từng file
    extracted_data_list = []
    for txt_path in sorted_txt_files:
        data = _extract_from_txt_file(txt_path)
        if data['links'] or data['title']:
            extracted_data_list.append((txt_path, data))

    # 2. Xử lý tìm Link khớp
    if clean_filter:
        # Trường hợp CÓ nhập domain lọc -> Quét toàn bộ các file .txt để tìm link khớp domain đó
        for txt_path, data in extracted_data_list:
            for l in data['links']:
                # So khớp domain: kiểm tra clean_filter có trong link
                if clean_filter in l.lower():
                    raw_link = l
                    if not title and data['title']:
                        title = data['title']
                    break
            if raw_link:
                break
        # Nếu quét hết tất cả file .txt mà không có link nào khớp domain đã lọc
        # -> raw_link giữ nguyên là rỗng '', TUYỆT ĐỐI KHÔNG lấy domain khác!
    else:
        # Trường hợp KHÔNG nhập domain lọc -> Lấy link đầu tiên từ file ưu tiên đầu tiên
        for txt_path, data in extracted_data_list:
            if data['links']:
                raw_link = data['links'][0]
                if not title and data['title']:
                    title = data['title']
                break

    # Nếu vẫn chưa có title thì lấy title đầu tiên tìm được trong bất kỳ file .txt nào
    if not title:
        for txt_path, data in extracted_data_list:
            if data['title']:
                title = data['title']
                break

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

    if raw_link:
        first_comment = f"watch full here 👉: {raw_link}"

    return {
        'folder': folder.name,
        'folder_path': str(folder.resolve()),
        'video_path': str(video_file.resolve()),
        'title': title,
        'caption': caption,
        'raw_link': raw_link,
        'first_comment': first_comment
    }

def scan_and_prepare_data(kho_path_str, domain_filter='', hashtag='', exclude_folders=None, shuffle_folders=False):
    import random
    kho_path = Path(kho_path_str)
    if not kho_path.exists() or not kho_path.is_dir():
        return []

    domain_filter = domain_filter.strip()
    hashtag = hashtag.strip()
    exclude_set = {str(Path(p).resolve()) for p in exclude_folders} if exclude_folders else set()

    valid_items = []
    
    # 1. Kiểm tra folder được chọn
    item_self = _process_single_folder(kho_path, domain_filter, hashtag)
    if item_self:
        if item_self['folder_path'] not in exclude_set:
            valid_items.append(item_self)

    # 2. Quét các subfolder
    subfolders = [f for f in kho_path.iterdir() if f.is_dir()]
    if shuffle_folders:
        random.shuffle(subfolders)
    else:
        subfolders = sorted(subfolders)

    for folder in subfolders:
        if str(folder.resolve()) in exclude_set:
            continue
        item = _process_single_folder(folder, domain_filter, hashtag)
        if item and item['folder_path'] not in exclude_set:
            valid_items.append(item)

    if shuffle_folders and valid_items:
        random.shuffle(valid_items)

    return valid_items