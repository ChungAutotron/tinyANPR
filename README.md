# TinyANPR

*[English](#english) | [Tiếng Việt](#tiếng-việt)*

---

## English

A lightweight, dependency-free Automatic Number Plate Recognition (ANPR/LPR)
SDK for Vietnamese license plates. Pure native C/C++ inference engine (no
PyTorch/ONNX Runtime needed at runtime), with bindings for Python and C#.

### Supported plates

- **Vietnam** license plates (white/blue/yellow/red/green backgrounds), both
  long and square formats.
- Detects the plate location, reads the text, and classifies the plate color.

### Accuracy

Measured on a held-out validation set (200 real-world images, not seen during
training):

| Metric | Score |
|---|---|
| Exact match (full plate text correct) | **95.5%** |
| Character error rate (CER) | **2.4%** |

Runs in a few milliseconds per plate on a normal CPU - no GPU required.

### Repository layout

```
example/        Ready-to-run demo app (Windows .exe, trial mode - no
                license needed, 2h/day). Just double-click TinyANPR_Demo.exe.
sdk/            Integration files for developers:
  tinyANPR_SDK.dll       the native engine (C ABI)
  tinyanpr_trial.sdk     trial-mode model package (2h/day, no license)
  include/ta_anpr.h      C header
  python/ta_anpr.py      Python binding (ctypes)
  csharp/TaAnpr.cs       C# binding (P/Invoke)
  example_python.py      minimal runnable Python example
```

### Quick start (Python)

```
cd sdk
python example_python.py path/to/your/plate_image.jpg
```

No license required - this runs in trial mode (2 hours of use per rolling
24-hour window). See `sdk/example_python.py` for the full integration
sequence (activate/trial_start -> load model -> detect -> read plate).

### Getting the full SDK + a free 1-year license

The trial mode above is time-limited. For an unrestricted evaluation license
(1 year, free) and the full model package, contact:

**toanchungk57m.uet@gmail.com**

---

## Tiếng Việt

Bộ SDK nhận dạng biển số xe (ANPR/LPR) gọn nhẹ, không phụ thuộc thư viện
ngoài, dành cho biển số xe Việt Nam. Engine suy luận thuần C/C++ (không cần
PyTorch/ONNX Runtime lúc chạy), có sẵn binding cho Python và C#.

### Biển số hỗ trợ

- Biển số **Việt Nam** (nền trắng/xanh/vàng/đỏ/lục), cả dạng dài và vuông.
- Phát hiện vị trí biển, đọc chữ trên biển, và nhận diện màu biển.

### Độ chính xác

Đo trên tập validation (200 ảnh thực tế, không dùng để huấn luyện):

| Chỉ số | Kết quả |
|---|---|
| Đọc đúng toàn bộ ký tự | **95.5%** |
| Tỷ lệ lỗi ký tự (CER) | **2.4%** |

Chạy trong vài mili-giây/biển số trên CPU thường - không cần GPU.

### Cấu trúc thư mục

```
example/        Bản demo chạy thử ngay (.exe cho Windows, chế độ dùng thử -
                khong can license, 2 gio/ngay). Chi can mo TinyANPR_Demo.exe.
sdk/            File tich hop cho lap trinh vien:
  tinyANPR_SDK.dll       engine goc (C ABI)
  tinyanpr_trial.sdk     goi model cho che do dung thu (2h/ngay, khong can license)
  include/ta_anpr.h      header C
  python/ta_anpr.py      binding Python (ctypes)
  csharp/TaAnpr.cs       binding C# (P/Invoke)
  example_python.py      vi du Python don gian, chay duoc ngay
```

### Bắt đầu nhanh (Python)

```
cd sdk
python example_python.py duong_dan_anh_bien_so.jpg
```

Không cần license - chạy ở chế độ dùng thử (2 giờ mỗi 24 giờ). Xem
`sdk/example_python.py` để biết trình tự tích hợp đầy đủ (activate/
trial_start -> nạp model -> detect -> đọc biển).

### Nhận bộ SDK đầy đủ + license miễn phí 1 năm

Chế độ dùng thử ở trên bị giới hạn thời gian. Muốn nhận license đánh giá
không giới hạn (1 năm, miễn phí) cùng gói model đầy đủ, liên hệ:

**toanchungk57m.uet@gmail.com**
