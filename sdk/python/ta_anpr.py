# -*- coding: utf-8 -*-
"""
Binding Python (ctypes) cho tinyANPR_SDK.dll - Tiny ANPR SDK.

Dung trong examples/live_camera: Stage 1 (detector+refine) van chay PyTorch,
Stage 2 (doc chu) goi THANG vao engine C Q15 - dung ngay tinh than ghi trong
infer_pipeline.py tu dau: "khi DLL san sang chi can thay bang ctypes, GUI/camera
KHONG doi". Zones cung lay ban C (cung ray-casting voi infer/zones.py).

    from sdk.python.ta_anpr import TinyAnpr
    anpr = TinyAnpr()                                  # tu tim tinyANPR_SDK.dll trong sdk/
    anpr.activate("sdk/license_hiennt.lic", "hiennt@autotron.vn")
    anpr.load_reader("sdk/models/m12v2c_q15/reader_model.bin")
    anpr.threads = 8
    lane = anpr.add_zone([(100,300),(900,300),(950,700),(50,700)])
    text, conf = anpr.read_canon(canon_hwc, shape)     # canon: [h,w,in_ch] float64
"""

import ctypes as ct
import os


class TaDet(ct.Structure):
    _fields_ = [("box", ct.c_float * 4), ("quad", ct.c_float * 8),
                ("score", ct.c_float), ("shape", ct.c_int)]


class TaTrackOut(ct.Structure):
    _fields_ = [("track_id", ct.c_int), ("crossed", ct.c_int),
                ("line_id", ct.c_int), ("direction", ct.c_int)]

class TaPlate(ct.Structure):
    """Khop ta_plate_t trong sdk/include/ta_anpr.h (ta_process_frame)."""
    _fields_ = [("box", ct.c_float * 4), ("quad", ct.c_float * 8),
                ("score", ct.c_float), ("shape", ct.c_int),
                ("zone_id", ct.c_int), ("text", ct.c_char * 16),
                ("text_conf", ct.c_float),
                ("plate_color", ct.c_int), ("text_color", ct.c_int)]


_ERR = {0: "OK", -1: "BAD_ARG", -2: "NO_LICENSE", -3: "WRONG_USER", -4: "EXPIRED",
        -5: "BAD_MODEL", -6: "SELFTEST_FAILED", -7: "NOT_READY", -8: "NO_SPACE",
        -9: "WRONG_MACHINE (license khong cap cho may nay)",
        -10: "WRONG_APP (license khong cap cho ung dung nay)",
        -11: "CLOCK (dong ho may bi lui ve truoc lan chay gan nhat)",
        -12: "TAMPER (tep da bi sua - chu ky khong khop)"}

# Chu ky callback nhat ky: void(int level, const char* msg, void* user)
LOG_FN = ct.CFUNCTYPE(None, ct.c_int, ct.c_char_p, ct.c_void_p)


class TinyAnprError(RuntimeError):
    def __init__(self, what, code):
        super().__init__(f"{what}: {_ERR.get(code, code)}")
        self.code = code


def co_avx2():
    """CPU nay co AVX2 khong (Windows). Khong biet chac -> tra True (giu duong cu).

    VI SAO CAN: tinyANPR_SDK.dll bien dich voi /arch:AVX2, may khong co AVX2 thi
    NAP DLL LA CHET NGAY voi 0xc000001d (STATUS_ILLEGAL_INSTRUCTION) - ma loi do
    khong noi gi ve nguyen nhan. Da gap that 2026-09-11 tren mot may Ivy Bridge
    (Family 6 Model 62, doi 2013): app tat ngay khi mo, khong hien gi.
    AVX2 co tu Intel Haswell (2013) va AMD Excavator (2015).
    PF_AVX2_INSTRUCTIONS_AVAILABLE = 40 (winnt.h).
    """
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))
    except Exception:
        return True


def _default_dll():
    # Ban dong goi: sdk/ nam CANH .exe chu khong nam trong thu muc tam giai nen
    import sys
    # Ten thu vien doi thanh tinyANPR_SDK.dll (2026-07-30). Van thu ten cu
    # ta_anpr.dll phia sau de ban giao / ban build cu chua doi ten van chay.
    # GO BAN DU PHONG noavx2 (2026-09-12): sau khi dung LAI dung co, hai tep
    # co .text GIONG HET NHAU - SDK chinh von KHONG dung /arch:AVX2, no chon
    # duong bang CPUID luc chay va tu 2026-09-12 mac dinh la SSE. Nghia la ban
    # 'du phong' chi la bua ho menh: neu ban chinh chet tren may cu thi no cung
    # chet y het. Giu hai tep chi tao them mot thu de lac hau - da tra gia dung
    # the: no build TAY, thieu co toi uu (cham 9.4 lan) va khong duoc dung lai
    # sau khi sua loi buoc nhay Cpad -> may khach doc ra rac ca thang.
    # Van thu ten noavx2 SAU CUNG de ban giao cu (co san tep do) khong gay.
    TEN = ("tinyANPR_SDK.dll", "ta_anpr.dll", "tinyANPR_SDK_noavx2.dll")
    thu = []
    if getattr(sys, "frozen", False):
        d = os.path.dirname(os.path.abspath(sys.executable))
        thu += [os.path.join(d, t) for t in TEN]
        thu += [os.path.join(d, "sdk", t) for t in TEN]
    here = os.path.dirname(os.path.abspath(__file__))
    thu += [os.path.join(here, os.pardir, t) for t in TEN]
    for p in thu:
        if os.path.exists(p):
            return p
    return thu[-len(TEN)]        # bao loi voi ten MOI cho de hieu


class TinyAnpr:
    def __init__(self, dll_path=None, wait_policy="passive", simd=None):
        """wait_policy: dat OMP_WAIT_POLICY TRUOC khi nap DLL.

        BAT BUOC de ta_set_cpu_budget co tac dung. Mac dinh OpenMP cua MSVC la
        ACTIVE: sau moi vung song song, cac luong tho QUAY TIT cho viec ke tiep
        thay vi ngu - nen luong chinh co ngu bao nhieu thi CPU van bi an.
        Do thuc te 2026-07-30, 4 luong doc bien:
            wait_policy      budget 100%     budget 25%
            (mac dinh)        3.97 nhan      3.19 nhan   <- ham VO TAC DUNG
            passive           3.10 nhan      0.54 nhan   <- dung nhu thiet ke
        Doi lai: passive lam thong luong giam ~9% (79 -> 72 luot/giay) vi moi
        vung song song phai danh thuc luong. Voi app co UI / nhieu camera thi
        rat dang; can toi da thong luong tho thi truyen wait_policy=None.
        KHONG doi duoc luc chay - runtime OpenMP doc bien nay MOT LAN luc nap.

        simd: TRAN muc SIMD. None = MAC DINH CUA SDK, tuc SSE (chot
        2026-09-12: hau het may khach chi co SSE/AVX1, de moi may chay CUNG
        mot duong thi thu duoc kiem chinh la thu duoc giao). Muon nhanh hon
        tren may co AVX2 thi truyen simd="avx2" - do 250 anh val: 18.90 ->
        14.55 ms/anh. Nhan: "scalar" | "sse" | "avx2" | "avx512" | "auto".
        PHAI dat TRUOC ta_create() - muc bi KHOA o lan dung dau tien."""
        if wait_policy:
            os.environ.setdefault("OMP_WAIT_POLICY", wait_policy)
        self.lib = ct.CDLL(os.path.abspath(dll_path or _default_dll()))
        if simd is not None:
            MUC = {"scalar": 0, "sse": 1, "avx2": 2, "avx512": 3, "auto": -1}
            if isinstance(simd, str):
                if simd not in MUC:
                    raise ValueError(f"simd={simd!r}: chon trong {sorted(MUC)}")
                simd = MUC[simd]
            try:
                self.lib.ta_set_simd.argtypes = [ct.c_int]
                self.lib.ta_set_simd.restype = None
                self.lib.ta_set_simd(int(simd))   # TRUOC ta_create()
            except AttributeError:
                raise RuntimeError("DLL cu chua co ta_set_simd (can >= 0.6.1)")
        L = self.lib
        L.ta_create.restype = ct.c_void_p
        L.ta_destroy.argtypes = [ct.c_void_p]
        L.ta_version.restype = ct.c_char_p
        L.ta_activate.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p]
        # DLL CU KHONG CO hai ham nay - khai bao co dieu kien, dung de mot ban
        # binding moi di voi mot tinyANPR_SDK.dll cu la app chet ngay luc khoi tao
        # voi "AttributeError: function 'ta_activate_ex' not found".
        self.co_activate_ex = hasattr(L, "ta_activate_ex")
        if self.co_activate_ex:
            L.ta_activate_ex.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p,
                                         ct.c_char_p]
        self.co_machine_id = hasattr(L, "ta_machine_id")
        if self.co_machine_id:
            L.ta_machine_id.argtypes = [ct.c_char_p, ct.c_int]
            L.ta_machine_id.restype = ct.c_int
        L.ta_license_info.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int]
        L.ta_load_reader.argtypes = [ct.c_void_p, ct.c_char_p]
        # Stage 1 chi co o DLL tu 2026-07-30 - DLL cu van dung duoc (app tu lui
        # ve duong PyTorch), nen kiem su ton tai chu khong gia dinh.
        if hasattr(L, "ta_load_stage1"):
            L.ta_load_stage1.argtypes = [ct.c_void_p, ct.c_char_p]
            L.ta_stage1_info.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int]
            L.ta_detect.argtypes = [ct.c_void_p, ct.POINTER(ct.c_ubyte),
                                    ct.c_int, ct.c_int, ct.c_float, ct.c_float,
                                    ct.POINTER(ct.c_float), ct.c_int, ct.c_int]
            L.ta_detect.restype = ct.c_int
            L.ta_read_plate.argtypes = [ct.c_void_p, ct.POINTER(ct.c_ubyte),
                                        ct.c_int, ct.c_int,
                                        ct.POINTER(ct.c_float), ct.c_int,
                                        ct.c_char_p, ct.c_int,
                                        ct.POINTER(ct.c_float),
                                        ct.POINTER(ct.c_int)]
        if hasattr(L, "ta_warp_plate"):          # 2026-09-10: nan anh bien tu anh goc
            L.ta_warp_plate.argtypes = [ct.c_void_p, ct.POINTER(ct.c_ubyte),
                                        ct.c_int, ct.c_int, ct.POINTER(ct.c_float),
                                        ct.c_float, ct.c_int, ct.c_int,
                                        ct.POINTER(ct.c_ubyte)]
            L.ta_warp_plate.restype = ct.c_int
            L.ta_plate_size.argtypes = [ct.POINTER(ct.c_float), ct.c_float,
                                        ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
            L.ta_plate_size.restype = ct.c_int
        if hasattr(L, "ta_pack_open"):
            L.ta_pack_open.argtypes = [ct.c_void_p, ct.c_char_p]
            L.ta_pack_size.argtypes = [ct.c_void_p, ct.c_char_p]
            L.ta_pack_read.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p,
                                       ct.c_int]
            L.ta_pack_list.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int]
        # --- v0.6: goi v2 (khoa theo license) + sieu du lieu + bao mat ---
        self.co_goi_v2 = hasattr(L, "ta_pack_build_ex")
        if self.co_goi_v2:
            L.ta_pack_build_ex.argtypes = [ct.c_void_p, ct.c_char_p,
                                           ct.POINTER(ct.c_char_p),
                                           ct.POINTER(ct.c_char_p), ct.c_int,
                                           ct.c_char_p]
            L.ta_pack_meta.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int]
            L.ta_security_info.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int]
            L.ta_strerror.argtypes = [ct.c_int]
            L.ta_strerror.restype = ct.c_char_p
            L.ta_set_log.argtypes = [LOG_FN, ct.c_void_p]
            L.ta_set_max_longest.argtypes = [ct.c_void_p, ct.c_int]
            L.ta_get_max_longest.argtypes = [ct.c_void_p]
            L.ta_process_frame.argtypes = [ct.c_void_p, ct.POINTER(ct.c_ubyte),
                                           ct.c_int, ct.c_int,
                                           ct.POINTER(TaPlate), ct.c_int]
        self.co_plate_fix = hasattr(L, "ta_plate_fix")
        if self.co_plate_fix:
            L.ta_plate_fix.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int,
                                       ct.c_char_p, ct.c_int]
            L.ta_plate_display.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p,
                                           ct.c_char_p, ct.c_int]
        L.ta_model_info.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int]
        L.ta_set_threads.argtypes = [ct.c_void_p, ct.c_int]
        L.ta_set_performance.argtypes = [ct.c_void_p, ct.c_int]
        L.ta_cpu_count.restype = ct.c_int
        L.ta_get_threads.argtypes = [ct.c_void_p]
        L.ta_zone_add.argtypes = [ct.c_void_p, ct.POINTER(ct.c_float), ct.c_int]
        L.ta_zone_add_rect.argtypes = [ct.c_void_p] + [ct.c_float] * 4
        L.ta_zone_update.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(ct.c_float), ct.c_int]
        L.ta_zone_remove.argtypes = [ct.c_void_p, ct.c_int]
        self.co_zone_notify = hasattr(L, "ta_zone_set_notify")
        if self.co_zone_notify:
            L.ta_zone_set_notify.argtypes = [ct.c_void_p, ct.c_int, ct.c_int]
            L.ta_zone_notify.argtypes = [ct.c_void_p, ct.c_int]
            L.ta_zone_set_confirm.argtypes = [ct.c_void_p, ct.c_int, ct.c_int]
            L.ta_zone_confirm.argtypes = [ct.c_void_p, ct.c_int]
        L.ta_zone_count.argtypes = [ct.c_void_p]
        L.ta_zone_list.argtypes = [ct.c_void_p, ct.POINTER(ct.c_int),
                                   ct.POINTER(ct.c_int), ct.POINTER(ct.c_float), ct.c_int]
        L.ta_zone_clear.argtypes = [ct.c_void_p]
        L.ta_zone_of_quad.argtypes = [ct.c_void_p, ct.POINTER(ct.c_float)]
        L.ta_co_color.argtypes = [ct.c_void_p]
        L.ta_plate_color.argtypes = [ct.c_void_p, ct.POINTER(ct.c_ubyte), ct.c_int,
                                     ct.c_int, ct.POINTER(ct.c_float),
                                     ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
        L.ta_read_canon.argtypes = [ct.c_void_p, ct.POINTER(ct.c_double), ct.c_int,
                                    ct.c_int, ct.c_int, ct.c_char_p, ct.c_int,
                                    ct.POINTER(ct.c_float), ct.POINTER(ct.c_int)]
        L.ta_read_golden.argtypes = [ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_int,
                                     ct.POINTER(ct.c_float), ct.POINTER(ct.c_int)]
        L.ta_format_valid.argtypes = [ct.c_char_p, ct.c_char_p]
        L.ta_quad_expand.argtypes = [ct.POINTER(ct.c_float), ct.c_float, ct.c_float,
                                     ct.c_int, ct.POINTER(ct.c_float)]
        L.ta_line_add.argtypes = [ct.c_void_p] + [ct.c_float] * 5 + [ct.c_int]
        L.ta_line_update.argtypes = [ct.c_void_p, ct.c_int] + [ct.c_float] * 5 + [ct.c_int]
        L.ta_line_remove.argtypes = [ct.c_void_p, ct.c_int]
        L.ta_line_set_name.argtypes = [ct.c_void_p, ct.c_int, ct.c_char_p]
        L.ta_line_set_rearm.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, ct.c_float]
        L.ta_line_set_zone.argtypes = [ct.c_void_p, ct.c_int, ct.c_float, ct.c_float]
        L.ta_track_set_params.argtypes = [ct.c_void_p] + [ct.c_float]*3 + [ct.c_int]
        L.ta_line_get_name.argtypes = [ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_int]
        L.ta_line_count.argtypes = [ct.c_void_p]
        L.ta_line_list.argtypes = [ct.c_void_p, ct.POINTER(ct.c_int),
                                   ct.POINTER(ct.c_float), ct.POINTER(ct.c_int), ct.c_int]
        L.ta_line_clear.argtypes = [ct.c_void_p]
        L.ta_line_zone.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(ct.c_float)]
        L.ta_track_update.argtypes = [ct.c_void_p, ct.c_longlong,
                                      ct.POINTER(TaDet), ct.c_int, ct.POINTER(TaTrackOut)]
        L.ta_track_expire.argtypes = [ct.c_void_p, ct.c_int]
        L.ta_track_label_feed.argtypes = [ct.c_void_p, ct.c_int, ct.c_char_p,
                                          ct.c_float, ct.c_char_p, ct.c_int]
        L.ta_track_label_get.argtypes = [ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_int]
        L.ta_track_set_label_params.argtypes = [ct.c_void_p, ct.c_int, ct.c_int,
                                                ct.c_float, ct.c_float]
        L.ta_track_get_quad.argtypes = [ct.c_void_p, ct.c_int, ct.c_float * 8]
        L.ta_track_set_smooth.argtypes = [ct.c_void_p, ct.c_float]
        L.ta_set_decode.argtypes = [ct.c_void_p, ct.c_int, ct.c_int]
        L.ta_set_cpu_budget.argtypes = [ct.c_void_p, ct.c_int]
        L.ta_get_cpu_budget.argtypes = [ct.c_void_p]
        L.ta_omp_passive.argtypes = []
        L.ta_text_valid.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int]
        L.ta_selftest.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int]
        L.ta_benchmark.argtypes = [ct.c_void_p, ct.c_int]
        L.ta_benchmark.restype = ct.c_double
        self.h = ct.c_void_p(L.ta_create())
        if not self.h:
            raise RuntimeError("ta_create that bai")

    # ---------------------------------------------------------------- tien ich
    def _ck(self, rc, what):
        if rc != 0:
            raise TinyAnprError(what, rc)
        return rc

    @staticmethod
    def _flt(seq):
        """[(x,y),...] hoac [x,y,x,y,...] -> mang c_float."""
        flat = []
        for p in seq:
            flat.extend(p) if hasattr(p, "__len__") else flat.append(p)
        return (ct.c_float * len(flat))(*[float(v) for v in flat]), len(flat) // 2

    @property
    def version(self):
        return self.lib.ta_version().decode()

    # ---------------------------------------------------------------- license
    def activate(self, license_file, user, app_id=None):
        """app_id: ma DU AN, phai trung the <app> trong license neu the do
        khong rong. De None = dung duong cu (chi hop voi license <app>ANY)."""
        if not self.co_activate_ex:
            if app_id:
                raise TinyAnprError(
                    "activate: ta_anpr.dll cu khong ho tro rang buoc app_id "
                    "(can DLL >= 0.4.0)", -7)
            self._ck(self.lib.ta_activate(self.h, license_file.encode(),
                                          user.encode()), "activate")
            return
        self._ck(self.lib.ta_activate_ex(
            self.h, license_file.encode(), user.encode(),
            app_id.encode() if app_id else None), "activate")

    def trial_start(self, user="trial"):
        """Vao che do DUNG THU (khong license): 2 gio moi 24h, chong reset. Goi
        khi activate nem NO_LICENSE. Nem TinyAnprError(TRIAL_HET) neu het cua so
        hom nay. Model dung thu la goi dong bang license-thu."""
        if not hasattr(self.lib, "ta_trial_start"):
            raise TinyAnprError("trial_start: DLL cu khong ho tro (can >= 0.6.2)", -7)
        self.lib.ta_trial_start.argtypes = [ct.c_void_p, ct.c_char_p]
        self._ck(self.lib.ta_trial_start(self.h, user.encode()), "trial_start")

    def trial_seconds_left(self):
        """So giay con lai trong cua so 24h (0 = het). None neu khong o che do thu."""
        if not hasattr(self.lib, "ta_trial_seconds_left"):
            return None
        self.lib.ta_trial_seconds_left.argtypes = [ct.c_void_p]
        v = self.lib.ta_trial_seconds_left(self.h)
        return None if v < 0 else int(v)

    @property
    def is_trial(self):
        if not hasattr(self.lib, "ta_is_trial"):
            return False
        self.lib.ta_is_trial.argtypes = [ct.c_void_p]
        return bool(self.lib.ta_is_trial(self.h))

    @property
    def days_left(self):
        """So ngay con lai den han license (am = da qua han). -1 neu DLL cu."""
        if not hasattr(self.lib, "ta_license_days_left"):
            return None
        self.lib.ta_license_days_left.argtypes = [ct.c_void_p]
        return int(self.lib.ta_license_days_left(self.h))

    @property
    def simd(self):
        """Muc lenh vec dang dung: AVX2 / AVX / scalar (tu chon theo CPU)."""
        if not hasattr(self.lib, "ta_simd_info"):
            return ""
        self.lib.ta_simd_info.restype = ct.c_char_p
        return self.lib.ta_simd_info().decode()

    @property
    def build_id(self):
        """Ma ban build ("VCAR-20260730") hoac "PUBLIC". Hoi khach chuoi nay
        de biet ho dang cam ban nao ma phat dung license."""
        if not hasattr(self.lib, "ta_build_id"):
            return ""
        self.lib.ta_build_id.restype = ct.c_char_p
        return self.lib.ta_build_id().decode()

    @property
    def machine_id(self):
        """Van tay may nay (16 hex). Gui cho ben cap license de rang buoc.
        Rong neu DLL cu hon 0.4.0."""
        if not self.co_machine_id:
            return ""
        b = ct.create_string_buffer(24)
        n = self.lib.ta_machine_id(b, 24)
        if n <= 0:
            raise TinyAnprError("machine_id", n)
        return b.value.decode()

    @property
    def license_info(self):
        buf = ct.create_string_buffer(256)
        self._ck(self.lib.ta_license_info(self.h, buf, 256), "license_info")
        return buf.value.decode()

    # ------------------------------------------------------- goi model .sdk
    @staticmethod
    def build_pack(out_path, muc, dll_path=None):
        """Dong MOT goi .sdk tu dict {ten: duong_dan}.

        Ma hoa bang khoa san pham cua CHINH ban DLL nay - goi dong bang DLL cua
        doi tac A chi mo duoc bang DLL cua doi tac A. Ten quy uoc:
            reader -> model Stage 2 (.bin)
            stage1 -> checkpoint Stage 1 (.pt)
        """
        lib = ct.CDLL(os.path.abspath(dll_path or _default_dll()))
        lib.ta_pack_build.argtypes = [ct.c_char_p, ct.POINTER(ct.c_char_p),
                                      ct.POINTER(ct.c_char_p), ct.c_int]
        ten = list(muc.keys())
        A = (ct.c_char_p * len(ten))(*[t.encode() for t in ten])
        B = (ct.c_char_p * len(ten))(*[str(muc[t]).encode() for t in ten])
        rc = lib.ta_pack_build(str(out_path).encode(), A, B, len(ten))
        if rc != 0:
            raise TinyAnprError("pack_build", rc)
        return out_path

    def build_pack_ex(self, out_path, muc, meta_json=None):
        """Dong goi v2: ma hoa bang khoa dan xuat tu <mkey> RIENG cua license
        DANG KICH HOAT tren ctx nay. Nghia la goi CHI mo duoc bang dung license
        do - dong cho khach nao phai activate() bang license cua khach do.

        Ky rieng mot buoc (khoa bi mat khong nam trong DLL):
            python tools/ta_sign.py sign --file <out_path>"""
        if not self.co_goi_v2:
            raise TinyAnprError("build_pack_ex: can DLL >= 0.6", -7)
        ten = list(muc.keys())
        A = (ct.c_char_p * len(ten))(*[t.encode() for t in ten])
        B = (ct.c_char_p * len(ten))(*[str(muc[t]).encode() for t in ten])
        self._ck(self.lib.ta_pack_build_ex(
            self.h, str(out_path).encode(), A, B, len(ten),
            meta_json.encode() if meta_json else None), "pack_build_ex")
        return out_path

    def open_pack(self, pack_path):
        self._ck(self.lib.ta_pack_open(self.h, str(pack_path).encode()),
                 "pack_open")

    def pack_meta(self):
        """Sieu du lieu nhung luc dong goi (JSON) - "" neu goi khong co."""
        if not self.co_goi_v2:
            return ""
        b = ct.create_string_buffer(4096)
        n = self.lib.ta_pack_meta(self.h, b, 4096)
        if n < 0:
            raise TinyAnprError("pack_meta", n)
        return b.value.decode("utf-8", "replace")

    def pack_list(self):
        """-> dict {ten: so byte}."""
        b = ct.create_string_buffer(1024)
        n = self.lib.ta_pack_list(self.h, b, 1024)
        if n < 0:
            raise TinyAnprError("pack_list", n)
        s_ = b.value.decode()
        return {} if not s_ else {k: int(v) for k, v in
                                  (x.split("=") for x in s_.split(";"))}

    def pack_read(self, name):
        """-> bytes cua mot muc trong goi (vd 'stage1' de torch.load)."""
        n = self.lib.ta_pack_size(self.h, name.encode())
        if n < 0:
            raise TinyAnprError(f"pack_size({name})", n)
        b = ct.create_string_buffer(n)
        m = self.lib.ta_pack_read(self.h, name.encode(), b, n)
        if m < 0:
            raise TinyAnprError(f"pack_read({name})", m)
        return b.raw[:m]

    # ------------------------------------------------------------------ model
    # ---- vung / quoc gia (v0.5) ----
    def set_region(self, code):
        """Chon vung TRUOC khi load_reader/load_stage1 ("vn", "th"...)."""
        self._ck(self.lib.ta_set_region(self.h, str(code).encode()), "set_region")

    def get_region(self):
        b = ct.create_string_buffer(16)
        self._ck(self.lib.ta_get_region(self.h, b, 16), "get_region")
        return b.value.decode()

    def region_list(self):
        """-> list vung co model trong goi dang mo, vd ["vn", "th"]."""
        b = ct.create_string_buffer(256)
        n = self.lib.ta_region_list(self.h, b, 256)
        if n < 0:
            raise TinyAnprError("region_list", n)
        return [x for x in b.value.decode().split(";") if x]

    def load_reader(self, bin_path):
        self._ck(self.lib.ta_load_reader(self.h, bin_path.encode()), "load_reader")

    @property
    def model_info(self):
        buf = ct.create_string_buffer(256)
        self._ck(self.lib.ta_model_info(self.h, buf, 256), "model_info")
        return buf.value.decode()

    # ---------------------------------------------------------------- Stage 1
    def co_stage1(self):
        """True neu DLL nay co Stage 1 trong C (ban cu chi co Stage 2)."""
        return hasattr(self.lib, "ta_load_stage1")

    def load_stage1(self, path):
        """Nap detector + refine head. path = goi .sdk (muc "det"/"refine")
        hoac duong dan detector .bin."""
        self._ck(self.lib.ta_load_stage1(self.h, str(path).encode()), "load_stage1")

    @property
    def stage1_info(self):
        buf = ct.create_string_buffer(256)
        self._ck(self.lib.ta_stage1_info(self.h, buf, 256), "stage1_info")
        return buf.value.decode()

    def read_plate(self, rgb, quad, shape):
        """Doc MOT bien: anh RGB goc + quad (toa do ANH GOC) -> (text, conf,
        valid). Tu lo cat vung + CLAHE + stem + nan phoi canh ben C, app khong
        can PyTorch. Tra ve ("", 0.0, False) neu SDK khong doc duoc."""
        import numpy as np
        a = np.ascontiguousarray(rgb, dtype=np.uint8)
        h, w = a.shape[:2]
        q = (ct.c_float * 8)(*[float(v) for v in
                               np.asarray(quad, np.float64).reshape(-1)[:8]])
        buf = ct.create_string_buffer(64)
        cf = ct.c_float(0.0)
        vl = ct.c_int(0)
        rc = self.lib.ta_read_plate(self.h, a.ctypes.data_as(ct.POINTER(ct.c_ubyte)),
                                    w, h, q, int(shape), buf, 64,
                                    ct.byref(cf), ct.byref(vl))
        if rc != 0:
            return "", 0.0, False
        return buf.value.decode("ascii", "ignore"), float(cf.value), bool(vl.value)

    def plate_size(self, quad, margin=0.0):
        """(w, h) goc cua bien trong anh theo quad (+ margin moi phia) - de nan
        giu nguyen phan giai nguon."""
        import numpy as np
        q = (ct.c_float * 8)(*[float(v) for v in np.asarray(quad, np.float64).reshape(-1)[:8]])
        w, h = ct.c_int(0), ct.c_int(0)
        self._ck(self.lib.ta_plate_size(q, ct.c_float(margin), ct.byref(w), ct.byref(h)), "plate_size")
        return int(w.value), int(h.value)

    def warp_plate(self, rgb, quad, out_w=0, out_h=0, margin=0.0):
        """Anh bien THANG (RGB uint8 [out_h, out_w, 3]) nan tu ANH GOC theo quad
        cua detect() (da refine) - lay mau truc tiep tren anh dau vao nen giu
        du phan giai, khong qua anh 640 cua mang. out_w/out_h = 0 -> kich thuoc
        goc (1 px ra ~ 1 px vao). margin: le them moi phia (0.04 = 4 %).
        Goi y co dinh: bien dai 520x120, bien vuong 336x240."""
        import numpy as np
        a = np.ascontiguousarray(rgb, dtype=np.uint8)
        h, w = a.shape[:2]
        if out_w <= 0 or out_h <= 0:
            pw, ph = self.plate_size(quad, margin)
            out_w = out_w if out_w > 0 else pw
            out_h = out_h if out_h > 0 else ph
        q = (ct.c_float * 8)(*[float(v) for v in np.asarray(quad, np.float64).reshape(-1)[:8]])
        out = np.empty((out_h, out_w, 3), np.uint8)
        self._ck(self.lib.ta_warp_plate(self.h, a.ctypes.data_as(ct.POINTER(ct.c_ubyte)),
                                        w, h, q, ct.c_float(margin), out_w, out_h,
                                        out.ctypes.data_as(ct.POINTER(ct.c_ubyte))),
                 "warp_plate")
        return out

    def detect(self, rgb, side_crop=-1.0, conf=-1.0, cap=64, max_longest=0):
        """rgb: mang uint8 [H,W,3] LIEN TUC. Tra ve list dict:
        {score, shape, box (x1,y1,x2,y2), quad ndarray [4,2]} - TOA DO ANH GOC.
        side_crop/conf < 0 = lay tu chinh tep model (nen dung: hai so nay doi
        theo tung lan train, de hang so trong app la sai).
        max_longest: TRAN canh dai (0 = tri trong tep model). Model chay KICH
        THUOC DONG nen khung 1080p khong chan se chay o 1280x904."""
        import numpy as np
        a = np.ascontiguousarray(rgb, dtype=np.uint8)
        if a.ndim != 3 or a.shape[2] != 3:
            raise ValueError(f"can anh RGB [H,W,3], nhan {a.shape}")
        h, w = a.shape[:2]
        out = (ct.c_float * (14 * cap))()
        n = self.lib.ta_detect(self.h, a.ctypes.data_as(ct.POINTER(ct.c_ubyte)),
                               w, h, ct.c_float(side_crop), ct.c_float(conf),
                               out, cap, int(max_longest))
        # ta_detect tra ve SO DETECTION (>=0), khong phai ma TA_OK - chi so AM
        # moi la loi. Dung _ck() thang o day thi anh nao co bien cung "loi".
        if n < 0:
            self._ck(n, "detect")
        ra = []
        for i in range(min(n, cap)):
            v = out[i * 14:(i + 1) * 14]
            ra.append({"score": float(v[0]), "shape": int(v[1]),
                       "box": [float(x) for x in v[2:6]],
                       "quad": np.array(v[6:14], np.float32).reshape(4, 2)})
        return ra

    PERF = {"low": 0, "medium": 1, "high": 2, "max": 3}

    def set_performance(self, level):
        """4 cap hieu nang: 'max' (toan bo nhan + khoa RAM model + warm-up 3),
        'high' (12 nhan + khoa RAM + warm-up), 'medium' (6 nhan + warm-up),
        'low' (4 nhan, khoi dong nhe). Luu y may nhieu nhan: 'high' thuong
        NHANH hon 'max' (bai toan nho, dong bo an vao phan tinh)."""
        self._ck(self.lib.ta_set_performance(self.h, self.PERF[str(level).lower()]),
                 "set_performance")

    @property
    def cpu_count(self):
        return self.lib.ta_cpu_count()

    @property
    def threads(self):
        """So luong dang dung thuc te (da phan giai AUTO)."""
        return self.lib.ta_get_threads(self.h)

    @threads.setter
    def threads(self, n):
        """n <= 0 = AUTO (xem auto_threads() ben C: dinh do o ~12 luong)."""
        self._ck(self.lib.ta_set_threads(self.h, int(n)), "set_threads")

    # ------------------------------------------------------------------ zones
    def set_zone_notify(self, zone_id, ms):
        """Chu ky bao lap cua vung, mili giay (0 = tat)."""
        if not getattr(self, "co_zone_notify", False):
            return
        self._ck(self.lib.ta_zone_set_notify(self.h, int(zone_id), int(ms)),
                 "set_zone_notify")

    def zone_notify(self, zone_id):
        """Chu ky bao lap cua vung (ms); 0 = tat, khong co vung -> 0."""
        if not getattr(self, "co_zone_notify", False):
            return 0
        ms = self.lib.ta_zone_notify(self.h, int(zone_id))
        return int(ms) if ms >= 0 else 0

    def set_zone_confirm(self, zone_id, n):
        """So luot doc giong nhau phai co truoc khi chup (1 = chup ngay)."""
        if not getattr(self, "co_zone_notify", False):
            return
        self._ck(self.lib.ta_zone_set_confirm(self.h, int(zone_id), int(n)),
                 "set_zone_confirm")

    def zone_confirm(self, zone_id):
        if not getattr(self, "co_zone_notify", False):
            return 1
        n = self.lib.ta_zone_confirm(self.h, int(zone_id))
        return int(n) if n >= 1 else 1

    def add_zone(self, pts, notify_ms=0, confirm_n=1):
        """notify_ms > 0: bien NAM TRONG vung nay duoc bao lap lai moi ngan
        ay mili giay (che do bai do - khong can cat vach). Dat luon o day de
        chu ky di theo chinh cai box."""
        arr, n = self._flt(pts)
        rc = self.lib.ta_zone_add(self.h, arr, n)
        if rc <= 0:
            raise TinyAnprError("zone_add", rc)
        if notify_ms:
            self.set_zone_notify(rc, notify_ms)
        if confirm_n and confirm_n > 1:
            self.set_zone_confirm(rc, confirm_n)
        return rc

    def add_zone_rect(self, x1, y1, x2, y2, notify_ms=0, confirm_n=1):
        rc = self.lib.ta_zone_add_rect(self.h, x1, y1, x2, y2)
        if rc <= 0:
            raise TinyAnprError("zone_add_rect", rc)
        if notify_ms:
            self.set_zone_notify(rc, notify_ms)
        if confirm_n and confirm_n > 1:
            self.set_zone_confirm(rc, confirm_n)
        return rc

    def update_zone(self, zone_id, pts):
        arr, n = self._flt(pts)
        self._ck(self.lib.ta_zone_update(self.h, zone_id, arr, n), "zone_update")

    def remove_zone(self, zone_id):
        self._ck(self.lib.ta_zone_remove(self.h, zone_id), "zone_remove")

    def zone_count(self):
        return self.lib.ta_zone_count(self.h)

    def clear_zones(self):
        self.lib.ta_zone_clear(self.h)

    def list_zones(self):
        n = self.zone_count()
        if n == 0:
            return []
        ids = (ct.c_int * n)(); npts = (ct.c_int * n)(); pts = (ct.c_float * (n * 32))()
        got = self.lib.ta_zone_list(self.h, ids, npts, pts, n)
        out, off = [], 0
        for i in range(got):
            k = npts[i]
            out.append((ids[i], [(pts[off + 2 * j], pts[off + 2 * j + 1]) for j in range(k)]))
            off += 2 * k
        return out

    # ---- MAU BIEN (v0.8): head chroma chay TRONG C, khong con doan HSV ----
    def co_color(self):
        """Goi co muc "color@<vung>" khong."""
        return bool(self.lib.ta_co_color(self.h))

    def plate_color(self, rgb, quad8):
        """(anh RGB goc, quad 8 float) -> (mau_nen, mau_chu); None neu goi
        khong co head mau. 0 trang 1 vang 2 xanh 3 do 4 luc."""
        import numpy as _np
        a = _np.ascontiguousarray(rgb, dtype=_np.uint8)
        h, w = a.shape[:2]
        q = (ct.c_float * 8)(*[float(x) for x in _np.asarray(quad8).reshape(-1)])
        mn = ct.c_int(-1); mc = ct.c_int(-1)
        rc = self.lib.ta_plate_color(self.h, a.ctypes.data_as(ct.POINTER(ct.c_ubyte)),
                                      w, h, q, ct.byref(mn), ct.byref(mc))
        return None if rc != 0 else (mn.value, mc.value)

    def zone_of(self, quad):
        """>0 = id zone chua tam bien (chay Stage 2); 0 = chua khai bao zone nao;
        -1 = ngoai zone (chi lay bbox/quad de theo doi doi tuong)."""
        arr, _ = self._flt(quad)
        return self.lib.ta_zone_of_quad(self.h, arr)

    def should_read(self, quad):
        return self.zone_of(quad) != -1

    def expand_quad(self, quad, mx=0.04, my=0.10, parallelogram=True):
        """Nan quad thanh hinh binh hanh chuan roi noi rong mx/my (ti le be
        rong/chieu cao) - de VE khung bien cho dep. Tra ve [(x,y)]*4.
        LUU Y: chi dung de HIEN THI; doc chu phai dung quad GOC (reader duoc
        hieu chuan tren quad sat mep, noi rong ra se lam tut do chinh xac)."""
        arr, _ = self._flt(quad)
        out = (ct.c_float * 8)()
        self._ck(self.lib.ta_quad_expand(arr, float(mx), float(my),
                                         1 if parallelogram else 0, out), "quad_expand")
        return [(out[0], out[1]), (out[2], out[3]), (out[4], out[5]), (out[6], out[7])]

    # ------------------------------------------------------- ca khung (v0.6)
    @property
    def max_longest(self):
        return self.lib.ta_get_max_longest(self.h) if self.co_goi_v2 else 0

    @max_longest.setter
    def max_longest(self, px):
        """TRAN canh dai anh dua vao mang cho process_frame. NEN DAT 640:
        khung 1080p khong chan chay o 1280x904 - 57 ms/khung so voi 13 ms."""
        self._ck(self.lib.ta_set_max_longest(self.h, int(px)), "set_max_longest")

    def process_frame(self, rgb, cap=16):
        """CA KHUNG trong mot lenh: detect -> refine -> vung doc -> doc chu.

        Tra ve list dict {box, quad, score, shape, zone_id, text, conf,
        plate_color, text_color}.
        Bien NGOAI vung doc co text rong va zone_id = -1 (app van co quad de
        theo doi doi tuong).

        plate_color: 0 trang 1 vang 2 xanh 3 do 4 luc; -1 = goi KHONG mang muc
        "color@<vung>". Head mau da chay TRONG C tu 2026-08-12 - ghi chu cu o
        day noi "chua co ben C" la SAI, va mac dinh cu con VUT MAT truong nay
        khi tra ve (sua 2026-09-11)."""
        import numpy as np
        if not self.co_goi_v2:
            raise TinyAnprError("process_frame: can DLL >= 0.6", -7)
        a = np.ascontiguousarray(rgb, dtype=np.uint8)
        if a.ndim != 3 or a.shape[2] != 3:
            raise ValueError(f"can anh RGB [H,W,3], nhan {a.shape}")
        h, w = a.shape[:2]
        out = (TaPlate * cap)()
        n = self.lib.ta_process_frame(self.h,
                                      a.ctypes.data_as(ct.POINTER(ct.c_ubyte)),
                                      w, h, out, cap)
        if n < 0:
            self._ck(n, "process_frame")
        ra = []
        for i in range(min(n, cap)):
            p = out[i]
            ra.append({"box": [float(v) for v in p.box],
                       "quad": np.array(p.quad, np.float32).reshape(4, 2),
                       "score": float(p.score), "shape": int(p.shape),
                       "zone_id": int(p.zone_id),
                       "text": p.text.decode("ascii", "ignore"),
                       "conf": float(p.text_conf),
                       "plate_color": int(p.plate_color),
                       "text_color": int(p.text_color)})
        return ra

    # ------------------------------------------------- hau xu ly theo vung
    def plate_fix(self, text, shape):
        """Sua ky tu theo VI TRI cua luat vung (B<->8, O<->0...). CHI sua khi
        chuoi dang KHONG hop le va chi nhan khi sua xong THANH hop le.
        Tra ve (chuoi, da_sua)."""
        if not self.co_plate_fix:
            return text, False
        b = ct.create_string_buffer(64)
        rc = self.lib.ta_plate_fix(self.h, str(text).encode(), int(shape), b, 64)
        if rc < 0:
            raise TinyAnprError("plate_fix", rc)
        return b.value.decode("ascii", "ignore"), rc == 1

    def plate_display(self, line1, line2=None):
        """Chuoi hien thi day du dau: '30A-123.45', '29-X1 123.45'.
        Tra ve "" neu khong khop luat vung nao."""
        if not self.co_plate_fix:
            return ""
        b = ct.create_string_buffer(64)
        rc = self.lib.ta_plate_display(self.h, str(line1).encode(),
                                       (line2 or "").encode(), b, 64)
        return b.value.decode("ascii", "ignore") if rc == 0 else ""

    def display_text(self, text, shape):
        """Nhu plate_display nhung nhan chuoi DA GHEP (thu ma read_plate tra ve).

        Bien vuong: engine tra chuoi gop hai hang nen o day phai thu MOI diem
        cat - dung cach ta_text_valid dang lam. Tra ve "" neu khong khop luat
        nao (bien la / chuoi rac) -> app cu hien chuoi tho."""
        if not text:
            return ""
        if int(shape) == 0:
            return self.plate_display(text)
        for k in range(2, len(text) - 1):
            ra = self.plate_display(text[:k], text[k:])
            if ra:
                return ra
        return ""

    # ------------------------------------------------------ nhat ky + bao mat
    def set_log(self, fn):
        """fn(level, msg): 0 = loi, 1 = canh bao, 2 = thong tin. None = tat.

        Truoc v0.6 loi nap model in thang ra stdout nen app GUI nuot mat.
        LUU Y ctypes: PHAI giu tham chieu Python toi callback (o day la
        self._log_keep) - de bi thu gom thi native goi vao vung da giai phong,
        dung cai bay da dinh o dahua_sdk.py."""
        if not self.co_goi_v2:
            return
        if fn is None:
            self._log_keep = LOG_FN()
        else:
            self._log_keep = LOG_FN(
                lambda lv, msg, _u: fn(int(lv), msg.decode("utf-8", "replace")))
        self.lib.ta_set_log(self._log_keep, None)

    @property
    def security_info(self):
        """"build=... sig=... lic_sig=1 pack=v2 packonly=0 text=ok require_sig=0"

        KIEM TRUOC KHI BAN GIAO: sig=khong nghia la DLL nay KHONG kiem duoc chu
        ky (ban dev) - dung giao cho khach."""
        if not self.co_goi_v2:
            return ""
        b = ct.create_string_buffer(256)
        self._ck(self.lib.ta_security_info(self.h, b, 256), "security_info")
        return b.value.decode()

    def strerror(self, code):
        if not self.co_goi_v2:
            return _ERR.get(code, str(code))
        return self.lib.ta_strerror(int(code)).decode()

    # ------------------------------------------- tracking + line crossing
    COUNT_MODES = {"rearm": 0, "once": 1, "always": 2}

    def set_line_count(self, line_id, mode="rearm", rearm_px=0.0):
        """Chong dem lap khi xe lung chung o vach.
        mode 'rearm' (mac dinh): bao xong thi KHOA, chi mo lai khi xe roi xa
             vach >= rearm_px (0 = lay bang band). Xe nhich qua nhich lai
             quanh vach chi dem MOT lan; lui han ra roi vao lai thi dem tiep.
        mode 'once'  : moi track chi dem 1 lan tren vach nay.
        mode 'always': dem moi lan cat."""
        self._ck(self.lib.ta_line_set_rearm(self.h, line_id,
                                            self.COUNT_MODES[mode], float(rearm_px)),
                 "line_set_rearm")

    def set_line_zone(self, line_id, up_px=0.0, down_px=0.0):
        """Vung boc vach (read-zone) BAT DOI XUNG: up_px ve phia tren, down_px
        ve phia duoi (0 = lay bang band). Vach 'down' nen dat up_px lon de doc
        SOM - cat vach la da co san chuoi."""
        self._ck(self.lib.ta_line_set_zone(self.h, line_id, float(up_px),
                                           float(down_px)), "line_set_zone")

    def set_track_params(self, iou_min=0.0, dist_gate=0.0, predict_k=0.0,
                         expire_ms=0):
        """Tham so ghep track (0 = giu nguyen). Xem ta_anpr.h."""
        self._ck(self.lib.ta_track_set_params(self.h, float(iou_min),
                                              float(dist_gate), float(predict_k),
                                              int(expire_ms)), "track_set_params")

    def add_line(self, p1, p2, band=60.0, direction="both", name="",
                 count_mode="rearm", rearm_px=0.0, zone_up=0.0, zone_down=0.0):
        """Ve mot VACH line-crossing. direction: 'both' | 'down' (top->bottom)
        | 'up' (bottom->top). name = TEN LAN (mot camera phu nhieu lan).
        Tra ve line id (>0). Ve duoc NHIEU vach."""
        dm = {"both": 0, "down": 1, "up": 2}[direction]
        rc = self.lib.ta_line_add(self.h, float(p1[0]), float(p1[1]),
                                  float(p2[0]), float(p2[1]), float(band), dm)
        if rc <= 0:
            raise TinyAnprError("line_add", rc)
        if name:
            self.lib.ta_line_set_name(self.h, rc, name.encode("utf-8"))
        if count_mode != "rearm" or rearm_px:
            self.set_line_count(rc, count_mode, rearm_px)
        if zone_up or zone_down:
            self.set_line_zone(rc, zone_up, zone_down)
        return rc

    def line_name(self, line_id):
        buf = ct.create_string_buffer(64)
        if self.lib.ta_line_get_name(self.h, line_id, buf, 64) != 0:
            return ""
        return buf.value.decode("utf-8", "replace")

    def update_line(self, line_id, p1, p2, band=60.0, direction="both"):
        dm = {"both": 0, "down": 1, "up": 2}[direction]
        self._ck(self.lib.ta_line_update(self.h, line_id, float(p1[0]), float(p1[1]),
                                         float(p2[0]), float(p2[1]), float(band), dm),
                 "line_update")

    def remove_line(self, line_id):
        self._ck(self.lib.ta_line_remove(self.h, line_id), "line_remove")

    def clear_lines(self):
        self.lib.ta_line_clear(self.h)

    def list_lines(self):
        n = self.lib.ta_line_count(self.h)
        if n <= 0:
            return []
        ids = (ct.c_int * n)(); xy = (ct.c_float * (n * 5))(); dm = (ct.c_int * n)()
        got = self.lib.ta_line_list(self.h, ids, xy, dm, n)
        names = {0: "both", 1: "down", 2: "up"}
        return [(ids[i], (xy[i*5], xy[i*5+1]), (xy[i*5+2], xy[i*5+3]),
                 xy[i*5+4], names[dm[i]]) for i in range(got)]

    def line_zone(self, line_id):
        """4 dinh hinh binh hanh boc vach - de ve va/hoac add_zone."""
        out = (ct.c_float * 8)()
        self._ck(self.lib.ta_line_zone(self.h, line_id, out), "line_zone")
        return [(out[0], out[1]), (out[2], out[3]), (out[4], out[5]), (out[6], out[7])]

    def track_update(self, ts_ms, dets):
        """dets: list dict {'box':[x1,y1,x2,y2], 'quad':[...8 float...],
        'score':f, 'shape':0|1}. Tra ve list dict {'track_id','crossed',
        'line_id','direction'} ung voi tung det (+1 = top->bottom)."""
        n = len(dets)
        arr = (TaDet * max(n, 1))()
        for i, d in enumerate(dets):
            arr[i].box = (ct.c_float * 4)(*[float(v) for v in d["box"]])
            q = d["quad"]
            flat = [float(v) for p in q for v in (p if hasattr(p, "__len__") else (p,))]
            arr[i].quad = (ct.c_float * 8)(*flat)
            arr[i].score = float(d.get("score", 0))
            arr[i].shape = int(d.get("shape", 0))
        out = (TaTrackOut * max(n, 1))()
        rc = self.lib.ta_track_update(self.h, int(ts_ms), arr, n, out)
        if rc < 0:
            raise TinyAnprError("track_update", rc)
        return [{"track_id": out[i].track_id, "crossed": bool(out[i].crossed),
                 "line_id": out[i].line_id, "direction": out[i].direction}
                for i in range(n)]

    def set_track_expire(self, ms):
        self._ck(self.lib.ta_track_expire(self.h, int(ms)), "track_expire")

    # ---------------- nhan on dinh + khung muot (v0.3.1) ----------------
    def label_feed(self, track_id, text, conf):
        """Dong 1 phieu doc cho track. Tra ve (nhan_on_dinh, vua_doi).
        Chuoi KHONG hop le dinh dang thi ha trong so truoc khi goi
        (vd conf * 0.3) - van co phieu nhung nhe."""
        buf = ct.create_string_buffer(16)
        rc = self.lib.ta_track_label_feed(
            self.h, int(track_id), (text or "").encode(), float(conf), buf, 16)
        if rc < 0:
            raise TinyAnprError("label_feed", rc)
        return buf.value.decode(errors="replace"), rc == 1

    def label_get(self, track_id):
        buf = ct.create_string_buffer(16)
        rc = self.lib.ta_track_label_get(self.h, int(track_id), buf, 16)
        return buf.value.decode(errors="replace") if rc == 0 else ""

    def set_label_params(self, first_n=0, confirm_n=0, switch_ratio=0.0, decay=0.0):
        """Doi tham so on dinh nhan LUC CHAY (0 = giu nguyen gia tri hien tai)."""
        self._ck(self.lib.ta_track_set_label_params(
            self.h, int(first_n), int(confirm_n), float(switch_ratio), float(decay)),
            "set_label_params")

    def track_quad(self, track_id):
        """Quad DA LAM MUOT cua track (ve overlay khong rung). None neu chua co."""
        q = (ct.c_float * 8)()
        if self.lib.ta_track_get_quad(self.h, int(track_id), q) != 0:
            return None
        return [float(v) for v in q]

    def set_track_smooth(self, alpha):
        """He so muot khung (0..1], 1.0 = tat muot."""
        self._ck(self.lib.ta_track_set_smooth(self.h, float(alpha)), "set_track_smooth")

    @property
    def cpu_budget(self):
        return int(self.lib.ta_get_cpu_budget(self.h))

    @property
    def omp_passive(self):
        """True = OMP_WAIT_POLICY=passive da duoc dat -> cpu_budget co tac dung."""
        return bool(self.lib.ta_omp_passive())

    @cpu_budget.setter
    def cpu_budget(self, percent):
        """Gioi han % thoi gian CPU ban cua NGU CANH NAY (1..100, 100 = tat ham).

        Khac han gioi han SO LUONG luong: 4 luong chay het cong suat van an
        tron 4 nhan. Day la duty cycle - SDK ngu bu sau moi luot doc de UI con
        nhan. Danh doi: do tre moi luot doc tang ~(100/percent) lan."""
        self._ck(self.lib.ta_set_cpu_budget(self.h, int(percent)), "set_cpu_budget")

    def set_decode(self, use_beam=-1, min_chars=-1):
        """use_beam: beam search khi greedy ra chuoi khong hop le dinh dang.
        min_chars: chuoi ngan hon LUON bi coi la khong hop le. -1 = giu nguyen."""
        self._ck(self.lib.ta_set_decode(self.h, int(use_beam), int(min_chars)),
                 "set_decode")

    def text_valid(self, text, shape):
        """Kiem MOT chuoi da ghep (bien vuong tu thu moi diem cat hai hang)."""
        return bool(self.lib.ta_text_valid(self.h, (text or "").encode(), int(shape)))

    # --------------------------------------------------------------- suy luan
    def read_canon(self, canon_hwc, shape):
        """canon_hwc: numpy [h, w, in_ch] float64 (dau ra rectify cua reader).
        Tra ve (text, conf, valid) - valid = kiem LUAT BIEN VN ngay trong SDK
        (v0.2; bien vuong kiem RIENG tung hang truoc khi ghep)."""
        import numpy as np
        a = np.ascontiguousarray(canon_hwc, dtype=np.float64)
        h, w = a.shape[0], a.shape[1]
        buf = ct.create_string_buffer(32)
        conf = ct.c_float(0); fv = ct.c_int(0)
        self._ck(self.lib.ta_read_canon(
            self.h, a.ctypes.data_as(ct.POINTER(ct.c_double)), h, w, int(shape),
            buf, 32, ct.byref(conf), ct.byref(fv)), "read_canon")
        return buf.value.decode(), float(conf.value), bool(fv.value)

    def read_golden(self, shape=0):
        buf = ct.create_string_buffer(32)
        conf = ct.c_float(0); fv = ct.c_int(0)
        self._ck(self.lib.ta_read_golden(self.h, int(shape), buf, 32,
                                         ct.byref(conf), ct.byref(fv)), "read_golden")
        return buf.value.decode(), float(conf.value), bool(fv.value)

    def format_valid(self, line1, line2=None):
        """Kiem luat bien VN doc lap (cung bo luat data/plate_format.py)."""
        return bool(self.lib.ta_format_valid(
            line1.encode(), line2.encode() if line2 else None))

    def selftest(self):
        buf = ct.create_string_buffer(256)
        rc = self.lib.ta_selftest(self.h, buf, 256)
        if rc != 0:
            raise TinyAnprError("selftest: " + buf.value.decode(), rc)
        return buf.value.decode()

    def benchmark_ms(self, iters=200):
        return self.lib.ta_benchmark(self.h, int(iters))

    def close(self):
        if getattr(self, "h", None):
            self.lib.ta_destroy(self.h)
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
