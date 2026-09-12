/* ta_anpr.h - Tiny ANPR SDK, API C cong khai (v0.6, 2026-08-06)
 *
 * Thiet ke theo yeu cau: (1) load model dong tu .bin/.sdk + ACTIVE LICENSE
 * THEO USER truoc khi dung; (2) zones CRUD day du (add/sua/xoa/list) voi ngu
 * nghia "bien nam TRONG zone moi chay Stage 2 (doc chu/mau), ngoai zone van
 * tra bbox+quad cua Stage 1" - app dung toa do nay lam tracking doi tuong.
 *
 * Trang thai v0.6:
 *   - TOAN BO tuyen chay trong C: ta_detect (Stage 1 Q8/Q15 + refine) ->
 *     ta_read_plate / ta_process_frame (Stage 2). App KHONG can PyTorch.
 *     Ngoai le duy nhat: head MAU van o Python (xem ta_process_frame).
 *   - Vung/quoc gia (ta_set_region), hau xu ly theo luat vung (ta_plate_fix,
 *     ta_plate_display), beam co rang buoc dinh dang.
 *   - Tracking + line crossing + nhan on dinh theo track.
 *   - Zones CRUD + zone_of; ngan sach CPU; 4 cap hieu nang.
 *
 * BAO MAT (v0.6 - xem docs/bao_mat.md):
 *   - License VA goi model .sdk deu duoc KY Ed25519; DLL chi mang khoa cong
 *     khai nen dich nguoc DLL KHONG tu phat hanh duoc. Sua mot bit trong tep
 *     -> TA_E_TAMPER.
 *   - Khoa giai ma goi .sdk dan xuat tu <mkey> RIENG cua tung license: patch
 *     nhanh kiem license trong DLL cung khong mo duoc goi, vi khoa nam trong
 *     license chu khong nam trong DLL.
 *   - Ban build /DTA_PACK_ONLY tu choi model .bin tran; /DTA_REQUIRE_SIG tu
 *     choi moi tep chua ky. ta_security_info() cho biet ban dang cam co gi.
 *
 * Moi ham (tru create/destroy/activate/version/strerror/set_log) tra
 * TA_E_LICENSE khi chua kich hoat thanh cong.
 */
#ifndef TA_ANPR_H
#define TA_ANPR_H

#ifdef __cplusplus
extern "C" {
#endif

#ifdef _WIN32
#  ifdef TA_BUILD_DLL
#    define TA_API __declspec(dllexport)
#  else
#    define TA_API
#  endif
#else
#  define TA_API
#endif

/* ------------------------------- ma loi -------------------------------- */
enum {
    TA_OK           = 0,
    TA_E_ARG        = -1,   /* tham so sai/NULL */
    TA_E_LICENSE    = -2,   /* chua kich hoat / license hong */
    TA_E_LIC_USER   = -3,   /* license khong cap cho user nay */
    TA_E_LIC_EXPIRED= -4,   /* license het han */
    TA_E_MODEL      = -5,   /* .bin khong nap duoc (magic/version/doc file) */
    TA_E_SELFTEST   = -6,   /* vector vang KHONG bit-exact */
    TA_E_NOTREADY   = -7,   /* tinh nang chua co o phien ban nay (detector C) */
    TA_E_NOSPACE    = -8,   /* buffer nguoi goi dua vao qua nho */
    TA_E_LIC_MACHINE= -9,   /* license khong cap cho MAY nay (hwid khong khop) */
    TA_E_LIC_APP    = -10,  /* license khong cap cho UNG DUNG nay (app khong khop) */
    TA_E_LIC_CLOCK  = -11,  /* dong ho may bi lui ve truoc lan chay gan nhat */
    TA_E_TRIAL_HET  = -13,  /* dung thu het 2h/ngay - can license, hoac cho cua so sau */
    TA_E_TAMPER     = -12   /* tep DA BI SUA: chu ky Ed25519 khong khop (license,
                             * goi .sdk) hoac ma may cua chinh DLL bi va cham */
};

/* Chuoi mo ta ma loi - dung de ghi log/hien cho nguoi dung. Luon tra ve con
 * tro hop le (khong bao gio NULL), khong can giai phong. */
TA_API const char* ta_strerror(int code);

/* ---------------------------- nhat ky (log) -----------------------------
 * Mac dinh SDK im lang o duong thanh cong va in loi nap model ra stderr. App
 * GUI nuot mat stderr -> khong chan doan duoc tu xa. Dat ham nay de huong moi
 * thong bao ve log cua app.
 *   level: 0 = loi, 1 = canh bao, 2 = thong tin
 * Ham co the duoc goi TU NHIEU LUONG - app tu lo dong bo. Dat fn = NULL de
 * quay ve hanh vi mac dinh. Goi duoc TRUOC ta_create (tham so toan tien trinh)
 * de bat ca loi luc nap model dau tien. */
typedef void (*ta_log_fn)(int level, const char* msg, void* user);
TA_API void ta_set_log(ta_log_fn fn, void* user);

/* ------------------------- ket qua mot bien so ------------------------- */
/* zone_id:  >0 = id zone chua TAM bien (da chay Stage 2)
 *            0 = KHONG co zone nao dang ky -> moi bien deu chay Stage 2
 *           -1 = co zone nhung bien NGOAI het -> CHI co box/quad/score/shape
 *                (text/color de trong) - danh cho app tracking. */
typedef struct {
    float box[4];        /* x1,y1,x2,y2 - toa do ANH GOC */
    float quad[8];       /* 4 goc TL,TR,BR,BL (x,y) - toa do ANH GOC */
    float score;         /* objectness cua detector */
    int   shape;         /* 0 = bien dai, 1 = bien vuong */
    int   zone_id;       /* xem tren */
    char  text[16];      /* chuoi bien so (rong neu ngoai zone) */
    float text_conf;     /* do tin cay trung binh theo ky tu 0..1 */
    int   plate_color;   /* 0 trang 1 vang 2 xanhduong 3 do 4 xanhla; -1 = n/a */
    int   text_color;    /* 0 den 1 trang 2 khac; -1 = n/a */
} ta_plate_t;

typedef struct ta_ctx ta_ctx;   /* handle mo (opaque) */

/* --------------------------- vong doi & license ------------------------ */
TA_API ta_ctx*     ta_create(void);
TA_API void        ta_destroy(ta_ctx*);
TA_API const char* ta_version(void);                 /* "0.1.0" */

/* Kich hoat theo USER: license_file la XML ma hoa AES-256-CBC (sinh boi
 * tools/gen_license.ps1 hoac tool .NET dung clEncryptDecrypt cung mat khau
 * san pham). Kiem: product khop, user khop (khong phan biet hoa thuong),
 * chua het han. */
TA_API int ta_activate(ta_ctx*, const char* license_file, const char* user);
/* Van tay MAY chay (16 ky tu hex, khong can license). Khach hang chay lay ma
 * nay gui cho ben cap license; license phat ra chi kich hoat duoc tren may do.
 * Tra so ky tu da ghi, hoac TA_E_NOSPACE neu cap < 17. */
TA_API int ta_machine_id(char* buf, int cap);
/* Ma BAN BUILD ("VCAR-20260730") hoac "PUBLIC" neu build bang khoa chung.
 * Moi ban build phat cho mot doi tac co khoa san pham RIENG (xem
 * tools/gen_product_key.ps1): license cua doi tac nay khong giai duoc bang DLL
 * cua doi tac kia. Ban build KHONG rang buoc may - chay o dau cung duoc. */
TA_API const char* ta_build_id(void);
/* Muc lenh vec dang dung: "AVX2" | "AVX" | "scalar". Chon TU DONG luc chay
 * theo CPUID (+ xgetbv), khong can bien dich rieng. Ep bang bien moi truong
 * TA_SIMD=scalar|avx|avx2 de thu. Ket qua so hoc GIONG NHAU o moi muc (da kiem
 * selftest bit-exact); chi khac toc do - scalar cham hon AVX2 khoang 1,5 lan. */
TA_API const char* ta_simd_info(void);
/* Nhu ta_activate nhung kiem THEM hai rang buoc, de license bi chep sang noi
 * khac thi khong dung duoc:
 *   <hwid> trong license != "ANY"  -> phai chua ta_machine_id() cua may nay
 *                                     (nhieu may thi ngan cach bang dau phay)
 *   <app>  trong license khong rong -> phai trung app_id truyen vao day
 * app_id la ma DU AN do ben tich hop bien thang vao ung dung cua ho.
 * LUU Y: day la kiem o phia may khach, chan duoc chuyen tay file license chu
 * khong chan duoc nguoi co kha nang va cho ma may. */
TA_API int ta_activate_ex(ta_ctx*, const char* license_file, const char* user,
                          const char* app_id);

/* CHE DO DUNG THU (khong license): 2 gio moi 24h, CHONG reset (cong don qua
 * cac lan restart, buoc theo may). Goi khi ta_activate tra TA_E_LICENSE (khong
 * co license). Tra TA_OK neu con gio, TA_E_TRIAL_HET neu het cua so hom nay.
 * Model dung thu la goi dong bang license-thu (xem docs). */
TA_API int ta_trial_start(ta_ctx*, const char* user);
/* So GIAY con lai trong cua so 24h hien tai (0 = het). -1 neu khong o che do thu. */
TA_API int ta_trial_seconds_left(ta_ctx*);
/* 1 neu dang chay che do dung thu, 0 neu license that. */
TA_API int ta_is_trial(ta_ctx*);
/* Chuoi mo ta license da kich hoat: "user=...;issued=...;expiry=...". */
TA_API int ta_license_info(ta_ctx*, char* buf, int cap);
/* Trang thai CAC LOP BAO VE cua ban DLL nay - de kiem tra truoc khi ban giao:
 *   "build=VCAR-20260806 sig=vendor-20260806 lic_sig=1 pack=v2 packonly=1
 *    text=ok require_sig=1"
 *   sig=      ma khoa cong khai nhung trong DLL, "khong" = ban DEV (khong kiem
 *             duoc chu ky - TUYET DOI khong giao ban nay cho khach)
 *   lic_sig=  license dang kich hoat co chu ky khong (0 = license kieu cu)
 *   pack=     phien ban goi dang mo (v1 cu / v2 co khoa rieng theo license)
 *   packonly= 1 = DLL tu choi model .bin tran, chi nhan goi .sdk
 *   text=     ok | LECH | chua-dong-dau  (dau van tay ma may cua chinh DLL)
 * Goi duoc truoc khi kich hoat (khi do lic_sig/pack bo trong). */
TA_API int ta_security_info(ta_ctx*, char* buf, int cap);
/* So NGAY con lai den han (am = da qua han). App nen canh bao nguoi dung khi
 * con duoi ~30 ngay - het han giua ca truc ma khong bao truoc la mat viec.
 * TA_E_LICENSE neu chua kich hoat. */
TA_API int ta_license_days_left(ta_ctx*);

/* ------------------------------- model --------------------------------- */
/* Nap reader. Nhan HAI dang:
 *   - .bin  : model Stage 2 tran (tu quant/export_reader.py --bits 16|8)
 *   - .sdk  : GOI MA HOA chua ca hai model, tu giai ma va nap muc "reader"
 * Tu mo ta: kich thuoc canonical, so kenh, vocab, op-stream nam trong file. */
TA_API int ta_load_reader(ta_ctx*, const char* bin_path);

/* ---------------------------- Stage 1 (C) ------------------------------
 * Nap detector + refine head. Nhan .sdk (lay muc "det" va "refine") hoac
 * duong dan detector .bin (khi do refine lay tep cung thu muc, ten
 * refine_q15.bin; khong co thi van chay - 4 goc la quad THO, sai so ~2.3x).
 * LUU Y: engine Stage 1 dung trang thai TOAN TIEN TRINH (mot model cho ca
 * process), khac reader la theo tung ctx. Nap o ctx nao cung nhu nhau. */
TA_API int ta_load_stage1(ta_ctx*, const char* path);

/* Phat hien bien + 4 goc tren anh RGB [h*w*3], toa do tra ve o ANH GOC.
 * out: mang float nguoi goi cap phat, MOI detection 14 so:
 *   score, shape, x1, y1, x2, y2, x0,y0, x1c,y1c, x2c,y2c, x3c,y3c
 * (4 goc TL,TR,BR,BL da qua refine). cap_dets = so detection toi da chua duoc.
 * Tra ve SO DETECTION thuc te (co the > cap_dets: khi do chi 'cap_dets' dau
 * duoc ghi), hoac ma loi am.
 * side_crop/conf < 0 => lay tu chinh tep model (khuyen dung). */
/* max_longest: TRAN canh dai anh dua vao mang. Model nay chay o che do KICH
 * THUOC DONG (moi anh mot kich thuoc, theo bac megapixel) nen KHONG chan thi
 * khung 1080p se chay o 1280x904 - rat cham. 0 = lay tri trong tep model;
 * dat 640 nhu ban demo. */
TA_API int ta_detect(ta_ctx*, const unsigned char* rgb, int w, int h,
                     float side_crop, float conf, float* out, int cap_dets,
                     int max_longest);

/* "in=3x384x640 grid=15x48x80 stride=8 side_crop=0.100 conf=0.900 refine=1" */
TA_API int ta_stage1_info(ta_ctx*, char* buf, int cap);

/* TRAN canh dai anh dua vao mang, dung cho ta_process_frame (ta_detect nhan
 * tham so rieng tung lan goi). 0 = lay tri trong tep model.
 * NEN DAT 640: model chay KICH THUOC DONG theo bac megapixel, khong chan thi
 * khung 1080p chay o 1280x904 - do duoc 57 ms/khung so voi 13 ms khi chan 640,
 * ma khau doc khong loi gi (phan chi tiet mat da duoc bu bang stem_crop). */
TA_API int ta_set_max_longest(ta_ctx*, int px);
TA_API int ta_get_max_longest(ta_ctx*);

/* Stage 2 TRON GOI: anh RGB goc + quad (8 so, toa do ANH GOC, TL,TR,BR,BL)
 * -> doc chu. Tu lo cat vung + CLAHE + stem + nan phoi canh ve canonical roi
 * goi engine reader (xem cpp/stage2_rt.h). Dung ham nay thi app KHONG can
 * PyTorch cho bat ky khau nao nua.
 * shape: 0 = bien dai, 1 = bien vuong (lay tu ta_detect).
 * conf/format_valid: co the NULL neu khong can. */
TA_API int ta_read_plate(ta_ctx*, const unsigned char* rgb, int w, int h,
                         const float quad8[8], int shape,
                         char* text, int cap, float* conf, int* format_valid);

/* NAN ANH BIEN (2026-09-10): anh RGB goc + quad (8 so, toa do ANH GOC, tu
 * ta_detect - da qua refine) -> anh bien THANG out_w x out_h RGB, lay mau
 * truc tiep tren ANH DAU VAO (giu du phan giai nguon, KHONG qua anh 640 cua
 * mang). Dung de hien thi / luu / dua OCR ngoai. Khong can model, chi can
 * license. margin: le them moi phia theo ti le canh (0.04 = 4 %), 0 = dung
 * bien quad. out_rgb: nguoi goi cap phat out_w*out_h*3 byte.
 * Goi y kich thuoc: bien dai 520x120, bien vuong 336x240, hoac ta_plate_size
 * de giu nguyen phan giai nguon. */
TA_API int ta_warp_plate(ta_ctx*, const unsigned char* rgb, int w, int h,
                         const float quad8[8], float margin,
                         int out_w, int out_h, unsigned char* out_rgb);
/* Kich thuoc goc (px) cua bien trong anh theo quad + margin (rong = trung
 * binh 2 canh ngang, cao = trung binh 2 canh doc) -> out_w/out_h cho
 * ta_warp_plate khi muon 1 px ra = 1 px vao. Khong can handle. */
TA_API int ta_plate_size(const float quad8[8], float margin, int* out_w, int* out_h);

/* --------------------------- goi model .sdk ----------------------------
 * MOT TEP DUY NHAT thay cho bo tep model roi rac, ma hoa bang CHINH khoa san
 * pham cua ban build (xem ta_build_id): goi cua doi tac nay khong mo duoc
 * bang DLL cua doi tac kia. Huan luyen xong chi can thay dung tep .sdk la
 * chay model moi, khong build lai gi.
 *
 * Ten muc quy uoc (v0.5 co VUNG/QUOC GIA - hau to "@<cc>"):
 *   "reader@vn" = Stage 2 (.bin)                    <- ta_load_reader
 *   "det@vn"    = Stage 1 detector Q8/Q15 (.bin)    <- ta_load_stage1
 *   "refine@vn" = Stage 1 refine head Q15 (.bin)    <- ta_load_stage1
 *   "stage1"    = checkpoint PyTorch (.pt)          <- CU, tuong thich nguoc
 * MOT goi chua duoc NHIEU vung ("det@vn" + "det@th"...): app goi
 * ta_set_region() truoc khi nap de chon. Ten TRAN khong hau to ("det",
 * "reader", "refine") la goi CU truoc v0.5 - duoc hieu la "vn".
 * Muc "stage1" la duong CU (app tu torch.load tu bo nho). Tu khi co "det" +
 * "refine" thi Stage 1 chay HAN trong SDK, app khong can PyTorch nua. */
/* ---- GOI v1 (cu): ma hoa bang MOT khoa san pham cho ca ban build ----
 * Giu de doc/dong lai goi da phat hanh. Diem yeu: moi khach cung mot ban build
 * dung chung mot khoa, nen goi cua khach nay mo duoc bang DLL cua khach kia. */
TA_API int ta_pack_build(const char* out_path, const char* const* names,
                         const char* const* files, int n);
/* ---- GOI v2 (khuyen dung tu 2026-08-06) ----
 * Khoa ma hoa = KDF(khoa san pham + <mkey> RIENG cua license dang kich hoat),
 * nen goi CHI mo duoc bang DLL dung ban build VA license da phat cho goi do.
 * Vi the phai ta_activate() bang license CUA KHACH truoc khi dong goi cho ho.
 * IV ngau nhien tung tep. Sau khi dong, PHAI ky:
 *     python tools/ta_sign.py sign --file <out_path>
 * Khong ky thi DLL ban phat hanh (co /DTA_REQUIRE_SIG) se tu choi voi
 * TA_E_TAMPER. meta_json = chuoi JSON tuy y (tag model, ngay train, nguong da
 * hieu chuan...) doc lai bang ta_pack_meta - de truy vet goi ngoai dong. */
TA_API int ta_pack_build_ex(ta_ctx*, const char* out_path,
                            const char* const* names, const char* const* files,
                            int n, const char* meta_json);
TA_API int ta_pack_open(ta_ctx*, const char* pack_path);
/* Sieu du lieu nhung luc dong goi (muc "meta"), "" neu goi khong co. */
TA_API int ta_pack_meta(ta_ctx*, char* buf, int cap);
/* TRICH MUC GOC - KHOA O BAN GIAO (2026-09-12).
 * Hai ham duoi tra ve byte NGUYEN VEN cua mot muc trong goi (det@vn, reader@vn,
 * color@vn...) va chi doi da kich hoat license. Voi san pham BAN RA NGOAI thi
 * chinh khach hang cam license hop le, nen chung dua thang model cho ho qua mot
 * loi goi API - khong can debugger, khong can dump RAM.
 * Ban mac dinh (san pham) tra TA_E_NOTREADY. Chi ban bien dich voi
 * /DTA_DEV_TOOLS moi mo - dung cho cong cu noi bo.
 * ta_pack_list ben duoi VAN MO: no chi tra TEN + CO, khong tra noi dung. */

/* Do dai muc, hoac TA_E_ARG neu khong co muc do. TA_E_NOTREADY o ban giao. */
TA_API int ta_pack_size(ta_ctx*, const char* name);
/* Chep muc ra buf. Tra ve so byte da chep, TA_E_NOSPACE neu cap qua nho. */
TA_API int ta_pack_read(ta_ctx*, const char* name, void* buf, int cap);
/* Liet ke: "reader=502000;stage1=451000" */
TA_API int ta_pack_list(ta_ctx*, char* buf, int cap);
/* ---- VUNG / QUOC GIA (v0.5, mac dinh "vn") ----
 * Chon TRUOC khi ta_load_stage1/ta_load_reader: quyet dinh muc model lay tu
 * goi ("det@<cc>"...) VA bo luat dinh dang bien cua nuoc do (beam +
 * format_valid). Vung chua co luat trong DLL van nap duoc model - chi khong
 * kiem dinh dang. Doi vung xong phai NAP LAI model. */
TA_API int ta_set_region(ta_ctx*, const char* code);          /* "vn", "th"... */
TA_API int ta_get_region(ta_ctx*, char* buf, int cap);
/* Vung co model trong goi dang mo, "vn;th". Goi cu mot-model -> "vn". */
TA_API int ta_region_list(ta_ctx*, char* buf, int cap);
/* ---- HAU XU LY theo luat vung (v0.5.1) ----
 * ta_plate_fix: sua ky tu theo VI TRI cua bien nuoc do (bien VN: 2 so tinh -
 *   chu seri - day so; doi B<->8, O<->0, S<->5... theo cho). CHI sua khi
 *   chuoi dang KHONG hop dinh dang, va chi nhan khi sua xong THANH hop le -
 *   khong bao gio dong vao chuoi da dung. Tra 1 = da sua, 0 = giu nguyen.
 *   Engine da tu goi ben trong ta_read_plate/ta_read_canon; ham nay danh cho
 *   nhan lay tu bo on dinh theo track hoac tu nguon khac.
 * ta_plate_display: chuoi hien thi day du dau, "30A-123.45" / "29-X1 123.45".
 *   l2 = NULL hoac rong cho bien mot hang. TA_E_ARG neu khong khop luat. */
TA_API int ta_plate_fix(ta_ctx*, const char* text, int shape, char* out, int cap);
TA_API int ta_plate_display(ta_ctx*, const char* l1, const char* l2,
                            char* out, int cap);
/* "bits=16 qmax=16383 in_ch=32 ch=32 canon=24x96/48x48 vocab=41" */
TA_API int ta_model_info(ta_ctx*, char* buf, int cap);
/* ---- 4 cap hieu nang (nguoi dung 2026-07-29) ----
 * Cap        luong CPU                RAM/khoi dong
 * TA_PERF_MAX    toan bo nhan logic   khoa trang nho model (khong swap) + warm-up 3 luot
 * TA_PERF_HIGH   toi da 12            khoa trang nho model + warm-up 1 luot
 * TA_PERF_MEDIUM toi da 6             warm-up 1 luot
 * TA_PERF_LOW    toi da 4             khong warm-up (khoi dong nhe nhat)
 * Goi truoc hay sau ta_load_reader deu duoc (truoc thi ap dung khi nap model).
 * LUU Y do thuc te: bai toan reader rat nho (canonical 24x96) nen tren may
 * nhieu nhan, MAX co the CHAM hon HIGH (36 luong 9.6ms vs 12 luong 7.7ms -
 * chi phi dong bo an vao phan tinh). MAX ton tai cho may it nhan. */
enum { TA_PERF_LOW = 0, TA_PERF_MEDIUM = 1, TA_PERF_HIGH = 2, TA_PERF_MAX = 3 };
TA_API int ta_set_performance(ta_ctx*, int level);
/* So luong OpenMP cho engine. n<=0 = AUTO. Ghi de lua chon cua performance. */
TA_API int ta_set_threads(ta_ctx*, int n);
TA_API int ta_cpu_count(void);
/* So luong dang dung thuc te (sau khi phan giai AUTO). */
TA_API int ta_get_threads(ta_ctx*);

/* ------------------------------- zones --------------------------------- */
/* Toa do theo ANH GOC cua camera. pts = [x0,y0,x1,y1,...], n >= 3 dinh.
 * Tra ve id (>0) hoac TA_E_ARG. ID ON DINH: xoa zone nay khong doi id zone khac. */
TA_API int  ta_zone_add(ta_ctx*, const float* pts, int n);
TA_API int  ta_zone_add_rect(ta_ctx*, float x1, float y1, float x2, float y2);
/* "sua": thay toan bo dinh cua zone id (giu nguyen id). TA_E_ARG neu khong co id. */
TA_API int  ta_zone_update(ta_ctx*, int id, const float* pts, int n);
TA_API int  ta_zone_remove(ta_ctx*, int id);          /* TA_OK / TA_E_ARG */
/* CHU KY BAO LAP cua mot vung, mili giay. 0 = tat (chi bao khi cat vach).
 * Dung cho che do BAI DO: xe do vao box la bao bien len, cu ngan nay lai bao
 * mot lan, khong can di qua vach nao. Nhip tinh theo TUNG XE. */
TA_API int  ta_zone_set_notify(ta_ctx*, int id, int ms);
TA_API int  ta_zone_notify(ta_ctx*, int id);   /* ms, hoac TA_E_ARG neu khong co */
/* SO LUOT DOC GIONG NHAU can co truoc khi chup (1 = chup ngay luot dau).
 * Chong nhay so: doc lech mot ky tu ma chup luon thi ban ghi sai. */
TA_API int  ta_zone_set_confirm(ta_ctx*, int id, int n);
TA_API int  ta_zone_confirm(ta_ctx*, int id);
TA_API int  ta_zone_count(ta_ctx*);
/* Liet ke: ghi toi da cap zone. ids[i] = id; npts[i] = so dinh; pts_flat nhan
 * dinh cua TUNG zone noi tiep nhau (moi zone toi da 16 dinh -> cap*32 float
 * la du). Tra ve so zone da ghi. */
TA_API int  ta_zone_list(ta_ctx*, int* ids, int* npts, float* pts_flat, int cap);
TA_API void ta_zone_clear(ta_ctx*);
/* Bien co quad nay thuoc zone nao (ngu nghia zone_id o ta_plate_t). */
TA_API int  ta_zone_of_quad(ta_ctx*, const float* quad8);

/* ---- MAU BIEN (v0.8, 2026-08-12) ---------------------------------------
 * Doan mau NEN bien va mau CHU tu (anh RGB goc, quad). Chay head chroma trong
 * C (muc "color@<vung>" trong goi) - KHONG con phai tu doan HSV ben app.
 *
 * Vi sao co ham RIENG chu khong chi dua vao ta_process_frame: duong dung nhieu
 * nhat la ta_detect + ta_read_plate (de ap nguong rieng theo dang bien), duong
 * do khong di qua ta_process_frame nen se khong bao gio thay mau.
 *
 * out_plate: 0 trang 1 vang 2 xanhduong 3 do 4 xanhla
 * out_text : 0 den 1 trang 2 khac    (truyen NULL neu khong can)
 * Tra ve TA_OK, hoac TA_E_MODEL neu goi KHONG co muc mau (app tu lo lay).
 * Chi phi ~0.1 ms/bien - lay mau 48x16 diem, khong chay CNN. */
TA_API int  ta_plate_color(ta_ctx*, const unsigned char* rgb, int w, int h,
                           const float* quad8, int* out_plate, int* out_text);
/* 1 = goi co head mau, 0 = khong (plate_color se luon la -1). */
TA_API int  ta_co_color(ta_ctx*);

/* ---------------------- tracking + line crossing ----------------------- */
/* (v0.3) Ve NHIEU vach tren mot anh - nhu da support nhieu zone. Moi vach:
 * 2 dau (toa do ANH GOC), band_px = nua be rong HINH BINH HANH boc vach
 * (lay ra bang ta_line_zone de ve + dang ky lam read-zone cho Stage 2 doc
 * truoc), dir_mode chon huong bao:
 *     0 = ca hai huong | 1 = chi top->bottom | 2 = chi bottom->top
 * ("top->bottom" = theo chieu y TANG cua anh; vach thang dung thi +1 nghia
 *  la trai->phai).
 *
 * Dung: moi khung, app dua danh sach detection Stage 1 vao ta_track_update.
 * SDK gan track_id ben vung (ghep IoU tham lam giua 2 khung) va bao
 * crossed=1 dung MOT lan khi doan duong tam bien (khung truoc -> khung nay)
 * GIAO vach theo huong da chon -> app chay/lay ket qua Stage 2 cua bien do
 * va phat notify day du. Track khong thay lai qua expire_ms (mac dinh
 * 1500ms) thi tu xoa. */
typedef struct {
    float box[4];        /* x1,y1,x2,y2 - toa do ANH GOC */
    float quad[8];       /* TL,TR,BR,BL */
    float score;
    int   shape;
} ta_det_t;

typedef struct {
    int track_id;        /* id ben vung qua cac khung */
    int crossed;         /* 1 = VUA cat vach o khung nay -> phat notify */
    int line_id;         /* vach nao (khi crossed=1) */
    int direction;       /* +1 = top->bottom, -1 = bottom->top */
} ta_track_out_t;

TA_API int  ta_line_add(ta_ctx*, float x1, float y1, float x2, float y2,
                        float band_px, int dir_mode);        /* -> id (>0) */
TA_API int  ta_line_update(ta_ctx*, int id, float x1, float y1, float x2,
                           float y2, float band_px, int dir_mode);
TA_API int  ta_line_remove(ta_ctx*, int id);
/* TEN LAN cho vach (toi da 31 ky tu): mot camera thuong phu NHIEU LAN, app
 * can "Lan 2 - cong ra" chu khong phai "line_id=3". Ten di theo vach, giu
 * nguyen khi ta_line_update doi hinh dang. */
TA_API int  ta_line_set_name(ta_ctx*, int id, const char* name);
/* CHONG DEM LAP khi xe lung chung o vach (xe lui roi tien lai). Sau khi mot
 * track da bao tren vach nay, no bi khoa; count_mode quyet dinh khi nao mo:
 *   0 REARM_DIST (mac dinh) - mo khi track roi XA vach >= rearm_px (khoang
 *     cach toi DOAN vach). rearm_px <= 0 -> lay bang band cua vach.
 *   1 ONCE   - moi track chi bao DUNG MOT lan tren vach nay.
 *   2 ALWAYS - bao moi lan cat (khong khoa). */
TA_API int  ta_line_set_rearm(ta_ctx*, int id, int count_mode, float rearm_px);
/* VUNG BOC VACH (read-zone) - cau hinh RIENG, khong dinh band. Do theo phap
 * tuyen "xuong duoi" cua vach: up_px noi ve phia TREN, down_px ve phia DUOI
 * (<=0 -> lay bang band). Vach chi bao chieu 'down' nen dat up_px LON de bien
 * duoc doc SOM, cat vach la co san chuoi. */
TA_API int  ta_line_set_zone(ta_ctx*, int id, float up_px, float down_px);
/* Tham so GHEP TRACK (<=0 = giu nguyen gia tri hien tai):
 *   iou_min   nguong IoU coi la cung mot xe        (mac dinh 0.15)
 *   dist_gate he so duong cheo box cho ghep du phong (1.2)
 *   predict_k nguong no them theo van toc*dt        (0.5)
 *   expire_ms track khong thay lai bao lau thi xoa  (1500) */
TA_API int  ta_track_set_params(ta_ctx*, float iou_min, float dist_gate,
                                float predict_k, int expire_ms);
TA_API int  ta_line_get_name(ta_ctx*, int id, char* buf, int cap);
TA_API int  ta_line_count(ta_ctx*);
/* moi vach ghi 5 float [x1,y1,x2,y2,band] vao xyxyb + dir vao dir_modes */
TA_API int  ta_line_list(ta_ctx*, int* ids, float* xyxyb, int* dir_modes, int cap);
TA_API void ta_line_clear(ta_ctx*);
/* 4 dinh hinh binh hanh boc vach (TL,TR,BR,BL) - de ve va lam read-zone */
TA_API int  ta_line_zone(ta_ctx*, int line_id, float poly8[8]);
/* Cap nhat tracker voi detection cua MOT khung; out[i] ung voi dets[i].
 * ts_ms: dong ho mili giay bat ky nhung TANG DAN. Tra ve so track dang song. */
TA_API int  ta_track_update(ta_ctx*, long long ts_ms,
                            const ta_det_t* dets, int n, ta_track_out_t* out);
TA_API int  ta_track_expire(ta_ctx*, int ms);   /* doi nguong xoa track */

/* ---- NHAN ON DINH theo track (v0.3.1, 2026-07-29) ----------------------
 * Van de: doc lien tuc mot bien cho ket qua dao dong (29A12345 <-> 29A12845)
 * lam nhan tren man hinh va nhan trong notify NHAY LIEN TUC, nhat la luc xe
 * cham o vach. Cach cua ANPR thuong mai: BO PHIEU CO TRONG SO - moi luot doc
 * dong 1 phieu nang bang conf; nhan cong bo chi DOI khi ung vien moi du so
 * luot (confirm_n, mac dinh 5) VA tong trong so >= switch_ratio (1.5) lan
 * nhan cu. Nhan dau tien cong bo nhanh (first_n=2) de kip xe cat vach.
 *
 * Dung: sau MOI luot doc Stage 2, goi ta_track_label_feed voi chuoi + conf
 * (chuoi khong hop le dinh dang thi truyen conf * 0.3 - van co phieu nhung
 * nhe). Chuoi hien thi / dua vao notify lay tu stable_out (hoac
 * ta_track_label_get). Tra ve: 1 = nhan vua DOI o luot nay, 0 = giu nguyen,
 * TA_E_* < 0 = loi (track khong ton tai...). */
TA_API int  ta_track_label_feed(ta_ctx*, int track_id, const char* text,
                                float conf, char* stable_out, int cap);
TA_API int  ta_track_label_get(ta_ctx*, int track_id, char* out, int cap);
/* doi tham so LUC CHAY (0/am = giu nguyen gia tri hien tai):
 * first_n: so luot cho nhan dau; confirm_n: so luot de DOI nhan;
 * switch_ratio: ti le trong so phai vuot; decay: phieu cu nhat dan (0..1). */
TA_API int  ta_track_set_label_params(ta_ctx*, int first_n, int confirm_n,
                                      float switch_ratio, float decay);

/* KHUNG MUOT theo track: quad ve overlay lay tu day thay vi quad detection
 * tho - loc alpha-beta (du doan theo van toc roi keo ve do dac) nen khong
 * rung ma cung khong tre khi xe chay nhanh. alpha (0..1], 1 = tat muot;
 * doi luc chay bang ta_track_set_smooth. */
TA_API int  ta_track_get_quad(ta_ctx*, int track_id, float quad8[8]);
TA_API int  ta_track_set_smooth(ta_ctx*, float alpha);

/* ---- Giai ma (v0.3.2) ---------------------------------------------------
 * use_beam: 1 = khi greedy ra chuoi KHONG hop le dinh dang bien VN thi chay
 *   beam search (B=12) va lay ban HOP LE diem cao nhat. Greedy chon argmax
 *   tung cot doc lap nen mot cot mo ho (B/8, D/0, G/6) hong la hong ca chuoi.
 *   Chi doi khi greedy sai - khong bao gio lam hong ban dang dung. 0 = tat.
 * min_chars: chuoi ngan hon nguong nay LUON bi danh dau khong hop le (mac
 *   dinh 6). Bien VN ngan nhat 7 ky tu; "G8" / "00" / "883" la manh bien bi
 *   cat hoac vet ban - khong duoc phep bao la bien.
 * Truyen so AM cho tham so nao = giu nguyen tham so do. */
TA_API int  ta_set_decode(ta_ctx*, int use_beam, int min_chars);

/* ---- NGAN SACH CPU (v0.3.3) --------------------------------------------
 * NHIEU CAMERA + UI: gioi han SO LUONG luong (ta_set_threads /
 * ta_set_performance) la CHUA DU - 4 luong chay het cong suat van an tron 4
 * nhan va UI giat. Ham nay gioi han DUTY CYCLE: sau moi luot doc, SDK ngu
 * mot khoang ti le voi thoi gian vua lam, sao cho
 *     thoi gian ban / (ban + ngu)  ~=  percent %
 * Vd 4 camera x 4 luong x budget 25% = ban dung ~4 nhan tren tong 16 nhan
 * da cap phat, con lai tra ve cho he dieu hanh.
 *
 * DANH DOI: do TRE cua chinh luot doc do tang len ~ (100/percent) lan. Bien
 * 9ms voi budget 25% se mat ~36ms tuong doi. Voi camera 25fps va doc theo su
 * kien (moi xe chi doc vai lan) thi hoan toan chap nhan duoc; voi bai can do
 * tre thap thi de 100.
 *
 * Moi ngu canh (moi camera) co ngan sach RIENG. percent 1..100, 100 = tat
 * ham. Mac dinh 100.
 *
 * !!! BAT BUOC: dat bien moi truong OMP_WAIT_POLICY=passive TRUOC KHI NAP
 * ta_anpr.dll, khong thi ham nay gan nhu VO TAC DUNG. Mac dinh OpenMP cua
 * MSVC la ACTIVE - sau moi vung song song cac luong tho QUAY TIT cho viec ke
 * tiep, nen luong chinh co ngu thi CPU van bi an het. Do 2026-07-30, 4 luong:
 *       OMP_WAIT_POLICY     budget 100%   budget 25%
 *       (mac dinh ACTIVE)    3.97 nhan     3.19 nhan   <- ham vo tac dung
 *       passive              3.10 nhan     0.54 nhan   <- dung nhu thiet ke
 * Gia phai tra: passive lam thong luong reader giam ~9%.
 *   C/C++ : _putenv("OMP_WAIT_POLICY=passive") truoc lan goi DLL dau tien,
 *           hoac dat bien moi truong cho ca tien trinh.
 *   .NET  : Environment.SetEnvironmentVariable("OMP_WAIT_POLICY","passive")
 *           TRUOC lan P/Invoke dau tien.
 *   Python: binding tu dat san (TinyAnpr(wait_policy="passive")).
 * ta_omp_passive() cho biet bien da duoc dat dung chua. */
TA_API int  ta_set_cpu_budget(ta_ctx*, int percent);
TA_API int  ta_get_cpu_budget(ta_ctx*);
/* 1 = OMP_WAIT_POLICY dang la passive (ngan sach CPU se co tac dung),
 * 0 = chua dat (ham CPU se khong an thua). */
TA_API int  ta_omp_passive(void);

/* MUC SIMD (v0.6.1, 2026-09-12). MAC DINH LA SSE, khong tu len AVX2.
 *
 * Vi sao khong de "cao nhat CPU cho phep": hau het may khach chi co SSE/AVX1,
 * nen de auto thi may dev chay mot duong con may khach chay duong KHAC - va
 * duong khach chay lai la duong khong ai kiem. Da tra gia mot lan: loi buoc
 * nhay trong nhanh du phong cua reader song ca thang, may khach doc ra chuoi
 * rac, vi moi phep kiem deu chay tren may co AVX2.
 *
 * Gia phai tra khi giu SSE tren may CO AVX2: cham ~30% (do 250 anh val,
 * 14.55 -> 18.90 ms/anh). Muon nhanh thi GOI RO ham nay.
 *
 * muc: 0 scalar, 1 sse (mac dinh), 2 avx2, 3 avx512, -1 = tu chon theo CPU.
 * Khong bao gio ep LEN cao hon CPU that ho tro.
 * PHAI goi TRUOC lan nhan dang dau tien - muc duoc nho lai o lan dung dau. */
TA_API void ta_set_simd(int muc);
TA_API int  ta_get_simd(void);        /* muc DANG chay (xem ta_simd_ten) */

/* Kiem MOT chuoi DA GHEP (bien vuong: tu thu moi diem cat hai hang) + rang
 * buoc do dai toi thieu. Dung cho nhan lay tu bo on dinh theo track - luc do
 * chuoi khong con di kem thong tin tach hang cua luot doc nao ca. */
TA_API int  ta_text_valid(ta_ctx*, const char* text, int shape);

/* --------------------------- hinh hoc tien ich ------------------------- */
/* Nan quad (4 goc TL,TR,BR,BL) thanh HINH BINH HANH chuan roi NOI RONG - de
 * ve khung bien cho dep. Quad tu refine bam sat mep bien (no duoc train de
 * trung quad GT) nen ve nguyen trong nhu "can" vao bien; hon nua 4 goc doc
 * doc lap tu 4 heatmap nen hai canh doi dien co the khong song song.
 *   parallelogram != 0: ep 2 cap canh doi dien song song (trung binh hoa
 *     vector canh) - het meo, nhin "phang" hon h...
 *   mx, my: noi rong theo TI LE be rong / chieu cao bien (vd 0.04 = 4%).
 * Ham THUAN HINH HOC, khong can license, khong dung model. */
TA_API int ta_quad_expand(const float* quad8, float mx, float my,
                          int parallelogram, float* out8);

/* ------------------------------ suy luan ------------------------------- */
/* Doc tu luoi CANONICAL (dau ra buoc rectify): canon_hwc [h*w*in_ch] double
 * layout HWC, shape 0/1. Ghi text + conf.
 *
 * format_valid (cho phep NULL): 1 neu chuoi khop LUAT BIEN VN (ke ca quan
 * doi) - kiem TRONG SDK tu v0.2 (nguoi dung 2026-07-28), voi bien vuong kiem
 * RIENG hang tren/hang duoi truoc khi ghep nen chac hon moi cach doan tren
 * chuoi gop. Ly do ton tai: quay thu camera that cho thay detector co the
 * dong khung khuon mat/bang hieu roi reader "doc" ra '2'/'22' - app phai co
 * co so de vut nhung chuoi nay thay vi hien ra man hinh. */
TA_API int ta_read_canon(ta_ctx*, const double* canon_hwc, int h, int w,
                         int shape, char* text, int cap, float* conf,
                         int* format_valid);
/* Doc vector vang nhung trong .bin (demo/kiem tra nhanh): shape 0 = bien dai. */
TA_API int ta_read_golden(ta_ctx*, int shape, char* text, int cap, float* conf,
                          int* format_valid);
/* Kiem dinh dang doc lap (app dung cho OCR nguon khac cung duoc):
 * line2 = NULL/rong -> bien 1 hang: ^\d{2}[A-Z]{1,2}\d{4,6}$ | ^[A-Z]{2}\d{4}$
 * co line2          -> bien 2 hang: (top ^\d{2}[A-Z]{1,2}\d{0,2}$ + bot
 *   ^\d{3,5}$) HOAC quan doi (top ^[A-Z]{2}$ + bot ^\d{4}$).
 * PHAI khop data/plate_format.py - hai ben cung mot bo luat. */
TA_API int ta_format_valid(const char* line1, const char* line2);
/* Selftest bit-exact voi vector vang (LONG + SQUARE). TA_OK = PASS. */
TA_API int ta_selftest(ta_ctx*, char* report, int cap);
/* ms/bien khi chay lap vector vang LONG. */
TA_API double ta_benchmark(ta_ctx*, int iters);

/* CA KHUNG trong MOT lenh (v0.6): detector -> refine -> vung doc -> reader.
 * Can ca ta_load_stage1 lan ta_load_reader (goi .sdk co du ba muc thi nap hai
 * lan cung mot duong dan). Tra ve SO BIEN thay duoc (co the > max_plates: khi
 * do chi max_plates dau duoc ghi), hoac ma loi am.
 *
 * Bien NGOAI vung doc chi co box/quad/score/shape (zone_id = -1, text rong) -
 * dung de app theo doi doi tuong ma khong ton ~9ms/bien cho khau doc.
 *
 * KHAC ta_read_plate MOT DIEM: chuoi doc ra KHONG hop luat bien cua vung thi
 * tra ve RONG (text_conf = 0), khong tra chuoi rac. Ly do: ta_plate_t KHONG co
 * truong bao hop le (struct da co dinh tu v0.1, them truong la vo ABI), nen
 * neu tra "22" ra thi app khong con co so nao de vut - dung cai canh detector
 * dong khung khuon mat roi reader "doc" ra '2'/'22' da gap tren camera that.
 * Can chuoi tho de go loi thi dung ta_read_plate (co out-param format_valid).
 *
 * plate_color / text_color: DA CHAY TRONG C tu v0.8 (2026-08-12). Goi co muc
 * "color@<vung>" thi hai truong nay mang ma mau that (0 trang 1 vang 2 xanh
 * 3 do 4 luc); goi KHONG co muc do thi giu -1 (tuong thich nguoc).
 * Goi tinyanpr.sdk hien hanh DA CO muc mau - do 2026-09-11 tren 748 bien voi
 * quad cua chinh detector: 0.9987, rieng bien trang 702/702.
 * Kiem goi co muc mau khong: ta_co_color().
 * Toc do = ta_detect + ~9ms moi bien TRONG vung (xem ta_set_max_longest). */
TA_API int ta_process_frame(ta_ctx*, const unsigned char* rgb, int w, int h,
                            ta_plate_t* out, int max_plates);

#ifdef __cplusplus
}
#endif
#endif /* TA_ANPR_H */
