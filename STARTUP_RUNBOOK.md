# YasinHub — Startup Runbook

این فایل مرجع عملیاتی اجرای YasinHub است. هدف آن این است که در اجرای بعدی، مسیر نصب، استارت، احراز هویت Agent و بررسی واقعی Control Plane دوباره از صفر حدس زده نشود.

## 1. پیش‌نیازها

- Android/Termux یا Linux
- Python 3.9+
- مخزن‌ها در مسیر پیش‌فرض اکوسیستم:
  - `~/yasineco/YasinHub`
  - `~/yasineco/Yasin-agent`
- برای نصب وابستگی‌ها، اینترنت و دسترسی pip لازم است.

YasinHub به `pyyaml` و `rich` نیاز دارد و تست توسعه با `pytest` انجام می‌شود.

## 2. ورود به مخزن

```bash
cd ~/yasineco/YasinHub
```

بررسی:

```bash
git status
git branch --show-current
```

## 3. محیط Python

اگر محیط پروژه از قبل ساخته شده است، همان محیط را استفاده کنید. در صورت نیاز:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

برای توسعه/تست:

```bash
python -m pip install -e '.[dev]'
```

## 4. وابستگی و تست قبل از اجرا

```bash
python -m pytest tests/ -q
```

اگر تست‌ها سبز نیستند، قبل از ادامه علت را بررسی کنید و از اجرای نسخه‌ای که وضعیت نامشخص دارد خودداری کنید.

## 5. توکن Yasin-Agent

YasinHub برای کنترل Yasin-Agent از توکن مشترک استفاده می‌کند. فایل canonical توکن Hub:

```text
~/.yasinhub/yasin-agent.token
```

این فایل باید فقط برای کاربر قابل خواندن باشد. توکن را داخل Git، README یا این Runbook ثبت نکنید.

برای اجرای دستی Agent، متغیر زیر باید با توکن Hub یکسان باشد:

```bash
export YASIN_AGENT_SERVICE_TOKEN='YOUR_TOKEN'
```

اگر Hub قبلاً توکن را ساخته/ذخیره کرده است، از همان منبع استفاده کنید و توکن جدید نسازید مگر اینکه عمداً rotation انجام می‌دهید.

## 6. اجرای YasinHub API

از داخل مخزن:

```bash
cd ~/yasineco/YasinHub
python -m yasinhub.api.server
```

سرور باید روی این آدرس در دسترس باشد:

```text
http://127.0.0.1:8000
```

این ترمینال را باز نگه دارید.

## 7. Health check

در ترمینال دوم:

```bash
curl -i http://127.0.0.1:8000/api/health
```

انتظار:

```text
HTTP 200
{"service":"YasinHub","status":"ok"}
```

سپس:

```bash
curl -i http://127.0.0.1:8000/api/services
```

باید سرویس‌های اکوسیستم، از جمله `yasin-agent`، در خروجی دیده شوند.

## 8. اجرای Agent از طریق Hub — مسیر استاندارد

مسیر استاندارد Control Plane این است که Agent را خود YasinHub مدیریت کند:

```bash
cd ~/yasineco/YasinHub
python -m yasinhub.cli start yasin-agent
```

بررسی:

```bash
python -m yasinhub.cli status
```

و health/readiness واقعی Agent:

```bash
TOKEN="$(cat ~/.yasinhub/yasin-agent.token)"
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/health
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/ready
```

هر دو باید پاسخ موفق بدهند و `ready` برای readiness برابر `true` باشد.

## 9. PWA

مرورگر را روی این آدرس باز کنید:

```text
http://127.0.0.1:8000/dashboard/
```

بعد از هر عملیات Start/Stop/Restart، Dashboard و Status باید دوباره از API خوانده شوند.

## 10. تست واقعی Lifecycle

برای اطمینان از اینکه Control Plane فقط UI نیست، این چرخه را انجام دهید:

```bash
python -m yasinhub.cli stop yasin-agent
python -m yasinhub.cli status
python -m yasinhub.cli start yasin-agent
python -m yasinhub.cli status
python -m yasinhub.cli restart yasin-agent
python -m yasinhub.cli status
```

برای اثبات Restart واقعی، PID قبل و بعد را مقایسه کنید؛ Restart موفق باید Process جدید ایجاد کند.

## 11. اجرای دستی Agent — فقط برای عیب‌یابی

اگر لازم شد Agent مستقل از Hub اجرا شود:

```bash
cd ~/yasineco/Yasin-agent
export YASIN_AGENT_SERVICE_TOKEN='YOUR_TOKEN'
.venv/bin/python -m agent_platform.server
```

یا:

```bash
.venv/bin/yasin-agent-server
```

این حالت نباید هم‌زمان با Agent مدیریت‌شده توسط Hub اجرا شود؛ در غیر این صورت ممکن است Port 8080 یا Process تکراری ایجاد شود.

## 12. توقف کامل

ابتدا Agent را از طریق Hub متوقف کنید:

```bash
cd ~/yasineco/YasinHub
python -m yasinhub.cli stop yasin-agent
```

سپس Process مربوط به YasinHub API را با روش مناسب همان session متوقف کنید (`Ctrl+C` در ترمینالی که سرور در آن اجراست).

## 13. نکات مهم ثبت‌شده از اجرای واقعی

- پورت YasinHub API: `8000`
- پورت HTTP Yasin-Agent: `8080`
- Entry point معتبر Agent: `python -m agent_platform.server`
- Yasin-Agent نیازمند `YASIN_AGENT_SERVICE_TOKEN` است.
- Hub می‌تواند توکن Agent را از `~/.yasinhub/yasin-agent.token` مدیریت کند.
- کنترل سرویس از مسیر `/api/control/<service>/<action>` انجام می‌شود.
- Lifecycle سرویس با PID واقعی بررسی می‌شود؛ صرفاً نمایش وضعیت PWA معیار موفقیت نیست.
- بسته شدن Termux می‌تواند Processهای foreground را متوقف کند؛ پس بعد از باز کردن مجدد Termux، Health API را دوباره بررسی کنید.

## 14. چک‌لیست شروع سریع دفعه بعد

```text
[ ] cd ~/yasineco/YasinHub
[ ] git status
[ ] Python/venv آماده است
[ ] pip install -e . در صورت نیاز
[ ] pytest سبز
[ ] ~/.yasinhub/yasin-agent.token موجود است
[ ] python -m yasinhub.api.server
[ ] GET /api/health = 200
[ ] GET /api/services = 200
[ ] start yasin-agent
[ ] /v1/health = healthy
[ ] /v1/ready = ready
[ ] PWA /dashboard/ باز می‌شود
[ ] Start/Stop/Restart و تغییر PID قابل اثبات است
```

## 15. اصل عملیاتی

**اول Health، بعد Control، بعد PWA.**

اگر API بالا نیست، PWA ممکن است فقط از Cache نمایش داده شود و نباید آن را به‌عنوان سالم بودن Control Plane تلقی کرد.
