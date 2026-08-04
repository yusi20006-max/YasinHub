# YasinHub

هاب سبک برای مانیتورینگ وضعیت پروژه‌های اکوسیستم Yasin.

## نصب
```bash
pip install -r requirements.txt

وابستگی‌های فعلی:
- `rich` برای نمایش CLI
- `pyyaml` برای پیکربندی
- `pytest` برای تست

یکپارچه‌سازی با Yasin-Relay اختیاری است. اگر SDK مربوط به Relay در محیط نصب
نباشد، بخش `RelayIntegration` به‌صورت graceful degraded کار می‌کند.

## استفاده

هر پروژه (بات ایتا، YasinRelay و ...) در انتهای اجرای خودش این را
در فایل وضعیت ثبت می‌کند و بعد YasinHub آن را نمایش می‌دهد.

bash
python3 -m yasinhub.cli status

## اجرای تست‌ها

bash
python3 -m pytest -v

## قرارداد RelayIntegration

کلاس `RelayIntegration` سه رفتار عمومی دارد:
- `connect()`: تلاش برای برقراری ارتباط با کلاینت Relay
- `get_status()`: دریافت وضعیت Relay به‌صورت `dict`
- `handle_event(event_type, payload)`: ارسال/پردازش رویداد در Relay

## وضعیت انتشار

نسخه فعلی: `1.0.0`
