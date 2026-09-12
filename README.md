# TinyANPR

A lightweight, dependency-free Automatic Number Plate Recognition (ANPR/LPR)
SDK for Vietnamese license plates. Pure native C/C++ inference engine (no
PyTorch/ONNX Runtime needed at runtime), with bindings for Python and C#.

## Supported plates

- **Vietnam** license plates (white/blue/yellow/red/green backgrounds), both
  long and square formats.
- Detects the plate location, reads the text, and classifies the plate color.

## Accuracy

Measured on a held-out validation set (200 real-world images, not seen during
training):

| Metric | Score |
|---|---|
| Exact match (full plate text correct) | **95.5%** |
| Character error rate (CER) | **2.4%** |

Runs in a few milliseconds per plate on a normal CPU - no GPU required.

## Repository layout

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

## Quick start (Python)

```
cd sdk
python example_python.py path/to/your/plate_image.jpg
```

No license required - this runs in trial mode (2 hours of use per rolling
24-hour window). See `sdk/example_python.py` for the full integration
sequence (activate/trial_start -> load model -> detect -> read plate).

## Getting the full SDK + a free 1-year license

The trial mode above is time-limited. For an unrestricted evaluation license
(1 year, free) and the full model package, contact:

**toanchungk57m.uet@gmail.com**
