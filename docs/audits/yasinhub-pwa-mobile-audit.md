# YasinHub PWA — Forensic Audit: فضای خالی موبایل و رفتار متفاوت Desktop/Mobile

- تاریخ: 2026-09-07 (UTC)
- شاخه/وضعیت: `main` در کامیت `4670b3a` (Merge branch 'fix/registry-wiring-repair')
- قانون مأموریت: فقط Audit و Report — هیچ فایل production تغییر نکرد، هیچ commit/PR ساخته نشد.
- مسیر گزارش درخواستی (`Yasin-Operations/reports/active/yasinhub-pwa-mobile-audit/latest.md`) در repository وجود ندارد
  (دایرکتوری `Yasin-Operations/` اصلاً موجود نیست). نزدیک‌ترین مسیر canonical موجود `docs/audits/` است
  (محل گزارش‌های `FINAL_*`)، پس گزارش اینجا ثبت شد: `docs/audits/yasinhub-pwa-mobile-audit.md`.
- قرارداد صداقت: هر یافته‌ای که evidence استاتیک (کد) دارد VERIFIED-BY-CODE، و هر چیز نیازمند رندر زنده
  که بدون مرورگر قابل اندازه‌گیری نبود NOT VERIFIED ذکر شده است.

---

## 1. Executive Summary

مشکل گزارش‌شده (فضای خالی/ناخواسته در PWA موبایل + رفتار متفاوت layout هنگام resize در PC) ریشه در
**تعارض cascade بین دو stylesheet** دارد که با ترتیب بارگذاری `style.css` و سپس `ui20.css`
(`dashboard/index.html` خطوط 8-9) فعال می‌شود، به‌علاوه **فرض ثابت بودن ارتفاع هدر (64px)**
در سه‌جا (هدر، دراور، backdrop) و استفاده از **`100vh` بدون `dvh` fallback**.

سه commit اخیر (`1690cbe`، `435a183`، `a5a3d22`) هرکدام یک علامت را درست کردند (دراور LTR، overflow هدر،
قانون sidebar تکراری) اما تعارض‌های باقی‌مانده — مخصوصاً **بردِ padding موبایل توسط ui20**
و **سقف `height:64px` روی هدر wrapشونده** — همچنان روی viewportهای باریک فعال‌اند.
JavaScript هیچ listener وابسته به viewport ندارد (بدون `matchMedia`/`innerWidth`/`resize`)،
اما دو MutationObserver ستون/نوار ابزار به DOM اضافه می‌کنند که در breakpointهای باریک اثر overflow می‌سازد.

خلاصه احکام:

- Root Cause اصلی (با evidence): تعارض `height:64px` (ui20) در برابر `flex-wrap` هدر (style) + فرض `top:64px`
  برای sidebar/backdrop، و override شدن `padding:12px` موبایل توسط padding پایه ui20.
- تست‌های موجود: PWA ‏71/71 پاس، سوئیت کامل ‏523/523 پاس.
- متریک‌های زنده DOM (`scrollWidth`/`clientWidth`/عناصر بیرون‌زده) بدون browser automation قابل اندازه‌گیری نبود: NOT VERIFIED.
- حکم نهایی: **NEEDS_FIX** — برای APK باید اول responsive حل شود.

---

## 2. Reproduction

| Viewport | مشاهده استاتیک (پیش‌بینی از cascade) | وضعیت رندر زنده |
|---|---|---|
| 360x800 | دراور فعال (fixed/top:64px)؛ کارت‌ها 2 ستونه؛ padding اصلی عملاً `24px clamp(...)` می‌ماند نه `12px`؛ هدر wrap مجاز اما سقف 64px → سرریز داخلی/ناهمترازی backdrop | NOT VERIFIED (بدون مرورگر) |
| 375x812 | مشابه 360 | NOT VERIFIED |
| 390x844 | مشابه 360 | NOT VERIFIED |
| 412x915 | مشابه 360 | NOT VERIFIED |
| 768x1024 | دراور فعال + کارت‌ها 3 ستونه (breakpoint های 800 و 900 از هم جدا هستند)؛ همین ترکیب، «رفتار متفاوت» هنگام resize است | NOT VERIFIED |
| 1366x768 | سایدبار استاتیک 220px؛ کارت‌ها 5 ستونه؛ هدر تک‌ردیفه و سازگار | NOT VERIFIED |

- آیا روی Desktop هم قابل reproduction است؟ از نظر استاتیک **بله**: با باریک کردن پنجره PC به زیر 800px
  همان قوانین موبایل (دراور fixed، app-shell بلوکی، کارت 3/2 ستونه) فعال می‌شود؛ و ناهماهنگی breakpointها
  (800 در برابر 900/560) دقیقاً هنگام resize حس می‌شود. رندر پیکسلی آن NOT VERIFIED است.
- نکته تاریخی: commit ‏`a5a3d22` شرح می‌دهد که قبل از آن، هدر بدون wrap کل صفحه را افقی اسکرول می‌داد
  و همین، علامت «blank space کنار دراور + اسکرول افقی» را می‌ساخت. آن علت خاص با `flex-wrap` و
  `overflow-x:hidden` پوشانده شد، اما تعارض ارتفاع 64px همچنان باقی است (بخش 3، RC-1).

---

## 3. Root Cause

### RC-1 — سقف `height:64px` روی هدر wrapشونده + فرض `top:64px` در دراور/backdrop (High)

- File: `dashboard/ui20.css` و `dashboard/style.css`
- Selector / Function: `.app-header` / `.sidebar` / `.nav-backdrop.visible`
- Line:
  - `dashboard/ui20.css:3` — `.app-header{height:64px;...}` (بدون هیچ media override برای هدر در خطوط 8-9)
  - `dashboard/style.css:4` — `.app-header{display:flex;flex-wrap:wrap;...position:sticky;...}`
  - `dashboard/style.css:11` — `.sidebar{...top:64px;...}` و `dashboard/style.css:10` — `.nav-backdrop.visible{...inset:64px 0 0;...}`
- Problem: هدر در viewport باریک به دو ردیف wrap می‌شود (قصد درست `a5a3d22`)، اما `height:64px` از ui20
  (که دیرتر لود می‌شود و specificity برابر دارد) ارتفاع را قفل می‌کند → محتوای ردیف دوم بیرون می‌زند یا بریده می‌شود.
  همزمان دراور و backdrop فرض می‌کنند هدر دقیقاً 64px است؛ اگر هدر بلندتر شود، بالای دراور/backdrop شکاف
  (blank gap) می‌ماند و انجمن آن با «فضای خالی موبایل» سازگار است.
- Evidence: خروجی static-analyzer موقت (حذف‌شده پس از اجرا):
  `ui20 .app-header height rule: True`، `style .app-header flex-wrap: True`،
  `ui20 has @media 800 sidebar rule: False` (یعنی هیچ اصلاحیه موبایل برای هدر در ui20 نیست).
  رندر پیکسلی: NOT VERIFIED.

### RC-2 — override شدن padding موبایل `.main` توسط قانون پایه ui20 (High)

- File: `dashboard/style.css` و `dashboard/ui20.css`
- Selector: `.main`
- Line:
  - `dashboard/style.css:11` — `@media(max-width:800px){... .main{width:100%;padding:12px;...} ...}`
  - `dashboard/ui20.css:4` — `.main{padding:24px clamp(14px,3vw,34px) 44px}` (بدون media، در شیت دیرتر)
- Problem: specificity هر دو `(0,1,0)` و برابر است؛ ترتیب سند (`style.css` قبل از `ui20.css` طبق
  `dashboard/index.html:8-9`) یعنی در ≤800px قانون پایه ui20 برنده می‌شود و padding موبایل عملاً
  همان `24px clamp(...) 44px` می‌ماند، نه `12px` موردنظر. نتیجه: حاشیه‌های جانبی اضافی، باریک شدن محتوا،
  و فشار بیشتر روی جدول‌ها/کارت‌ها در موبایل. (`width:100%` چون رقیبی در ui20 ندارد اعمال می‌شود؛ فقط padding مغلوب است.)
- Evidence: ترتیب `<link>` در `dashboard/index.html:8-9` + متن هر دو قانون (بالا). تحلیل cascade طبق CSS spec.
  رندر پیکسلی: NOT VERIFIED.

### RC-3 — ماسک شدن overflow افقی با `overflow-x:hidden` به‌جای رفع علت (Medium — تشدیدکننده)

- File: `dashboard/style.css`
- Selector: `html,body`
- Line: `dashboard/style.css:3` — `html,body{...overflow-x:hidden}`
- Problem: اضافه‌شده در `a5a3d22` به‌عنوان «backstop دفاعی». overflow واقعی (جدول nowrap، کنترل‌های 180px،
  هدر) را clip می‌کند؛ علامت «اسکرول افقی کل صفحه» پنهان می‌شود اما محتوای بریده‌شده/فضای مرده می‌ماند
  و دیباگ علت اصلی سخت‌تر می‌شود.
- Evidence: diff `a5a3d22` (خط `overflow-x:hidden` اضافه شد) + `grep -c` جدول‌ها (`white-space:nowrap` در دو فایل).

### RC-4 — ناهماهنگی breakpointها: دراور در 800، گریدها در 900/560 (Medium — علت «رفتار متفاوت هنگام resize»)

- File: `dashboard/style.css:11` در برابر `dashboard/ui20.css:8-9`
- Problem: سایدبار در ≤800px به دراور fixed تبدیل و `.app-shell` از flex به block می‌رود،
  اما گرید کارت‌ها در 900 (3 ستونه) و 560 (2 ستونه) می‌شکند. پس بازه 561-800 و 801-900 ترکیب‌های متفاوت
  (دراور+3ستونه / استاتیک+3ستونه) می‌سازند و هنگام resize روی PC layout «می‌پرد». ui20 هیچ قانون 800 ندارد
  (تأیید با analyzer: `ui20 has @media 800 sidebar rule: False`) چون بلاک 800 آن در `1690cbe` حذف شد.
- Evidence: متن media queryها + جدول per-viewport بخش 8. پیکسل‌به‌پیکسل: NOT VERIFIED.

### RC-5 — `min-height:calc(100vh - 64px)` بدون `dvh` (Medium-High برای موبایل/APK)

- File: هر دو stylesheet
- Line: `dashboard/style.css:5`، `dashboard/style.css:11`، `dashboard/ui20.css:4`
- Problem: سه occurrence از `100vh`، صفر occurrence از `100dvh`/`100svh` (شمارش analyzer: `100vh=3, 100dvh=0`).
  در مرورگر موبایل با toolbar جمع‌شونده و در WebView، `100vh` ناحیه زیر chrome را هم حساب می‌کند →
  اسکرول عمودی اضافه / نوار خالی پایین. ترکیب با RC-1 (هدر واقعی بلندتر از 64px) خطای `calc` را بزرگ‌تر می‌کند.
- Evidence: شمارش بالا. اندازه‌گیری روی دستگاه واقعی: NOT VERIFIED.

---

## 4. Secondary Issues

1. `.hero` بدون `flex-wrap`/`column` در موبایل (`dashboard/ui20.css:5`؛ media ‏560 فقط padding و min-width را کم می‌کند) → در 360px تیتر و stat کنار هم فشرده می‌شوند. (Medium)
2. `.data-table th/td{white-space:nowrap}` در هر دو فایل (`style.css:7`، `ui20.css:6`) → جدول‌ها ذاتاً عریض‌اند؛
   نجات موبایل فقط به تبدیل `responsive-cards` در `style.css:11` وابسته است. هر جدولی که آن کلاس را نداشته باشد
   در موبایل اسکرول افقی داخلی می‌سازد. (Medium)
3. `.table-wrap` در ui20 `overflow:auto` است (`ui20.css:6`) و روی `overflow-x:auto` استایل (`style.css:7`) سوار می‌شود →
   اسکرول دو‌محوره تودرتو در جدول‌ها محتمل است. (Low-Medium)
4. تزریق `min-width:180px` در دو جا: `dashboard/service-controls.js:121` (استایل glass با `!important`) و
   `dashboard/ui20.css:6` (`.table-search{flex:1;min-width:180px}`) → در 360px فشار افقی داخل toolbar/سلول کنترل.
   در ≤560px ورودی‌ها `width:100%` می‌شوند (`ui20.css:9`) پس toolbar بلند می‌شود و محتوای پایین‌تر را هل می‌دهد
   (حس «خالی بودن بالای صفحه»). (Medium)
5. `viewport` بدون `viewport-fit=cover` (`dashboard/index.html:5`: فقط `width=device-width, initial-scale=1`) →
   در دستگاه‌های notch و حالت standalone حاشیه unsafe مدیریت نشده. (Low-Medium، برای APK مهم)
6. ناهماهنگی رنگ splash: `manifest.json:7` ‏`background_color #ffffff` در برابر `index.html:6` ‏`theme-color #03040a`
   و `manifest theme_color #0f9d58` → فلش سفید هنگام launch. آیکون‌ها و `start_url` با مسیر مطلق `/dashboard/...`
   (`manifest.json:3-4,12-16`) → شکنندگی در subpath. (Low)
7. `.event-item{grid-template-columns:48px 1fr auto}` (`style.css:9`) و `.service-status-main` بدون wrap در ui20 پایه
   (فقط `style.css:11` در موبایل column می‌کند؛ ui20 پایه `justify-content:space-between` دارد) → ریسک فشردگی در 360px. (Low)
8. Service Worker (`dashboard/sw.js:63-82`): network-first برای JS/CSS تصمیم درستی است (جلوگیری از shell کهنه)،
   اما `style.css?v=2` نسخه‌دار و `ui20.css` بدون نسخه کش می‌شود (`sw.js:8-9`) → ریسک ناهمگامی دو شیت پس از دیپلوی. (Low)
9. `body{direction:rtl}` مضاعف (`ui20.css:3`) روی `html dir=rtl` (`index.html:2`) بی‌ضرر ولی افزونه؛ تاریخچه نشان می‌دهد
   دراور قبل از `435a183` با `translateX(-100%)` سمت چپ (LTR) بود و برای RTL غلط بود — الان درست است
   (`translateX(100%)` به سمت راست). (اطلاعاتی)

---

## 5. Desktop vs Mobile

- Desktop عریض (>900px): سایدبار استاتیک 220px در flex-shell؛ کارت‌ها 5 ستونه (قانون ui20 برنده)؛
  هدر تک‌ردیفه و هم‌ارتفاع 64px با `top` دراور (دراور اصلاً fixed نیست) → سازگار.
- تبلت/موبایل (≤800px): سایدبار fixed/right با `translateX(100%)`؛ `.app-shell` بلوکی؛ کارت‌ها 3 ستونه (561-800)
  یا 2 ستونه (≤560)؛ هدر wrapشونده ولی سقف 64px؛ backdrop از 64px شروع می‌شود؛ padding اصلی عملاً همان دسکتاپ می‌ماند (RC-2).
- نقطه پرش 800px: هنگام resize روی PC، موقعیت سایدبار (static↔fixed)، display شل (flex↔block)، و چیدمان جدول
  (table↔responsive-cards) همزمان عوض می‌شود در حالی که گرید کارت‌ها در 900/560 می‌شکند → حس «رفتار متفاوت».
- موبایل واقعی vs شبیه‌سازی دسکتاپ: `100vh` در Chrome موبایل داینامیک است ولی در resize دسکتاپ ثابت؛ پس نوار خالی
  عمودی (RC-5) و notch (Secondary-5) فقط روی دستگاه واقعی دیده می‌شوند — بدون دستگاه/امولاتور NOT VERIFIED.

---

## 6. CSS Analysis

| موضوع | نتیجه |
|---|---|
| overflow | `overflow-x:hidden` روی html/body (ماسک)؛ `table-wrap` دوگانه (`overflow-x:auto` مغلوب `overflow:auto`)؛ هدر wrapشده با سقف ارتفاع → سرریز داخلی |
| width | `width:min(240px,82vw)` دراور صحیح؛ `width:100%` موبایل `.main` اعمال می‌شود؛ `min-width:180px`‌ها فشار افقی می‌سازند |
| height | تعارض کلیدی: `height:64px` (ui20:3) vs هدر wrap (style:4)؛ فرض `top/inset:64px` در دراور/backdrop |
| min-height | `calc(100vh-64px)` در 3 جا؛ بدون dvh |
| vh/dvh | `100vh=3`، `100dvh=0`، `100svh=0` — VERIFIED-BY-CODE |
| flex | دو فلسفه گرید: style‏ `auto-fill/minmax(140px)` مغلوب ui20‏ `5/3/2 ثابت`؛ `.hero` بدون wrap |
| grid | کارت‌ها/سرویس‌ها/detail-grid همه در ui20 بازتعریف شده‌اند و برنده‌اند |
| position | sticky هدر + fixed دراور/backdrop/toast؛ ترکیب sticky-header عریض‌شده قبلاً کل صفحه را اسکرول می‌داد (شرح `a5a3d22`) |
| sticky/fixed | backdrop و دراور به 64px گره خورده‌اند (شکننده با RC-1) |
| media queries | فقط `800` (style) در برابر `900/560` (ui20)؛ هیچ `800` در ui20 نیست |
| breakpoints | ناهماهنگی 800/900/560 = علت پرش هنگام resize |
| sidebar | الان RTL-correct؛ تاریخچه LTR-bug قبل از `435a183` |
| header | RC-1؛ همچنین `.brand-tag` در موبایل مخفی می‌شود (هر دو شیت) — خواسته‌شده، نه باگ |

---

## 7. JavaScript Analysis

- هیچ منطق وابسته به viewport وجود ندارد: جست‌وجوی `innerWidth|matchMedia|resize|visualViewport|scrollWidth|clientWidth`
  در `app.js`، `service-controls.js`، `ui20.js`، `chat.js`، `js/*` صفر نتیجه داد (analyzer: False). **VERIFIED-BY-CODE.**
- تغییرات DOM که غیرمستقیم روی layout باریک اثر می‌گذارند:
  - `app.js:273` — ساخت `.nav-backdrop` و toggle کلاس `open`/`visible` (wireChrome)؛ `app.js:290` — بستن دراور هنگام تغییر route.
  - `app.js:110-123` — درج سطر `#live-meta.meta-row` بعد از heading (فضای عمودی اضافه).
  - `service-controls.js:114` — افزودن `<td data-label="کنترل">` + `<th>` کنترل (`:95`) به جدول سرویس‌ها؛ با `min-width:180px` تزریقی (`:121`) جدول را عریض‌تر می‌کند.
  - `service-controls.js:125` و `ui20.js:33` — دو MutationObserver مستقل که روی هر رندر کل محتوا را دوباره decorate/translate می‌کنند
    (ریسک دوباره‌کاری و reflow، نه علت مستقیم blank space).
  - `ui20.js:25-26` — درج `.table-toolbar` (search با `min-width:180px`) قبل از هر جدول.
  - `chat.js:98` — `dialog.showModal()` مودال است و روی layout صفحه اثر نمی‌گذارد.
- `d146544` فقط منطق شمارنده/فیلتر (`buildServiceStates`/`summarizeProjects` در `app.js:45-92`) اضافه کرد؛ اثر layout ندارد.

---

## 8. Evidence

- Commitها (خوانده‌شده با `git show`):
  - `1690cbe` — حذف بلاک `@media 800px` سایدبار از ui20 + حذف `display:grid` از toast؛ تک‌فایلی (`ui20.css`).
  - `435a183` — دراور RTL (`top:64px;right:0;translateX(100%)`، `width:min(240px,82vw)`) + `app-shell:block` در موبایل + `inset:64px` برای backdrop (`style.css`، 8 خط).
  - `a5a3d22` — `flex-wrap` هدر + `overflow-x:hidden` (`style.css`)، حذف قانون `.sidebar{width:240px...}` تکراری از ui20، فیکس assertion تست (`tests/test_pwa_ui_verification.py`).
  - `d146544` — شمارنده‌های visible-only + `window.__yasinhubServiceStates` (`app.js`)؛ بدون تغییر layout.
  - diff `‏a5a3d22..HEAD` فقط بازنشستگی سرویس‌هاست (app.js/service-controls.js/js/api.js) — ربطی به layout ندارد.
- Static analyzer موقت (در `/data/data/com.termux/files/usr/tmp/opencode/` ساخته، اجرا و سپس حذف شد — هیچ اثری در production نماند):
  شمارش‌ها و جدول per-viewport بخش 2 خروجی مستقیم آن است.
- دستورهای قابل تکرار:
  - `grep -n -E "100vh|100dvh|overflow|position|translateX|inset:|min-height|flex-wrap|@media" dashboard/style.css dashboard/ui20.css`
  - `grep -n -E "innerWidth|matchMedia|resize|visualViewport|scrollWidth|clientWidth" dashboard/app.js dashboard/service-controls.js dashboard/ui20.js dashboard/chat.js dashboard/js/views.js` (خروجی خالی = بدون منطق viewport)
  - `python3 -m pytest tests/test_pwa_foundation.py tests/test_pwa_ui_verification.py tests/test_pwa_ui20.py tests/test_pwa_controls.py tests/test_pwa_service_controls.py tests/test_pwa_observability.py tests/test_pwa_overview.py tests/test_pwa_integration.py tests/test_pwa_retirement_filter.py tests/test_phase4_pwa_control_plane.py -q` → ‏71 passed
  - `python3 -m pytest -q` → ‏523 passed (71.98s)
- محدودیت: browser automation در محیط موجود نیست (`which chromium/chrome` منفی، ماژول `playwright`/`selenium` نصب نیست)؛
  پس `scrollWidth`/`clientWidth`/عناصر بیرون‌زده/اسکرول واقعی اندازه‌گیری نشد — صراحتاً NOT VERIFIED.

---

## 9. Severity

| شناسه | مشکل | شدت |
|---|---|---|
| RC-1 | سقف height:64px روی هدر wrapشونده + ناهمترازی دراور/backdrop | High |
| RC-2 | مغلوب شدن padding موبایل .main توسط ui20 | High |
| RC-3 | ماسک overflow-x:hidden | Medium |
| RC-4 | ناهماهنگی breakpointهای 800/900/560 | Medium |
| RC-5 | 100vh بدون dvh | Medium (برای APK: High) |
| S-1 | hero بدون wrap | Medium |
| S-2 | nowrap جدول‌ها | Medium |
| S-4 | min-width:180px تزریقی/toolbar | Medium |
| S-3/S-5/S-6/S-7/S-8 | overflow دوگانه، viewport-fit، splash، event-grid، SW versioning | Low (±Medium برای APK در S-5) |

---

## 10. Recommended Fix

(فقط پیشنهاد — هیچ‌کدام اعمال نشد.)

1. تک‌منبعی کردن هدر: حذف `height:64px` ثابت از ui20 یا تبدیل به `min-height:64px` + `align-content:flex-start`؛
   و `top` دراور/backdrop را از ارتفاع واقعی هدر بگیرد (مثلاً CSS var `--header-h` که با wrap به‌روز شود، یا sticky-offset داینامیک).
2. رفع cascade موبایل: یا padding موبایل `.main` را به ui20 منتقل کنند، یا specificity/order را طوری تنظیم کنند که
   قانون ≤800px برنده شود (مثلاً `@media` معادل در ui20، یا کاهش padding پایه به `clamp` کوچک‌تر در موبایل).
3. یکپارچه‌سازی breakpointها (پیشنهاد: 800 واحد برای دراور + گرید، یا انتقال کامل گریدها به style با auto-fill) تا resize نپرد.
4. `min-height:calc(100dvh - var(--header-h))` با fallback `100vh` برای `.app-shell` (هر دو شیت).
5. `viewport-fit=cover` + `env(safe-area-inset-*)` برای standalone/APK؛ یکدست‌سازی `theme-color`/`background_color`.
6. `.hero{flex-wrap:wrap}` (یا column در ≤560)؛ بازبینی `white-space:nowrap` (حذف در ستون Message با ellipsis واقعی)؛
   کاهش `min-width`های 180px در موبایل؛ `overflow-x:clip` به‌جای hidden پس از رفع علت‌ها.
7. تست رگرسیون: Playwright/Chromium با همان 6 viewport +断言 روی `document.scrollingElement.scrollWidth <= innerWidth`
   و اسکرین‌شات diff، چون сейчас هیچ تست layout واقعی وجود ندارد (تست‌های فعلی فقط presence断言 روی رشته‌ها هستند).

---

## 11. APK Readiness

**آماده نیست.** PWA فعلی برای تبدیل به APK باید ابتدا مشکلات responsive حل شود: هدر/دراور ناهمتراز (RC-1)،
padding مغلوب (RC-2)، `100vh` بدون dvh (RC-5)، نبود `viewport-fit=cover`، و اسکرول‌های افقی داخلی جدول‌ها —
همه در WebView تمام‌صفحه با gesture-nav و notch تشدید می‌شوند. WebView خطای `overflow-x:hidden` را هم پنهان می‌کند،
پس بریدگی محتوا دیر کشف می‌شود.

---

## 12. Final Verdict

**NEEDS_FIX**
