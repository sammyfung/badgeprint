# Raspberry Pi OS — Auto-start Setup

Runs two systemd services at boot:

- **badgeprint** — Django app served by gunicorn on port 8000
- **checkin-scanner** — `manage.py checkin_scanner` reading from the barcode scanner (requires TTY)

> **Headless / SSH / no-TTY Linux?**  Use `checkin_usb_scanner` instead — see [below](#headless--no-tty-checkin_usb_scanner).

| | Path |
|---|---|
| Project | `/home/sammy/myconference` |
| Virtualenv | `/home/sammy/venv` |
| User | `sammy` |
| Settings module | `myconference.settings` |

---

## Prerequisites

### Install gunicorn into your virtualenv

```bash
/home/sammy/venv/bin/pip install gunicorn
```

---

## Service files

### Django / gunicorn — `/etc/systemd/system/badgeprint.service`

```ini
[Unit]
Description=BadgePrint Django (gunicorn)
After=network.target

[Service]
User=sammy
WorkingDirectory=/home/sammy/myconference
ExecStart=/home/sammy/venv/bin/gunicorn \
    --workers 2 \
    --bind 0.0.0.0:8000 \
    myconference.wsgi:application
Restart=always
RestartSec=5
Environment="DJANGO_SETTINGS_MODULE=myconference.settings"

[Install]
WantedBy=multi-user.target
```

### Check-in scanner — `/etc/systemd/system/checkin-scanner.service`

`checkin_scanner` reads from stdin (keyboard / barcode scanner in HID mode) so it needs a real TTY.

```ini
[Unit]
Description=BadgePrint Check-in Scanner
After=network.target badgeprint.service
Requires=badgeprint.service

[Service]
User=sammy
WorkingDirectory=/home/sammy/myconference
ExecStart=/home/sammy/venv/bin/python manage.py checkin_scanner
StandardInput=tty
TTYPath=/dev/tty1
Restart=always
RestartSec=3
StartLimitIntervalSec=60
StartLimitBurst=5
Environment="DJANGO_SETTINGS_MODULE=myconference.settings"

[Install]
WantedBy=multi-user.target
```

> **TTYPath note:** `/dev/tty1` is the physical console TTY.  
> HID barcode scanners (appear as a USB keyboard) feed input through the kernel input system into the active TTY — plug/unplug is transparent to the process, which simply waits at `input()` until the next scan.  
> `Restart=always` ensures the scanner loop restarts even on a clean exit (e.g. accidental Ctrl-D / EOF). `StartLimitBurst=5` prevents a crash-restart loop.  
> If your scanner appears as a **serial device** instead, run `ls /dev/tty*` after plugging it in and use the matching path (e.g. `/dev/ttyACM0` or `/dev/ttyUSB0`).

---

## Install and enable

```bash
# Reload systemd after creating/editing service files
sudo systemctl daemon-reload

# Django / gunicorn
sudo systemctl enable badgeprint.service
sudo systemctl start badgeprint.service

# Check-in scanner
sudo systemctl enable checkin-scanner.service
sudo systemctl start checkin-scanner.service
```

---

## Common commands

```bash
# Status
sudo systemctl status badgeprint.service
sudo systemctl status checkin-scanner.service

# Live logs
sudo journalctl -u badgeprint.service -f
sudo journalctl -u checkin-scanner.service -f

# Restart after a code change
sudo systemctl restart badgeprint.service
sudo systemctl restart checkin-scanner.service

# Stop
sudo systemctl stop checkin-scanner.service
sudo systemctl stop badgeprint.service
```

---

---

## Headless / no-TTY: `checkin_usb_scanner`

Use this command instead of `checkin_scanner` when running **without a physical TTY** — e.g. over SSH, inside a plain systemd service, or on a fully headless server.

Unlike `checkin_scanner` (which reads from stdin and requires `StandardInput=tty`), `checkin_usb_scanner` reads raw keyboard events directly from the `/dev/input/eventX` device node via the `evdev` library.  Keystrokes are **not** forwarded to the desktop or other processes when `--grab` is used.

### Install evdev

```bash
/home/sammy/venv/bin/pip install evdev
```

> `evdev` is Linux-only. It is not available on macOS or Windows.

### Add user to the `input` group

```bash
sudo usermod -aG input sammy
# Log out and back in, or reboot, for the change to take effect.
```

### Find your scanner device

```bash
/home/sammy/venv/bin/python manage.py checkin_usb_scanner --list-devices
```

Detected Honeywell / HID scanners are marked with `← scanner`. Note the path (e.g. `/dev/input/event3`).

### Run manually (test)

```bash
# Auto-detect scanner device
/home/sammy/venv/bin/python manage.py checkin_usb_scanner

# Specify device explicitly + grab it exclusively (recommended for kiosk / headless)
/home/sammy/venv/bin/python manage.py checkin_usb_scanner --device /dev/input/event3 --grab

# Restrict check-in to one event (UUID or partial name)
/home/sammy/venv/bin/python manage.py checkin_usb_scanner --grab --event "My Conference 2026"

# Check in without printing badges
/home/sammy/venv/bin/python manage.py checkin_usb_scanner --no-print
```

### systemd service — `/etc/systemd/system/checkin-usb-scanner.service`

No TTY required — works in a standard headless service unit.

```ini
[Unit]
Description=BadgePrint USB HID Check-in Scanner (no TTY)
After=network.target badgeprint.service
Requires=badgeprint.service

[Service]
User=sammy
WorkingDirectory=/home/sammy/myconference
ExecStart=/home/sammy/venv/bin/python manage.py checkin_usb_scanner --grab
Restart=always
RestartSec=3
StartLimitIntervalSec=60
StartLimitBurst=5
Environment="DJANGO_SETTINGS_MODULE=myconference.settings"

[Install]
WantedBy=multi-user.target
```

> **`--grab`** exclusively captures the scanner device so keystrokes are not sent to other applications.  
> Remove `--grab` if you need the scanner to also act as a keyboard in a desktop session.  
> Add `--device /dev/input/event3` if auto-detection picks the wrong device.  
> Add `--no-print` to disable badge printing.

### Install and enable

```bash
sudo systemctl daemon-reload
sudo systemctl enable checkin-usb-scanner.service
sudo systemctl start checkin-usb-scanner.service
```

### Common commands

```bash
# Status / logs
sudo systemctl status checkin-usb-scanner.service
sudo journalctl -u checkin-usb-scanner.service -f

# Restart after a code change
sudo systemctl restart checkin-usb-scanner.service
```

---

## Run migrations and collect static files (first deploy)

These only need to be run once (or after a code update), not on every boot.

```bash
cd /home/sammy/myconference
/home/sammy/venv/bin/python manage.py migrate
/home/sammy/venv/bin/python manage.py collectstatic --no-input
```
