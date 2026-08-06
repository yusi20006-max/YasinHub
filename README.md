# YasinHub

یک CLI ساده‌ی وضعیت برای اکوسیستم Yasin — نه یک داشبورد سنگین، فقط
پاسخ سریع به «چی الان روشنه، آخرین اجرا کِی و چطور بوده».

## نصب

```bash
pip install -r requirements.txt  # (فعلاً فقط pytest برای تست لازم است)
```

## استفاده

هر پروژه (بات ایتا، YasinRelay و ...) در انتهای اجرای خودش این را
صدا می‌زند تا وضعیتش ثبت شود:

```python
from yasinhub.status_store import write_status

write_status("yasinrelay", success=True, message="۱۲ پست منتشر شد")
```

و برای دیدن وضعیت کلی:

```bash
python3 -m yasinhub.cli status
```

خروجی نمونه:
```
eitaa_news_v2  پروسس: در حال اجرا   آخرین اجرا: 2026-07-26T09:00:00+00:00 (موفق)
yasinrelay     پروسس: متوقف        آخرین اجرا: 2026-07-26T08:00:00+00:00 (موفق)
               پیام: ۱۲ پست منتشر شد
yasin-agent    پروسس: —            آخرین اجرا: بدون گزارش
```

## اجرای تست‌ها

```bash
python3 -m pytest tests/ -v
```

## ساختار

```
yasinhub/
├── yasinhub/
│   ├── __init__.py
│   ├── status_store.py     # خواندن/نوشتن فایل‌های وضعیت JSON
│   ├── process_checker.py   # چک زنده‌بودن پروسس با pgrep -f
│   ├── registry.py          # فهرست پروژه‌های تحت نظارت
│   ├── report.py            # ترکیب فایل وضعیت + چک پروسس
│   └── cli.py                # python -m yasinhub.cli status
├── tests/
│   └── test_yasinhub.py
├── conftest.py
└── README.md
```

## اضافه کردن پروژه‌ی جدید

در `yasinhub/registry.py`، به `DEFAULT_PROJECTS` یک `ProjectEntry`
اضافه کن:

```python
ProjectEntry(name="new_project", process_pattern="new_project.py", description="توضیح کوتاه")
```

اگر پروژه پروسس دائمی ندارد (مثل yasin-agent که فقط on-demand اجرا
می‌شود)، `process_pattern=None` بگذار.
