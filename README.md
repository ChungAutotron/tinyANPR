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

### Performance

Native C/C++ engine, no GPU needed - fast enough for **real-time camera
streams**, not just batch processing of stored images:

- **~32 ms** per plate for the full pipeline (detect + read text + read
  color), single-threaded on an ordinary CPU - **~31 fps**, comfortably
  above the frame rate of most surveillance cameras (typically 15-25 fps).
- Scales further with multiple threads/cameras: detection kernels are
  runtime-dispatched to the best available CPU instruction set (SSE2 up to
  AVX2), so the same binary runs safely and efficiently across a wide range
  of hardware.
- No PyTorch/ONNX Runtime dependency at runtime - smaller footprint, faster
  cold start, easier to deploy on edge/embedded PCs.

### vs. SimpleLPR

Measured on the same internal Vietnamese-plate validation set:

| | TinyANPR | SimpleLPR |
|---|---|---|
| Exact match (full plate text correct) | **85.9%** | 73.7% |
| Relative speed | **~5.7x faster** | 1x |

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

### Getting the full SDK + a license

The trial mode above is time-limited. For an unrestricted evaluation license
and the full model package, contact:

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

### Tốc độ xử lý

Engine thuần C/C++, không cần GPU - đủ nhanh để **chạy real-time trên
camera trực tiếp**, không chỉ xử lý theo lô ảnh có sẵn:

- **~32 ms** cho toàn bộ pipeline mỗi biển số (phát hiện + đọc chữ + đọc
  màu), đơn luồng trên CPU thường - tương đương **~31 fps**, vượt xa nhịp
  khung hình của hầu hết camera giám sát (thường 15-25 fps).
- Tận dụng thêm được khi chạy đa luồng/nhiều camera: các kernel nhận diện
  tự chọn tập lệnh CPU phù hợp nhất lúc chạy (từ SSE2 đến AVX2), nên cùng
  một bản build chạy an toàn và hiệu quả trên nhiều loại phần cứng khác nhau.
- Không phụ thuộc PyTorch/ONNX Runtime lúc chạy - gọn nhẹ hơn, khởi động
  nhanh hơn, dễ triển khai trên máy tính nhúng/edge.

### So với SimpleLPR

Đo trên cùng tập validation biển số Việt Nam nội bộ:

| | TinyANPR | SimpleLPR |
|---|---|---|
| Đọc đúng toàn bộ ký tự | **85.9%** | 73.7% |
| Tốc độ tương đối | **nhanh hơn ~5.7 lần** | 1x |

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

### Nhận bộ SDK đầy đủ + license

Chế độ dùng thử ở trên bị giới hạn thời gian. Muốn nhận license đánh giá
không giới hạn cùng gói model đầy đủ, liên hệ:

**toanchungk57m.uet@gmail.com**
