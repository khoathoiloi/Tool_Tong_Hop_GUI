# 🚀 MasterToolHub - Bộ Công Cụ Tổng Hợp Fanpage & Media (v2.6.1)

<p align="center">
  <img src="https://img.shields.io/badge/version-2.6.1-blue.svg?cacheSeconds=2592000" alt="Version 2.6.1" />
  <img src="https://img.shields.io/badge/Python-3.12-brightgreen.svg" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/CUDA-12.x-green.svg" alt="CUDA 12" />
  <img src="https://img.shields.io/badge/License-MIT-orange.svg" alt="License MIT" />
</p>

Bộ phần mềm đồ họa (GUI) tổng hợp **All-in-One** tích hợp toàn bộ các công cụ biên tập Fanpage, tạo phụ đề AI siêu tốc, xử lý tiêu đề và tự động hóa rút gọn link trong một cửa sổ làm việc duy nhất.

---

## 📥 TẢI VỀ & SỬ DỤNG NGAY (PORTABLE - KHÔNG CẦN CÀI ĐẶT)

👉 **[Tải Bản Mới Nhất (MasterToolHub_v2.6.1.zip)](https://github.com/khoathoiloi/Tool_Tong_Hop_GUI/releases/latest)**

*Tải về, giải nén và mở file `MasterToolHub.exe` hoặc click đúp `run_app.bat` để chạy ngay.*

---

## ✨ CÁC TÍNH NĂNG CHÍNH

### 1. 📊 Tạo File Excel Fanpage Reels + Combo Tự Động Rút Gọn Link
- **Nhập liệu linh hoạt**: Hỗ trợ nạp từ file TXT danh sách Page hoặc dán trực tiếp.
- **Khớp kho video**: Tự động nhận diện video và file `link-da-dang.txt`, ghép tiêu đề, link và caption.
- **⚡ Tính năng Combo Rút Gọn Link**: Tự động kết nối ShiftLink, rút gọn link gốc và **gán trực tiếp vào cột 'Bình luận đầu tiên'** (không sinh cột thừa).
- **Chống trùng lặp (Anti-duplicate)**: Tự động ghi nhớ các video đã từng lấy để tránh đăng trùng bài.

### 2. ⚡ AI Faster-Whisper Video to SRT (100% GPU NVIDIA CUDA)
- **Tăng tốc phần cứng**: Chạy trực tiếp trên GPU NVIDIA RTX (RTX 3060...) bằng nhân **Tensor Cores `float16`**, bóc tách âm thanh sang file `.srt` siêu tốc.
- **Bộ lọc Dynamic Audio Normalizer (`DynAudNorm`)**: Tự động kích âm thanh những đoạn nói nhỏ/thì thầm.
- **Lọc khoảng lặng VAD & Gom câu thông minh**: Chia dòng ngắn gọn (tối đa 36 ký tự, 7 từ) chuẩn định dạng video ngắn Reels / TikTok / Shorts.

### 3. 📝 Trích Xuất Tiêu Đề Đã Đăng (`title.txt`)
- Quét kho thư mục video, đọc `link-da-dung.txt` / `link-da-dang.txt` và tự động tạo file `title.txt` chuẩn cho từng folder.

### 4. 🔗 Rút Gọn Link ShiftLink Automation
- Tự động nhận diện cột link trong file Excel và danh sách Sheet.
- Tạo slug ngẫu nhiên độ dài 15-21 ký tự, bộ nhớ đệm cache URL tránh gọi trùng.
- Đã tích hợp sẵn **8 tên miền chuẩn của web**: `nextpart2.online`, `fullstoriesdrama.com`, `reviewphan2.com`, `fullguide.tips`, `phimhay.fit`, `filmgood.shop`, `nextpartfull.com`, `nextfullvideo.com`.

### 5. 🔄 Tự Động Cập Nhật Trực Tiếp Trên App (GitHub Auto-Updater)
- Tích hợp sẵn tính năng kiểm tra và tự động cập nhật ngay trên giao diện phần mềm khi có phiên bản mới trên GitHub.

---

## 🛠️ HƯỚNG DẪN CÀI ĐẶT & PHÁT TRIỂN TỪ SOURCE CODE

```bash
# 1. Clone repository
git clone https://github.com/khoathoiloi/Tool_Tong_Hop_GUI.git
cd Tool_Tong_Hop_GUI

# 2. Cài đặt các thư viện phụ thuộc
pip install openpyxl faster-whisper playwright torch torchvision torchaudio

# 3. Cài đặt trình duyệt Playwright (nếu chưa có)
playwright install chromium

# 4. Chạy ứng dụng
python app.py
```

---

## 📜 BẢN QUYỀN & TÁC GIẢ
Phát triển bởi **Khoa Thoi Loi** (@khoathoiloi). Mọi đóng góp và báo lỗi xin vui lòng tạo Issue trên GitHub.