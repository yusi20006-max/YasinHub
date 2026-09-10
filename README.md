# YasinHub

یک Control Plane سبک برای اکوسیستم Yasin؛ مرجع کنترل lifecycle، وضعیت واقعی سرویس‌ها و PWA عملیاتی.

## نصب

```bash
pip install -r requirements.txt
```

## اجرای وضعیت

```bash
python3 -m yasinhub.cli status
```

## اجرای canonical روی Termux / Android ARM64

YasinHub از **پورت اختصاصی 7000** استفاده می‌کند و `yasinhub.startup` لانچر رسمی و non-interactive برای شروع آن است.

### Sync + Start

```bash
cd ~/YasinEco/YasinHub

git fetch origin
git checkout main
git reset --hard origin/main
git clean -fd

export YASIN_ECOSYSTEM_ROOT="$HOME/YasinEco"
export PYTHONPATH=.

.venv/bin/python -m yasinhub.startup
```

لانچر startup قبل از شروع، پورت `7000` را بررسی می‌کند:

- اگر پورت آزاد باشد، YasinHub را start می‌کند.
- اگر یک YasinHub قبلی پورت را گرفته باشد، آن را به‌صورت graceful متوقف می‌کند، آزادشدن پورت را تأیید می‌کند و نمونه جدید را start می‌کند.
- اگر مالک پورت YasinHub نباشد یا هویت مالک قابل تأیید نباشد، **FAIL CLOSED** انجام می‌شود و هیچ process نامرتبطی kill نمی‌شود.
- پس از start، PID، هویت process، listening port و health باید قابل تأیید باشند.
- مسیر عادی از `SIGTERM` استفاده می‌کند و blind `kill -9` انجام نمی‌دهد.
- این startup کاملاً non-interactive است و برای Termux/Android ARM64 طراحی شده است.

**نکته:** پیام `YasinHub startup ok: action=started pid=<PID> port=7000` فقط پیام موفقیت launcher است. Launcher می‌تواند پس از start شدن Hub از ترمینال خارج شود؛ معیار زنده‌بودن Hub، پاسخ health روی پورت `7000` است.

### بررسی سریع پس از Start

```bash
curl -sS http://127.0.0.1:7000/api/health
```

پاسخ مورد انتظار:

```json
{
  "service": "YasinHub",
  "status": "ok"
}
```

PWA:

```text
http://127.0.0.1:7000/dashboard/
```

Version/build:

```bash
curl -sS http://127.0.0.1:7000/api/version
```

## Lifecycle authority

YasinHub تنها Control Plane و مرجع lifecycle/PID اکوسیستم است. PWA نباید مستقیماً processها را کنترل کند و سرویس‌ها نباید یک Control Plane دوم ایجاد کنند.

برای lifecycle سرویس‌ها از Hub استفاده کنید:

```bash
cd ~/YasinEco/YasinHub
export YASIN_ECOSYSTEM_ROOT="$HOME/YasinEco"
export PYTHONPATH=.

python -m yasinhub.cli status
python -m yasinhub.cli start yasinrelay
python -m yasinhub.cli status
```

## Port assignments

| Service | Port |
|---|---:|
| YasinHub | 7000 |
| Yasin-Agent | 7002 |
| YasinFeed | 7004 |
| YasinRelay | portless unless a proven HTTP runtime exists |
| Yasin-AI | portless unless a proven HTTP runtime exists |
| YasinPress | portless unless a proven HTTP runtime exists |
| Yasin-Coder | portless unless a proven HTTP runtime exists |

## Termux compatibility

Termux روی Android ARM64 هدف first-class است. Runtime، process identity، lifecycle و health باید با evidence واقعی روی Termux تأیید شوند.

## Tests

```bash
python3 -m pytest tests/ -v
```

## ساختار اصلی

```text
yasinhub/
├── api/
├── startup.py          # canonical self-healing startup launcher
├── cli.py
├── registry.py
├── report.py
├── process_checker.py
└── status_store.py
```

## Security

- `shell=False` برای lifecycle commands.
- عدم چاپ یا commit کردن secrets.
- `.env` محلی و ترجیحاً با permission `0600`.
- هویت process قبل از اعلام موفقیت بررسی می‌شود.
- مالک ناشناس پورت هرگز kill نمی‌شود.
- YasinHub تنها lifecycle/PID authority است.
