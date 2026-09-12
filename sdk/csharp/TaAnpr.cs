// TaAnpr.cs - binding C# cho tinyANPR_SDK.dll (Tiny ANPR SDK v0.6).
//
// Dung trong app WPF/WinForms (vd Example/wpfRtspCam/RTSPCam): copy file nay
// vao project + dat tinyANPR_SDK.dll canh exe (hoac dat DllImport tro toi duong dan
// khac). Kem IDisposable nen dung duoc voi `using`.
//
// CACH DUNG GON NHAT (v0.6 - ca tuyen chay trong C, KHONG can PyTorch):
//
//   Environment.SetEnvironmentVariable("OMP_WAIT_POLICY", "passive"); // truoc P/Invoke dau
//   using var anpr = new TinyAnpr();
//   anpr.SetLog((lv, m) => Log.Write(m));            // bat loi nap model
//   anpr.Activate(@"license.lic", "hiennt@autotron.vn");
//   anpr.SetRegion("vn");                            // TRUOC khi nap model
//   anpr.LoadStage1(@"models\tinyanpr.sdk");
//   anpr.LoadReader(@"models\tinyanpr.sdk");
//   anpr.MaxLongest = 640;                           // 1080p: 57ms -> 13ms
//   int laneId = anpr.AddZone(new[]{100f,300f, 900f,300f, 950f,700f, 50f,700f});
//
//   var plates = new TaPlate[16];
//   int n = anpr.ProcessFrame(rgbBytes, w, h, plates);   // ca khung mot lenh
//   for (int i = 0; i < Math.Min(n, plates.Length); ++i)
//       if (plates[i].ZoneId != -1) Console.WriteLine(plates[i].Text);
//
// KIEM TRUOC KHI BAN GIAO: anpr.SecurityInfo phai co "sig=vendor-..." va
// "text=ok". "sig=khong" nghia la DLL khong kiem duoc chu ky (ban DEV).

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace TinyAnprSdk
{
    public enum TaStatus
    {
        Ok = 0, BadArg = -1, NoLicense = -2, WrongUser = -3, Expired = -4,
        BadModel = -5, SelfTestFailed = -6, NotReady = -7, NoSpace = -8,
        WrongMachine = -9, WrongApp = -10, Clock = -11,
        /// <summary>Tep da bi sua doi - chu ky Ed25519 khong khop.</summary>
        Tamper = -12
    }

    /// <summary>Muc do nhat ky tra ve qua SetLog.</summary>
    public enum TaLogLevel { Error = 0, Warn = 1, Info = 2 }

    /// <summary>Callback nhat ky. CO THE duoc goi tu NHIEU LUONG.</summary>
    public delegate void TaLogHandler(TaLogLevel level, string message);

    public class TinyAnprException : Exception
    {
        public TaStatus Status { get; }
        public TinyAnprException(string what, TaStatus st)
            : base($"{what}: {st}") { Status = st; }
    }

    /// <summary>Detection Stage-1 dua vao tracker (toa do ANH GOC).</summary>
    [StructLayout(LayoutKind.Sequential)]
    public struct TaDet
    {
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)] public float[] Box;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 8)] public float[] Quad;
        public float Score;
        public int Shape;
    }

    /// <summary>Mot detection Stage 1 tra ve tu Detect() - toa do ANH GOC.</summary>
    public class TaDetection
    {
        public float Score;
        public int Shape;            // 0 = bien dai, 1 = bien vuong
        public float[] Box = new float[4];   // x1,y1,x2,y2
        public float[] Quad = new float[8];  // TL,TR,BR,BL (da qua refine)
    }

    /// <summary>Ket qua tracking cho tung detection sau TrackUpdate.</summary>
    [StructLayout(LayoutKind.Sequential)]
    public struct TaTrackOut
    {
        public int TrackId;    // id ben vung qua cac khung
        public int Crossed;    // 1 = vua cat vach -> phat notify voi Stage 2
        public int LineId;
        public int Direction;  // +1 top->bottom, -1 bottom->top
    }

    /// <summary>Mot bien so tra ve tu ta_process_frame (v1).</summary>
    [StructLayout(LayoutKind.Sequential)]
    public struct TaPlate
    {
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)] public float[] Box;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 8)] public float[] Quad;
        public float Score;
        public int Shape;          // 0 = bien dai, 1 = bien vuong
        public int ZoneId;         // >0 trong zone; 0 chua co zone; -1 ngoai zone
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 16)] public string Text;
        public float TextConf;
        public int PlateColor;     // 0 trang 1 vang 2 xanhduong 3 do 4 xanhla
        public int TextColor;      // 0 den 1 trang 2 khac
    }

    public sealed class TinyAnpr : IDisposable
    {
        const string DLL = "tinyANPR_SDK";

        // ---- CHON DLL THEO CPU (2026-09-11) --------------------------------
        // tinyANPR_SDK.dll bien dich voi /arch:AVX2. May KHONG co AVX2 thi NAP
        // DLL LA CHET NGAY voi 0xc000001d (STATUS_ILLEGAL_INSTRUCTION) - ma loi
        // do khong noi gi ve nguyen nhan, rat de tuong la hong tep hay thieu
        // thu vien. Gap that 2026-09-11 tren mot may Ivy Bridge (Family 6 Model
        // 62, doi 2013): app tat ngay khi mo, khong hien gi.
        //
        // P/Invoke gan ten DLL luc bien dich nen khong tu doi duoc; phai dang ky
        // resolver. Ban du phong tinyANPR_SDK_noavx2.dll cho ket qua BIT-EXACT
        // (do 122 bien: 0 lech chuoi, quad lech 0.0000 px) nhung CHAM gap ~4 lan.
        // Ca hai deu can vcomp140.dll nam canh exe.
        //
        // AVX2 co tu Intel Haswell (2013) va AMD Excavator (2015).
        // PF_AVX2_INSTRUCTIONS_AVAILABLE = 40 (winnt.h).
        const int PF_AVX2 = 40;

        [DllImport("kernel32.dll")]
        static extern bool IsProcessorFeaturePresent(int feature);

        /// <summary>CPU nay co AVX2 khong. Khong hoi duoc -> true (giu duong cu).</summary>
        public static bool CoAvx2()
        {
            try { return IsProcessorFeaturePresent(PF_AVX2); }
            catch { return true; }
        }

        /// <summary>Ten DLL se duoc nap thuc te - de app ghi log / chan doan.</summary>
        // GO BAN DU PHONG noavx2 (2026-09-12): sau khi dung LAI dung co, hai tep
        // co .text GIONG HET NHAU - SDK chinh von KHONG dung /arch:AVX2, no chon
        // duong bang CPUID luc chay va tu 2026-09-12 mac dinh la SSE. Nghia la ban
        // 'du phong' chi la bua ho menh: neu ban chinh chet tren may cu thi no cung
        // chet y het. Giu hai tep chi tao them mot thu de lac hau - da tra gia dung
        // the: no build TAY, thieu co toi uu (cham 9.4 lan) va khong duoc dung lai
        // sau khi sua loi buoc nhay Cpad -> may khach doc ra rac ca thang.
        public static string TenDllDangDung => "tinyANPR_SDK.dll";

        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern IntPtr ta_create();
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern void ta_destroy(IntPtr c);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern IntPtr ta_version();
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_activate(IntPtr c, string lic, string user);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_license_info(IntPtr c, StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_load_reader(IntPtr c, string path);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_model_info(IntPtr c, StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_set_threads(IntPtr c, int n);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_set_performance(IntPtr c, int level);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_zone_add(IntPtr c, float[] pts, int n);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_zone_add_rect(IntPtr c, float x1, float y1, float x2, float y2);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_co_color(IntPtr c);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_plate_color(IntPtr c, byte[] rgb, int w, int h, float[] quad8,
                                         out int outPlate, out int outText);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_zone_update(IntPtr c, int id, float[] pts, int n);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_zone_remove(IntPtr c, int id);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_zone_count(IntPtr c);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_zone_list(IntPtr c, int[] ids, int[] npts, float[] pts, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern void ta_zone_clear(IntPtr c);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_zone_of_quad(IntPtr c, float[] quad8);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_read_canon(IntPtr c, double[] canon, int h, int w, int shape,
                                        StringBuilder text, int cap, out float conf, out int valid);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_read_golden(IntPtr c, int shape, StringBuilder text, int cap, out float conf, out int valid);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_format_valid(string line1, string line2);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_quad_expand(float[] quad8, float mx, float my, int parallelogram, float[] out8);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_line_add(IntPtr c, float x1, float y1, float x2, float y2, float band, int dirMode);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_line_update(IntPtr c, int id, float x1, float y1, float x2, float y2, float band, int dirMode);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_line_remove(IntPtr c, int id);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_line_set_name(IntPtr c, int id, string name);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_line_get_name(IntPtr c, int id, StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_line_set_rearm(IntPtr c, int id, int countMode, float rearmPx);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_line_set_zone(IntPtr c, int id, float upPx, float downPx);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_track_set_params(IntPtr c, float iouMin, float distGate, float predictK, int expireMs);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_line_count(IntPtr c);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern void ta_line_clear(IntPtr c);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_line_zone(IntPtr c, int lineId, float[] poly8);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_track_update(IntPtr c, long tsMs, TaDet[] dets, int n, [Out] TaTrackOut[] outs);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern int ta_track_expire(IntPtr c, int ms);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_track_label_feed(IntPtr c, int trackId, string text, float conf,
                                              StringBuilder outBuf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_track_label_get(IntPtr c, int trackId, StringBuilder outBuf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_track_set_label_params(IntPtr c, int firstN, int confirmN,
                                                    float switchRatio, float decay);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_track_get_quad(IntPtr c, int trackId, [Out] float[] quad8);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_track_set_smooth(IntPtr c, float alpha);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_set_decode(IntPtr c, int useBeam, int minChars);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_text_valid(IntPtr c, string text, int shape);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_set_cpu_budget(IntPtr c, int percent);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_get_cpu_budget(IntPtr c);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_omp_passive();

        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern void ta_set_simd(int muc);

        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_get_simd();
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_selftest(IntPtr c, StringBuilder rep, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)] static extern double ta_benchmark(IntPtr c, int iters);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_process_frame(IntPtr c, byte[] rgb, int w, int h,
                                           [Out] TaPlate[] outp, int max);

        // ---- v0.4/v0.5/v0.6: license nang cao, Stage 1 C, goi, vung, bao mat ----
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_activate_ex(IntPtr c, string lic, string user, string appId);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_machine_id(StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern IntPtr ta_build_id();
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern IntPtr ta_simd_info();
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern IntPtr ta_strerror(int code);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_license_days_left(IntPtr c);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_security_info(IntPtr c, StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern void ta_set_log(TaLogNative? fn, IntPtr user);

        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_load_stage1(IntPtr c, string path);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_stage1_info(IntPtr c, StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_detect(IntPtr c, byte[] rgb, int w, int h,
                                    float sideCrop, float conf,
                                    [Out] float[] outp, int capDets, int maxLongest);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_read_plate(IntPtr c, byte[] rgb, int w, int h,
                                        float[] quad8, int shape,
                                        StringBuilder text, int cap,
                                        out float conf, out int formatValid);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_set_max_longest(IntPtr c, int px);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_warp_plate(IntPtr c, byte[] rgb, int w, int h,
                                        float[] quad8, float margin,
                                        int outW, int outH, [Out] byte[] outRgb);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_plate_size(float[] quad8, float margin, out int outW, out int outH);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_get_max_longest(IntPtr c);

        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_pack_open(IntPtr c, string path);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_pack_size(IntPtr c, string name);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_pack_read(IntPtr c, string name, [Out] byte[] buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_pack_list(IntPtr c, StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_pack_meta(IntPtr c, StringBuilder buf, int cap);

        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_set_region(IntPtr c, string code);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_get_region(IntPtr c, StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_region_list(IntPtr c, StringBuilder buf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_plate_fix(IntPtr c, string text, int shape,
                                       StringBuilder outBuf, int cap);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        static extern int ta_plate_display(IntPtr c, string l1, string l2,
                                           StringBuilder outBuf, int cap);

        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_zone_set_notify(IntPtr c, int id, int ms);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_zone_notify(IntPtr c, int id);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_zone_set_confirm(IntPtr c, int id, int n);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_zone_confirm(IntPtr c, int id);
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_cpu_count();
        [DllImport(DLL, CallingConvention = CallingConvention.Cdecl)]
        static extern int ta_get_threads(IntPtr c);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        delegate void TaLogNative(int level, IntPtr msg, IntPtr user);

        IntPtr _h;
        // PHAI giu tham chieu managed toi delegate: GC khong biet native dang
        // cam con tro toi no. Thu gom mat -> lan log sau goi vao vung da giai
        // phong (dung cai bay da dinh o examples/live_camera/dahua_sdk.py).
        TaLogNative? _logKeep;
        TaLogHandler? _logUser;

        public TinyAnpr()
        {
            _h = ta_create();
            if (_h == IntPtr.Zero) throw new InvalidOperationException("ta_create that bai");
        }

        public static string Version => Marshal.PtrToStringAnsi(ta_version()) ?? "?";

        static void Check(int rc, string what)
        {
            if (rc != 0) throw new TinyAnprException(what, (TaStatus)rc);
        }

        /// <summary>Mo ta ma loi bang tieng Viet khong dau (tu DLL).</summary>
        public static string StrError(int code)
            => Marshal.PtrToStringAnsi(ta_strerror(code)) ?? code.ToString();

        /// <summary>Muc lenh vec dang dung: AVX2 / AVX / scalar (tu chon theo CPU).</summary>
        public static string SimdInfo => Marshal.PtrToStringAnsi(ta_simd_info()) ?? "?";

        /// <summary>Ma ban build ("VCAR-20260806") hoac "PUBLIC". Hoi khach chuoi
        /// nay de biet ho dang cam ban nao ma phat dung license.</summary>
        public static string BuildId => Marshal.PtrToStringAnsi(ta_build_id()) ?? "?";

        /// <summary>Van tay MAY nay (16 hex) - gui cho ben cap license de rang buoc.</summary>
        public static string MachineId
        {
            get { var sb = new StringBuilder(24); return ta_machine_id(sb, sb.Capacity) > 0 ? sb.ToString() : ""; }
        }

        /// <summary>Huong loi/canh bao cua SDK ve log cua app. Nen goi NGAY sau
        /// khoi tao: khong co no thi loi nap model chi ra stderr, ma app GUI
        /// nuot mat - khong con gi de chan doan tu xa.</summary>
        public void SetLog(TaLogHandler? handler)
        {
            _logUser = handler;
            if (handler == null) { _logKeep = null; ta_set_log(null, IntPtr.Zero); return; }
            _logKeep = (lv, msg, _) =>
                _logUser?.Invoke((TaLogLevel)lv, Marshal.PtrToStringAnsi(msg) ?? "");
            ta_set_log(_logKeep, IntPtr.Zero);
        }

        /// <summary>Kich hoat license theo USER. Bat buoc truoc moi thao tac khac.</summary>
        public void Activate(string licenseFile, string user)
            => Check(ta_activate(_h, licenseFile, user), "activate");

        /// <summary>Nhu Activate nhung kiem THEM &lt;app&gt; trong license phai trung
        /// appId - de license bi chep sang app khac thi khong dung duoc.</summary>
        public void Activate(string licenseFile, string user, string appId)
            => Check(ta_activate_ex(_h, licenseFile, user, appId), "activate_ex");

        public string LicenseInfo
        {
            get { var sb = new StringBuilder(256); Check(ta_license_info(_h, sb, sb.Capacity), "license_info"); return sb.ToString(); }
        }

        /// <summary>So ngay con lai den han (am = qua han). App NEN canh bao khi
        /// con duoi ~30 ngay: het han giua ca truc ma khong bao truoc la mat viec.</summary>
        public int LicenseDaysLeft => ta_license_days_left(_h);

        /// <summary>Trang thai cac lop bao ve cua ban DLL dang cam. KIEM TRUOC KHI
        /// BAN GIAO: phai co "sig=vendor-..." va "text=ok"; "sig=khong" la ban DEV
        /// (khong kiem duoc chu ky) - dung giao cho khach.</summary>
        public string SecurityInfo
        {
            get { var sb = new StringBuilder(256); Check(ta_security_info(_h, sb, sb.Capacity), "security_info"); return sb.ToString(); }
        }

        public void LoadReader(string binPath) => Check(ta_load_reader(_h, binPath), "load_reader");

        // ------------------------------ Stage 1 (C) --------------------------
        /// <summary>Nap detector + refine head. path = goi .sdk hoac detector .bin.</summary>
        public void LoadStage1(string path) => Check(ta_load_stage1(_h, path), "load_stage1");

        public string Stage1Info
        {
            get { var sb = new StringBuilder(256); Check(ta_stage1_info(_h, sb, sb.Capacity), "stage1_info"); return sb.ToString(); }
        }

        /// <summary>TRAN canh dai anh dua vao mang. NEN DAT 640: khung 1080p khong
        /// chan chay o 1280x904 - 57 ms/khung so voi 13 ms, ma khau doc khong loi gi.</summary>
        public int MaxLongest
        {
            get => ta_get_max_longest(_h);
            set => Check(ta_set_max_longest(_h, value), "set_max_longest");
        }

        /// <summary>Phat hien bien + 4 goc. rgb = [h*w*3] RGB LIEN TUC.
        /// sideCrop/conf am = lay tu chinh tep model (nen dung: hai so nay doi
        /// theo tung lan train, de hang so trong app la sai).</summary>
        public List<TaDetection> Detect(byte[] rgb, int w, int h, int capDets = 32,
                                        float sideCrop = -1f, float conf = -1f,
                                        int maxLongest = 0)
        {
            var buf = new float[14 * capDets];
            int n = ta_detect(_h, rgb, w, h, sideCrop, conf, buf, capDets, maxLongest);
            if (n < 0) throw new TinyAnprException("detect", (TaStatus)n);
            var res = new List<TaDetection>();
            for (int i = 0; i < Math.Min(n, capDets); ++i)
            {
                var q = new float[8];
                Array.Copy(buf, i * 14 + 6, q, 0, 8);
                res.Add(new TaDetection
                {
                    Score = buf[i * 14], Shape = (int)buf[i * 14 + 1],
                    Box = new[] { buf[i * 14 + 2], buf[i * 14 + 3],
                                  buf[i * 14 + 4], buf[i * 14 + 5] },
                    Quad = q
                });
            }
            return res;
        }

        /// <summary>Stage 2 tron goi: anh RGB goc + quad -> doc chu. App KHONG
        /// can PyTorch cho bat ky khau nao.</summary>
        public (string Text, float Conf, bool Valid) ReadPlate(byte[] rgb, int w, int h,
                                                               float[] quad8, int shape)
        {
            var sb = new StringBuilder(32);
            int rc = ta_read_plate(_h, rgb, w, h, quad8, shape, sb, sb.Capacity,
                                   out float conf, out int v);
            if (rc != 0) return ("", 0f, false);
            return (sb.ToString(), conf, v != 0);
        }

        /// <summary>Kich thuoc goc (px) cua bien trong anh theo quad + margin
        /// (rong = TB 2 canh ngang, cao = TB 2 canh doc).</summary>
        public static (int W, int H) PlateSize(float[] quad8, float margin = 0f)
        {
            int rc = ta_plate_size(quad8, margin, out int w, out int h);
            if (rc != 0) throw new TinyAnprException("plate_size", (TaStatus)rc);
            return (w, h);
        }

        /// <summary>Anh bien THANG (RGB, outW*outH*3 byte) nan tu ANH GOC theo quad
        /// cua Detect (da refine): lay mau truc tiep tren anh dau vao nen giu du
        /// phan giai nguon, KHONG qua anh 640 cua mang. outW/outH = 0 -> kich thuoc
        /// goc (PlateSize). margin: le them moi phia (0.04f = 4 %). Goi y co dinh:
        /// bien dai 520x120, bien vuong 336x240. Khong can model, chi can license.</summary>
        public byte[] WarpPlate(byte[] rgb, int w, int h, float[] quad8,
                                float margin = 0f, int outW = 0, int outH = 0)
        {
            if (outW <= 0 || outH <= 0)
            {
                var (pw, ph) = PlateSize(quad8, margin);
                if (outW <= 0) outW = pw;
                if (outH <= 0) outH = ph;
            }
            var outRgb = new byte[outW * outH * 3];
            Check(ta_warp_plate(_h, rgb, w, h, quad8, margin, outW, outH, outRgb), "warp_plate");
            return outRgb;
        }

        // ------------------------------ goi .sdk -----------------------------
        public void OpenPack(string packPath) => Check(ta_pack_open(_h, packPath), "pack_open");

        /// <summary>-&gt; {ten muc: so byte}.</summary>
        public Dictionary<string, int> PackList()
        {
            var sb = new StringBuilder(1024);
            int n = ta_pack_list(_h, sb, sb.Capacity);
            if (n < 0) throw new TinyAnprException("pack_list", (TaStatus)n);
            var res = new Dictionary<string, int>();
            foreach (var it in sb.ToString().Split(';'))
            {
                if (it.Length == 0) continue;
                var kv = it.Split('=');
                if (kv.Length == 2 && int.TryParse(kv[1], out int v)) res[kv[0]] = v;
            }
            return res;
        }

        public byte[] PackRead(string name)
        {
            int n = ta_pack_size(_h, name);
            if (n < 0) throw new TinyAnprException("pack_size", (TaStatus)n);
            var buf = new byte[n];
            int m = ta_pack_read(_h, name, buf, n);
            if (m < 0) throw new TinyAnprException("pack_read", (TaStatus)m);
            return buf;
        }

        /// <summary>Sieu du lieu nhung luc dong goi (JSON) - "" neu goi khong co.</summary>
        public string PackMeta()
        {
            var sb = new StringBuilder(4096);
            int n = ta_pack_meta(_h, sb, sb.Capacity);
            return n < 0 ? "" : sb.ToString();
        }

        // ---------------------------- vung / quoc gia ------------------------
        /// <summary>Chon vung TRUOC khi LoadStage1/LoadReader ("vn", "th"...).
        /// Quyet dinh ca muc model lay tu goi lan bo luat bien cua nuoc do.</summary>
        public void SetRegion(string code) => Check(ta_set_region(_h, code), "set_region");

        public string GetRegion()
        {
            var sb = new StringBuilder(16);
            Check(ta_get_region(_h, sb, sb.Capacity), "get_region");
            return sb.ToString();
        }

        /// <summary>Cac vung CO MODEL trong goi dang mo.</summary>
        public string[] RegionList()
        {
            var sb = new StringBuilder(256);
            int n = ta_region_list(_h, sb, sb.Capacity);
            if (n < 0) return new string[0];
            return sb.ToString().Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries);
        }

        /// <summary>Sua ky tu theo VI TRI cua luat vung (B&lt;-&gt;8, O&lt;-&gt;0...).
        /// CHI sua khi chuoi dang KHONG hop le va chi nhan khi sua xong THANH
        /// hop le - khong bao gio dung vao chuoi da dung.</summary>
        public string PlateFix(string text, int shape, out bool changed)
        {
            var sb = new StringBuilder(64);
            int rc = ta_plate_fix(_h, text ?? "", shape, sb, sb.Capacity);
            if (rc < 0) throw new TinyAnprException("plate_fix", (TaStatus)rc);
            changed = rc == 1;
            return sb.ToString();
        }

        /// <summary>Chuoi hien thi day du dau: "30A-123.45", "29-X1 123.45".
        /// "" neu khong khop luat vung nao.</summary>
        public string PlateDisplay(string line1, string? line2 = null)
        {
            var sb = new StringBuilder(64);
            return ta_plate_display(_h, line1, line2 ?? "", sb, sb.Capacity) == 0
                   ? sb.ToString() : "";
        }

        public static int CpuCount => ta_cpu_count();
        /// <summary>So luong dang dung thuc te (sau khi phan giai AUTO).</summary>
        public int ThreadsInUse => ta_get_threads(_h);

        public string ModelInfo
        {
            get { var sb = new StringBuilder(256); Check(ta_model_info(_h, sb, sb.Capacity), "model_info"); return sb.ToString(); }
        }

        public int Threads { set => Check(ta_set_threads(_h, value), "set_threads"); }
        /// <summary>0 Low (4 nhan) | 1 Medium (6) | 2 High (12 + khoa RAM model
        /// + warm-up) | 3 Max (toan bo nhan). May nhieu nhan: High thuong nhanh hon Max.</summary>
        public void SetPerformance(int level) => Check(ta_set_performance(_h, level), "set_performance");

        // ------------------------------- zones -------------------------------
        /// <summary>pts = [x0,y0,x1,y1,...] toa do ANH GOC. Tra ve zone id (>0).</summary>
        public int AddZone(float[] pts)
        {
            int id = ta_zone_add(_h, pts, pts.Length / 2);
            if (id <= 0) throw new TinyAnprException("zone_add", (TaStatus)id);
            return id;
        }
        public int AddZoneRect(float x1, float y1, float x2, float y2)
        {
            int id = ta_zone_add_rect(_h, x1, y1, x2, y2);
            if (id <= 0) throw new TinyAnprException("zone_add_rect", (TaStatus)id);
            return id;
        }
        /// <summary>Sua hinh dang zone, GIU NGUYEN id.</summary>
        public void UpdateZone(int id, float[] pts)
            => Check(ta_zone_update(_h, id, pts, pts.Length / 2), "zone_update");
        public void RemoveZone(int id) => Check(ta_zone_remove(_h, id), "zone_remove");

        /// <summary>CHU KY BAO LAP cua vung, mili giay (0 = tat). Che do BAI DO:
        /// xe do trong vung thi cu ngan nay lai bao mot lan, khong can cat vach.</summary>
        public void SetZoneNotify(int id, int ms)
            => Check(ta_zone_set_notify(_h, id, ms), "zone_set_notify");
        public int ZoneNotify(int id) => ta_zone_notify(_h, id);
        /// <summary>So luot doc GIONG NHAU can co truoc khi chup (1 = chup ngay).
        /// Chong nhay so: doc lech mot ky tu ma chup luon thi ban ghi sai.</summary>
        public void SetZoneConfirm(int id, int n)
            => Check(ta_zone_set_confirm(_h, id, n), "zone_set_confirm");
        public int ZoneConfirm(int id) => ta_zone_confirm(_h, id);
        public int ZoneCount => ta_zone_count(_h);
        public void ClearZones() => ta_zone_clear(_h);

        public List<(int Id, float[] Points)> ListZones()
        {
            int n = ZoneCount;
            var res = new List<(int, float[])>();
            if (n == 0) return res;
            var ids = new int[n]; var np = new int[n]; var pts = new float[n * 32];
            int got = ta_zone_list(_h, ids, np, pts, n);
            int off = 0;
            for (int i = 0; i < got; ++i)
            {
                var p = new float[np[i] * 2];
                Array.Copy(pts, off, p, 0, p.Length);
                off += p.Length;
                res.Add((ids[i], p));
            }
            return res;
        }

        /// <summary>&gt;0 = id zone chua tam bien (chay Stage 2); 0 = chua khai bao zone
        /// nao (doc tat); -1 = ngoai zone (chi lay bbox/quad de theo doi).</summary>
        public int ZoneOf(float[] quad8) => ta_zone_of_quad(_h, quad8);

        /// <summary>Bien nay co duoc doc (Stage 2) khong.</summary>
        public bool ShouldRead(float[] quad8) => ZoneOf(quad8) != -1;

        // ------------------------------ mau bien ------------------------------
        /// <summary>Goi co HEAD MAU khong (muc "color@vung"). false = PlateColor
        /// se luon la -1, app phai tu lo lay mau.</summary>
        public bool CoMauBien => ta_co_color(_h) != 0;

        /// <summary>Doan mau NEN bien va mau CHU tu (anh RGB goc, quad).
        ///
        /// Chay head chroma TRONG C - khong con phai doan HSV ben app. Tra ve
        /// null neu goi khong co head mau.
        ///   nen: 0 trang 1 vang 2 xanhduong 3 do 4 xanhla
        ///   chu: 0 den 1 trang 2 khac
        /// Chi phi ~0.1 ms/bien (lay mau 48x16 diem, khong chay CNN).</summary>
        public (int Nen, int Chu)? MauBien(byte[] rgb, int w, int h, float[] quad8)
        {
            if (ta_plate_color(_h, rgb, w, h, quad8, out int nen, out int chu) != 0)
                return null;
            return (nen, chu);
        }

        // ------------------------------ suy luan -----------------------------
        public (string Text, float Conf, bool Valid) ReadCanon(double[] canonHwc, int h, int w, int shape)
        {
            var sb = new StringBuilder(32);
            Check(ta_read_canon(_h, canonHwc, h, w, shape, sb, sb.Capacity, out float conf, out int v), "read_canon");
            return (sb.ToString(), conf, v != 0);
        }

        public (string Text, float Conf, bool Valid) ReadGolden(int shape)
        {
            var sb = new StringBuilder(32);
            Check(ta_read_golden(_h, shape, sb, sb.Capacity, out float conf, out int v), "read_golden");
            return (sb.ToString(), conf, v != 0);
        }

        /// <summary>Kiem luat bien VN doc lap (line2 = null voi bien 1 hang).</summary>
        public static bool FormatValid(string line1, string? line2 = null)
            => ta_format_valid(line1, line2 ?? "") != 0;

        /// <summary>Nan quad thanh hinh binh hanh chuan roi noi rong - CHI de VE
        /// (doc chu phai dung quad goc). mx/my = ti le be rong/chieu cao.</summary>
        public static float[] ExpandQuad(float[] quad8, float mx = 0.04f, float my = 0.10f,
                                         bool parallelogram = true)
        {
            var o = new float[8];
            ta_quad_expand(quad8, mx, my, parallelogram ? 1 : 0, o);
            return o;
        }

        // -------------------- tracking + line crossing (v0.3) --------------------
        /// <summary>Ve vach line-crossing. direction: 0 ca hai, 1 top-&gt;bottom,
        /// 2 bottom-&gt;top. band = nua be rong hinh binh hanh boc vach.
        /// Ve duoc NHIEU vach - nhu nhieu zone.</summary>
        public int AddLine(float x1, float y1, float x2, float y2, float band = 60, int direction = 0)
        {
            int id = ta_line_add(_h, x1, y1, x2, y2, band, direction);
            if (id <= 0) throw new TinyAnprException("line_add", (TaStatus)id);
            return id;
        }
        public void UpdateLine(int id, float x1, float y1, float x2, float y2, float band, int direction)
            => Check(ta_line_update(_h, id, x1, y1, x2, y2, band, direction), "line_update");
        public void RemoveLine(int id) => Check(ta_line_remove(_h, id), "line_remove");
        /// <summary>Ten lan cho vach - mot camera phu nhieu lan xe.</summary>
        public void SetLineName(int id, string name) => Check(ta_line_set_name(_h, id, name), "line_set_name");
        /// <summary>Chong dem lap khi xe lung chung o vach. countMode:
        /// 0 = khoa sau khi bao, mo lai khi roi xa vach >= rearmPx (mac dinh,
        /// rearmPx&lt;=0 lay bang band); 1 = moi track dem 1 lan; 2 = dem moi lan cat.</summary>
        public void SetLineCount(int id, int countMode = 0, float rearmPx = 0)
            => Check(ta_line_set_rearm(_h, id, countMode, rearmPx), "line_set_rearm");
        /// <summary>Vung boc vach bat doi xung (0 = lay bang band).</summary>
        public void SetLineZone(int id, float upPx = 0, float downPx = 0)
            => Check(ta_line_set_zone(_h, id, upPx, downPx), "line_set_zone");
        /// <summary>Tham so ghep track (0 = giu nguyen).</summary>
        public void SetTrackParams(float iouMin = 0, float distGate = 0, float predictK = 0, int expireMs = 0)
            => Check(ta_track_set_params(_h, iouMin, distGate, predictK, expireMs), "track_set_params");
        public string GetLineName(int id)
        {
            var sb = new StringBuilder(64);
            Check(ta_line_get_name(_h, id, sb, sb.Capacity), "line_get_name");
            return sb.ToString();
        }
        public int LineCount => ta_line_count(_h);
        public void ClearLines() => ta_line_clear(_h);

        /// <summary>4 dinh hinh binh hanh boc vach - de ve va dang ky lam read-zone.</summary>
        public float[] LineZone(int lineId)
        {
            var poly = new float[8];
            Check(ta_line_zone(_h, lineId, poly), "line_zone");
            return poly;
        }

        /// <summary>Cap nhat tracker voi detection cua MOT khung. outs[i] ung voi
        /// dets[i]: TrackId ben vung + Crossed=1 khi vua cat vach dung huong
        /// (luc do app phat notify kem ket qua Stage 2).</summary>
        public TaTrackOut[] TrackUpdate(long tsMs, TaDet[] dets)
        {
            var outs = new TaTrackOut[Math.Max(dets.Length, 1)];
            int rc = ta_track_update(_h, tsMs, dets, dets.Length, outs);
            if (rc < 0) throw new TinyAnprException("track_update", (TaStatus)rc);
            return outs;
        }
        public void SetTrackExpire(int ms) => Check(ta_track_expire(_h, ms), "track_expire");

        /// <summary>Dong 1 phieu doc cho track (goi sau MOI luot Stage 2).
        /// Nhan cong bo chi DOI khi ung vien moi du so luot VA ap dao ve trong
        /// so - het canh nhan nhay qua lai luc xe cham o vach. Chuoi sai dinh
        /// dang thi truyen conf nhe (vd conf*0.3). changed=true la vua doi.</summary>
        public string LabelFeed(int trackId, string text, float conf, out bool changed)
        {
            var sb = new StringBuilder(16);
            int rc = ta_track_label_feed(_h, trackId, text ?? "", conf, sb, sb.Capacity);
            if (rc < 0) throw new TinyAnprException("label_feed", (TaStatus)rc);
            changed = rc == 1;
            return sb.ToString();
        }
        public string LabelGet(int trackId)
        {
            var sb = new StringBuilder(16);
            return ta_track_label_get(_h, trackId, sb, sb.Capacity) == 0 ? sb.ToString() : "";
        }
        /// <summary>0 = giu nguyen gia tri hien tai.</summary>
        public void SetLabelParams(int firstN = 0, int confirmN = 0,
                                   float switchRatio = 0f, float decay = 0f)
            => Check(ta_track_set_label_params(_h, firstN, confirmN, switchRatio, decay),
                     "set_label_params");

        /// <summary>Quad DA LAM MUOT de ve overlay (null neu track chua co).</summary>
        public float[]? TrackQuad(int trackId)
        {
            var q = new float[8];
            return ta_track_get_quad(_h, trackId, q) == 0 ? q : null;
        }
        /// <summary>He so muot khung (0..1], 1.0 = tat muot.</summary>
        public void SetTrackSmooth(float alpha)
            => Check(ta_track_set_smooth(_h, alpha), "set_track_smooth");

        /// <summary>useBeam: chay beam search khi greedy ra chuoi sai dinh dang.
        /// minChars: chuoi ngan hon LUON bi coi la khong hop le. -1 = giu nguyen.</summary>
        public void SetDecode(int useBeam = -1, int minChars = -1)
            => Check(ta_set_decode(_h, useBeam, minChars), "set_decode");

        /// <summary>Kiem MOT chuoi da ghep (bien vuong tu thu moi diem cat 2 hang).</summary>
        public bool TextValid(string text, int shape) => ta_text_valid(_h, text ?? "", shape) != 0;

        /// <summary>Gioi han % thoi gian CPU ban cua ngu canh nay (1..100).
        /// PHAI dat Environment.SetEnvironmentVariable("OMP_WAIT_POLICY","passive")
        /// TRUOC lan P/Invoke dau tien, khong thi gan nhu vo tac dung - xem
        /// OmpPassive va ghi chu trong ta_anpr.h.</summary>
        public int CpuBudget
        {
            get => ta_get_cpu_budget(_h);
            set => Check(ta_set_cpu_budget(_h, value), "set_cpu_budget");
        }

        /// <summary>true = OMP_WAIT_POLICY=passive da duoc dat -> CpuBudget co tac dung.</summary>
        public static bool OmpPassive => ta_omp_passive() != 0;

        /// <summary>Muc SIMD DANG chay: 0 scalar, 1 sse, 2 avx2, 3 avx512.</summary>
        public static int MucSimd => ta_get_simd();

        /// <summary>
        /// TRAN muc SIMD. MAC DINH CUA SDK LA SSE (chot 2026-09-12): hau het
        /// may khach chi co SSE/AVX1, de moi may chay CUNG mot duong thi thu
        /// duoc kiem chinh la thu duoc giao. Truoc day mac dinh "cao nhat CPU
        /// cho phep" nen may dev va may khach chay hai duong khac nhau - da
        /// tra gia mot lan: nhanh du phong cua reader co loi buoc nhay, may
        /// khach doc ra chuoi rac suot ca thang ma khong ai bat duoc.
        ///
        /// Gia phai tra khi giu SSE tren may CO AVX2: cham ~30% (do 150 anh
        /// val: 20.3 ms/anh so voi 15.2). Ket qua doc GIONG HET nhau o moi muc.
        ///
        /// muc: 0 scalar, 1 sse, 2 avx2, 3 avx512, -1 = tu chon theo CPU.
        /// PHAI goi TRUOC khi tao TinyAnpr dau tien - muc bi KHOA o lan dung
        /// dau tien va khong doi duoc nua trong cung tien trinh.
        /// </summary>
        public static void DatMucSimd(int muc) => ta_set_simd(muc);

        /// <summary>Nhu DatMucSimd nhung nhan ten: scalar|sse|avx2|avx512|auto.</summary>
        public static void DatMucSimd(string ten)
        {
            int m;
            switch ((ten ?? "sse").Trim().ToLowerInvariant())
            {
                case "scalar": m = 0; break;
                case "sse":    m = 1; break;
                case "avx2":   m = 2; break;
                case "avx512": m = 3; break;
                case "auto":   m = -1; break;
                default: throw new ArgumentException(
                    "muc SIMD phai la scalar|sse|avx2|avx512|auto, nhan: " + ten);
            }
            ta_set_simd(m);
        }

        public string SelfTest()
        {
            var sb = new StringBuilder(256);
            int rc = ta_selftest(_h, sb, sb.Capacity);
            if (rc != 0) throw new TinyAnprException("selftest: " + sb, (TaStatus)rc);
            return sb.ToString();
        }

        public double BenchmarkMs(int iters = 200) => ta_benchmark(_h, iters);

        /// <summary>CA KHUNG trong mot lenh (v0.6): detector -&gt; refine -&gt; vung
        /// doc -&gt; reader. Can ca LoadStage1 lan LoadReader. Tra ve SO BIEN thay
        /// duoc (co the &gt; outPlates.Length: khi do chi phan dau duoc ghi).
        ///
        /// Bien NGOAI vung doc co ZoneId = -1 va Text rong - app van co Quad de
        /// theo doi doi tuong ma khong ton ~9ms/bien cho khau doc.
        /// PlateColor/TextColor HIEN LUON = -1: head mau chua port sang C.</summary>
        public int ProcessFrame(byte[] rgb, int w, int h, TaPlate[] outPlates)
        {
            int rc = ta_process_frame(_h, rgb, w, h, outPlates, outPlates.Length);
            if (rc < 0) throw new TinyAnprException("process_frame", (TaStatus)rc);
            return rc;
        }

        public void Dispose()
        {
            if (_h != IntPtr.Zero) { ta_destroy(_h); _h = IntPtr.Zero; }
            GC.SuppressFinalize(this);
        }
        ~TinyAnpr() { Dispose(); }
    }
}
