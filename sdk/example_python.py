# -*- coding: utf-8 -*-
"""example_python.py - minimal Python integration example for the TinyANPR SDK.

Run from this folder (sdk/):
    python example_python.py <path_to_image.jpg>

Uses trial mode (trial_start) - no license file needed, works on any machine.
Trial: 2 hours per rolling 24h window, decrypts tinyanpr_trial.sdk (same
detection model as the full license, only the decryption key differs).

To use a real license instead (no time limit):
    sdk.activate("<your_license.lic>", "<your_user>")
and load the full "tinyanpr.sdk" package instead of "tinyanpr_trial.sdk".

Call sequence:
    1. TinyAnpr(dll_path)   - load the native DLL
    2. trial_start(user)    - required first, every other call fails otherwise
    3. open_pack + set_region + load_reader + load_stage1 (one .sdk package)
    4. detect()             - find every plate in the image
    5. read_plate() + plate_color() for each detected plate
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2                                              # noqa: E402
from python.ta_anpr import TinyAnpr, TinyAnprError       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DLL_PATH = os.path.join(HERE, "tinyANPR_SDK.dll")
MODEL_PACK = os.path.join(HERE, "tinyanpr_trial.sdk")

COLOR_NAMES = {0: "white", 1: "yellow", 2: "blue", 3: "red", 4: "green"}
DRAW_COLOR = {0: (255, 255, 255), 1: (0, 220, 220), 2: (255, 120, 0),
              3: (0, 0, 255), 4: (0, 200, 0)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python example_python.py <path_to_image.jpg>")
        return 1
    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return 1

    print("--- TinyANPR SDK: minimal Python example ---")
    print(f"input image: {image_path}")

    sdk = TinyAnpr(dll_path=DLL_PATH)
    try:
        sdk.trial_start("example_user")
    except TinyAnprError as e:
        print(f"Could not start trial mode: {e}")
        print("  -> trial quota for today may be used up, try again in 24h")
        return 1
    print(f"[1] trial started - {sdk.trial_seconds_left()}s left today, "
          f"machine_id={sdk.machine_id}")

    sdk.open_pack(MODEL_PACK)
    sdk.set_region("vn")
    sdk.load_reader(MODEL_PACK)
    sdk.load_stage1(MODEL_PACK)
    print(f"[2] model loaded: {sdk.model_info}")

    bgr = cv2.imread(image_path)
    if bgr is None:
        print(f"Could not read image: {image_path}")
        return 1
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    detections = sdk.detect(rgb)
    print(f"[3] detect() -> {len(detections)} plate(s)")

    for i, d in enumerate(detections):
        text, conf, valid = sdk.read_plate(rgb, d["quad"], d["shape"])
        color = sdk.plate_color(rgb, d["quad"])
        bg_name = COLOR_NAMES.get(color[0], "?") if color else "?"
        text_name = COLOR_NAMES.get(color[1], "?") if color else "?"
        shape = "square" if d["shape"] else "long"
        print(f"    plate {i + 1}: '{text}'  (conf={conf:.2f} valid={valid} "
              f"shape={shape} background={bg_name} text_color={text_name} "
              f"detect_score={d['score']:.2f})")

        draw_color = DRAW_COLOR.get(color[0] if color else -1, (0, 255, 0))
        quad = d["quad"].reshape(-1, 2).astype(int)
        cv2.polylines(bgr, [quad], True, draw_color, 2)
        x1, y1 = quad.min(axis=0)
        cv2.putText(bgr, text or "?", (int(x1), max(int(y1) - 8, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, draw_color, 2)

    out_path = os.path.splitext(os.path.basename(image_path))[0] + "_result.jpg"
    cv2.imwrite(out_path, bgr)
    print(f"[4] result image saved: {os.path.abspath(out_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
