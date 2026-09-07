# YasinHub PWA — Mobile/Responsive Fix Report

- تاریخ: 2026-09-07 (UTC)
- مبنا: `docs/audits/yasinhub-pwa-mobile-audit.md` (حفظ شده، overwrite نشد)
- شاخه: `main` — baseline در `4670b3a`
- محدوده: فقط PWA/UI/Responsive — هیچ تغییری در Control Plane (API/Service Manager/Registry/PID/lifecycle/Yasin-Agent/Yasin-AI) ایجاد نشد.

---

## 1. Baseline

قبل از هر تغییر:

- `python3 -m pytest -q` → **523 passed** (~72s)
- زیرمجموعه PWA (10 فایل: foundation, ui_verification, ui20, controls, service_controls, observability, overview, integration, retirement_filter, phase4_pwa_control_plane) → **71 passed**
- Browser automation: در محیط موجود نیست (no chromium/chrome، ماژول playwright/selenium نصب نیست) — همان limitation گزارش audit.

---

## 2. Root Causes Confirmed

هر ۵ علت audit با source فعلی تطبیق و تأیید شد (شماره خط‌ها مربوط به قبل از fix):

| شناسه | تأیید |
|---|---|
| RC-1 سقف `height:64px` روی هدر wrapشونده + فرض `top:64px` | تأیید شد: `ui20.css:3` در برابر `style.css:4` + `style.css:10-11` |
| RC-2 مغلوب شدن padding موبایل توسط ui20 (ترتیب لود) | تأیید شد: `style.css:11` در برابر `ui20.css:4` + ترتیب `<link>` در `index.html:8-9` |
| RC-3 ماسک `overflow-x:hidden` | تأیید شد: `style.css:3` (+ مشارکت‌دهنده پنهان: `.skip-link{left:-9999px}` در `style.css:4`) |
| RC-4 ناهماهنگی breakpointها (800 در برابر 900/560) | تأیید شد: `style.css:11` در برابر `ui20.css:8-9`؛ ui20 هیچ قانون 800 نداشت |
| RC-5 سه‌بار `100vh` بدون `dvh` | تأیید شد: `style.css:5`، `style.css:11`، `ui20.css:4`؛ شمارش `dvh=0` |

---

## 3. Changes Made

### 3.1 — File: `dashboard/ui20.css` — Selector: `.app-header`

- Before: `.app-header{height:64px;padding:10px 22px;...}`
- After: `.app-header{min-height:64px;padding:10px 22px;...}`
- Reason: هدر در موبایل دو ردیفه می‌شود (RC-1)؛ ارتفاع ثابت باعث clipping/overlap بود. `min-height` ظاهر دسکتاپ را حفظ می‌کند و به layout اجازه می‌دهد ارتفاع واقعی را تعیین کند.

### 3.2 — File: `dashboard/style.css` — Selector: `.sidebar` (mobile drawer، داخل `@media(max-width:800px)`)

- Before: `.sidebar{position:fixed;top:64px;right:0;bottom:0;...z-index:40;...}`
- After: `.sidebar{position:fixed;top:0;right:0;bottom:0;...z-index:60;...}`
- Reason: حذف فرض hard-coded ارتفاع هدر (RC-1). دراور تمام‌قد و خارج از document flow است، پس باز/بسته شدن آن نه فضای اضافی در flow می‌سازد نه horizontal overflow؛ `z-index:60` آن را بالای هدر sticky (`z-index:50`) می‌نشاند. بستن همچنان با backdrop و انتخاب لینک (منطق موجود `app.js`) کار می‌کند.

### 3.3 — File: `dashboard/style.css` — Selector: `.nav-backdrop.visible`

- Before: `.nav-backdrop.visible{...position:fixed;inset:64px 0 0;...}`
- After: `.nav-backdrop.visible{...position:fixed;inset:0;...}`
- Reason: حذف فرض `64px`؛ backdrop تمام‌صفحه (`position:fixed` خارج از flow) عرض document را افزایش نمی‌دهد و با هر ارتفاع هدر سازگار است.

### 3.4 — File: `dashboard/ui20.css` — بلوک جدید `@media(max-width:800px)`

- Before: ui20 هیچ قانون 800px نداشت.
- After: `@media(max-width:800px){.main{padding:12px}}`
- Reason: رفع RC-2/RC-4 با اصلاح cascade به‌جای `!important`: شیت دیرتر (ui20) حالا با padding موبایل style.css موافقت می‌کند، پس قانون پایه دسکتاپ دیگر آن را override نمی‌کند. هیچ breakpoint جدیدی اضافه نشد (مجموع `@media` هر دو شیت ≤5).

### 3.5 — File: `dashboard/style.css` — Selector: `html,body` + `.skip-link`

- Before: `html,body{...overflow-x:hidden}` و `.skip-link{position:absolute;left:-9999px;...}`
- After: `html,body{...}` (بدون ماسک) و `.skip-link` با تکنیک clip (`width:1px;height:1px;clip-path:inset(50%)`، بازگشت کامل در `:focus`)
- Reason: رفع RC-3 از ریشه: عنصر off-screen در `-9999px` خودش به scrollable overflow کمک می‌کرد؛ حالا هر دو منبع ماسک/overflow حذف شدند و containment به اجزای درست سپرده شد (`table-wrap:overflow-x:auto`، `responsive-cards`، دراور fixed).

### 3.6 — File: `dashboard/style.css` (دو جا) + `dashboard/ui20.css` (یک جا) — Selector: `.app-shell`

- Before: `min-height:calc(100vh - 64px)` (سه occurrence)
- After: `min-height:calc(100vh - 64px);min-height:calc(100dvh - 64px)` (fallback قدیمی اول، modern دوم)
- Reason: رفع RC-5 به‌صورت semantic: فقط جایی که معنای «پر کردن viewport منهای هدر» را دارد (نه کورکورانه همه‌جا)؛ `100vh` برای browserهای قدیمی حفظ شد.

### 3.7 — File: `dashboard/ui20.css` — Selector: `.table-wrap` و `.hero` (≤560px)

- Before: `.table-wrap{overflow:auto;...}` و `.hero{padding:18px}` (بدون wrap)
- After: `.table-wrap{overflow-x:auto;...}` و `.hero{flex-wrap:wrap;padding:18px}`
- Reason: اسکرول تک‌محوره جدول‌ها (جلوگیری از nested vertical scroll) و جلوگیری از فشردگی hero در 360px.

### 3.8 — File: `dashboard/index.html` — viewport meta

- Before: `width=device-width, initial-scale=1`
- After: `width=device-width, initial-scale=1, viewport-fit=cover`
- Reason: مدیریت safe-area/notch در standalone PWA و APK آینده. رنگ‌های splash/theme عمداً دست نخورد (خارج از scope و نیازمند تصمیم design).

### 3.9 — File: `tests/test_pwa_responsive.py` (جدید، 12 تست)

- پوشش: no-fixed-header-height، wrap بدون ماسک، skip-link بدون overflow، دراور/backdrop بدون offset ثابت، padding موبایل در cascade، dvh+fallback، حداقلی breakpointها، گرید کارت‌ها + hero، containment جدول‌ها، viewport-fit، سلامت قوانین دسکتاپ، دست‌نخورده ماندن retired-service filtering و summary counters.

---

## 4. Tests

- Baseline قبل از fix: full **523 passed**؛ PWA **71 passed**.
- بعد از fix: `python3 -m pytest -q` → **535 passed** (523 قبلی + 12 جدید، بدون هیچ fail).
- PWA subset (11 فایل با تست جدید) → **83 passed**.
- هیچ تست موجودی شکسته نشد؛ هیچ فایل Control Plane لمس نشد (`git diff --stat` فقط dashboard CSS/HTML + تست جدید + همین گزارش را نشان می‌دهد).

---

## 5. Responsive Matrix

مقادیر Overflow/Header/Drawer/Cards از راستی‌آزمایی استاتیک معادل (بودجه عرض + قوانین cascade مؤثر) به‌دست آمد؛ رندر پیکسلی NOT VERIFIED (بخش 6).

| Viewport | Result | Overflow | Header | Drawer | Cards |
|---|---|---|---|---|---|
| 360x800 | PASS (static) | none expected: mask حذف شد، drawer خارج از flow، جدول containment داخلی، بودجه محتوا 336px و min-180px جا می‌شود | دو ردیفه بدون clipping (min-height) | full-height، بدون gap/overflow | 2 ستونه ~162px |
| 375x812 | PASS (static) | none expected | دو ردیفه بدون clipping | full-height | 2 ستونه ~170px |
| 390x844 | PASS (static) | none expected | دو ردیفه بدون clipping | full-height | 2 ستونه ~177px |
| 412x915 | PASS (static) | none expected | دو ردیفه بدون clipping | full-height | 2 ستونه ~188px |
| 768x1024 | PASS (static) | none expected | wrap در صورت نیاز | full-height + کارت 3 ستونه (قابل پیش‌بینی) | 3 ستونه ~240px |
| 1366x768 | PASS (static) | none expected | تک‌ردیفه 64px | استاتیک 220px | 5 ستونه ~254px |

دستور قابل تکرار (بدون مرورگر): محاسبه بودجه `content = vw - 2*pad` با `pad=12` در ≤800 و `24` در غیر آن + بازرسی cascade قوانین بالا؛ اسکریپت معادل موقت بود و پس از اجرا حذف شد.

---

## 6. Browser Verification

**NOT VERIFIED** — Reason: browser automation unavailable (no chromium/chrome binary؛ ماژول playwright/selenium نصب نیست). هیچ ادعای pixel-level انجام نشد. ماتریس بخش 5 صرفاً static-equivalent است.

---

## 7. Regression

- Desktop (1366x768 و بزرگ‌تر): قوانین سایدبار استاتیک 220px، هدر sticky تک‌ردیفه، کارت 5 ستونه، جدول و کنترل‌ها دست نخورده‌اند (تست `test_desktop_layout_rules_untouched` + سوئیت کامل سبز).
- Control Plane/API/Registry/PID/lifecycle/Yasin-Agent/Yasin-AI: هیچ فایلی در این حوزه‌ها در diff نیست.
- retired-service filtering و summary counters: کد (`buildServiceStates`/`visibleProjects`/`summarizeProjects`/`__yasinhubServiceStates`/`enabled === false`) دست نخورده و تست‌های `test_pwa_retirement_filter` + تست جدید سبز‌اند.

---

## 8. APK Readiness

**READY** — با قید limitation مرورگر (PASS_WITH_LIMITATION): همه root causeهای CSS مؤثر بر WebView (هدر/دراور، padding، ماسک overflow، dvh، notch) رفع شدند. پیش از بیلد نهایی APK یک راستی‌آزمایی روی دستگاه واقعی/امولاتور برای 360x800 توصیه می‌شود.

---

## 9. Final Verdict

**PASS_WITH_LIMITATION** (limitation: browser pixel verification not available in this environment)
