"""
Django management command: checkin_usb_scanner
===============================================
Reads participant codes directly from a Honeywell USB barcode scanner
(or any USB HID keyboard-mode scanner) on Linux / Raspberry Pi OS.

Unlike checkin_scanner (which reads from stdin), this command reads raw
keyboard events from the /dev/input/eventX device node using the evdev
library.  This means:

  * The scanner does NOT need to be the active terminal's stdin.
  * Keystrokes are NOT forwarded to the desktop / other processes
    when --grab is used (recommended for kiosk / headless deployments).
  * Works reliably over SSH, inside a systemd service, or on a headless Pi.

Usage:
    python manage.py checkin_usb_scanner
    python manage.py checkin_usb_scanner --device /dev/input/event3
    python manage.py checkin_usb_scanner --grab
    python manage.py checkin_usb_scanner --no-print
    python manage.py checkin_usb_scanner --event <event-id-or-code>
    python manage.py checkin_usb_scanner --list-devices

Requirements:
    pip install evdev          # Linux / Raspberry Pi OS only

Permissions:
    The running user must have read access to the /dev/input/eventX device.
    On Raspberry Pi OS add the user to the 'input' group:
        sudo usermod -aG input <username>
    Then log out and back in (or reboot) for the group change to take effect.

The command runs until Ctrl-C.
"""

import select
import sys
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from badgeprint.badgeprint.models import Participant, Printer, Service, Event
from badgeprint.badgeprint.views import print_raster_file_by_code, load_all_printer


# ── ANSI colour helpers (fall back gracefully on dumb terminals) ─────────────
_USE_COLOR = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

def _c(code, text):
    return f'\033[{code}m{text}\033[0m' if _USE_COLOR else text

def green(t):   return _c('32;1', t)
def yellow(t):  return _c('33;1', t)
def red(t):     return _c('31;1', t)
def cyan(t):    return _c('36;1', t)
def bold(t):    return _c('1', t)
def dim(t):     return _c('2', t)


# ── Key-code → character tables (US layout, matches Honeywell HID default) ──

# Unshifted
_KEY_MAP = {
    'KEY_1': '1', 'KEY_2': '2', 'KEY_3': '3', 'KEY_4': '4', 'KEY_5': '5',
    'KEY_6': '6', 'KEY_7': '7', 'KEY_8': '8', 'KEY_9': '9', 'KEY_0': '0',
    'KEY_A': 'a', 'KEY_B': 'b', 'KEY_C': 'c', 'KEY_D': 'd', 'KEY_E': 'e',
    'KEY_F': 'f', 'KEY_G': 'g', 'KEY_H': 'h', 'KEY_I': 'i', 'KEY_J': 'j',
    'KEY_K': 'k', 'KEY_L': 'l', 'KEY_M': 'm', 'KEY_N': 'n', 'KEY_O': 'o',
    'KEY_P': 'p', 'KEY_Q': 'q', 'KEY_R': 'r', 'KEY_S': 's', 'KEY_T': 't',
    'KEY_U': 'u', 'KEY_V': 'v', 'KEY_W': 'w', 'KEY_X': 'x', 'KEY_Y': 'y',
    'KEY_Z': 'z',
    'KEY_MINUS': '-',      'KEY_EQUAL': '=',       'KEY_LEFTBRACE': '[',
    'KEY_RIGHTBRACE': ']', 'KEY_SEMICOLON': ';',   'KEY_APOSTROPHE': "'",
    'KEY_GRAVE': '`',      'KEY_BACKSLASH': '\\',  'KEY_COMMA': ',',
    'KEY_DOT': '.',        'KEY_SLASH': '/',        'KEY_SPACE': ' ',
    # Numpad digits (some scanners emit numpad codes)
    'KEY_KP0': '0', 'KEY_KP1': '1', 'KEY_KP2': '2', 'KEY_KP3': '3',
    'KEY_KP4': '4', 'KEY_KP5': '5', 'KEY_KP6': '6', 'KEY_KP7': '7',
    'KEY_KP8': '8', 'KEY_KP9': '9',
    'KEY_KPDOT': '.', 'KEY_KPMINUS': '-', 'KEY_KPPLUS': '+',
    'KEY_KPSLASH': '/', 'KEY_KPASTERISK': '*',
}

# Shifted (Honeywell sends SHIFT+letter for uppercase barcodes)
_KEY_MAP_SHIFT = {
    'KEY_1': '!', 'KEY_2': '@', 'KEY_3': '#', 'KEY_4': '$', 'KEY_5': '%',
    'KEY_6': '^', 'KEY_7': '&', 'KEY_8': '*', 'KEY_9': '(', 'KEY_0': ')',
    'KEY_A': 'A', 'KEY_B': 'B', 'KEY_C': 'C', 'KEY_D': 'D', 'KEY_E': 'E',
    'KEY_F': 'F', 'KEY_G': 'G', 'KEY_H': 'H', 'KEY_I': 'I', 'KEY_J': 'J',
    'KEY_K': 'K', 'KEY_L': 'L', 'KEY_M': 'M', 'KEY_N': 'N', 'KEY_O': 'O',
    'KEY_P': 'P', 'KEY_Q': 'Q', 'KEY_R': 'R', 'KEY_S': 'S', 'KEY_T': 'T',
    'KEY_U': 'U', 'KEY_V': 'V', 'KEY_W': 'W', 'KEY_X': 'X', 'KEY_Y': 'Y',
    'KEY_Z': 'Z',
    'KEY_MINUS': '_',       'KEY_EQUAL': '+',       'KEY_LEFTBRACE': '{',
    'KEY_RIGHTBRACE': '}',  'KEY_SEMICOLON': ':',   'KEY_APOSTROPHE': '"',
    'KEY_GRAVE': '~',       'KEY_BACKSLASH': '|',   'KEY_COMMA': '<',
    'KEY_DOT': '>',         'KEY_SLASH': '?',
}

# Keyword fragments used to auto-detect Honeywell (and generic) USB scanners
_SCANNER_NAME_HINTS = (
    'honeywell',
    'metrologic',    # Honeywell legacy brand
    'hand held',
    'barcode',
    'bar code',
    'scanner',
    'hid pos',       # HID POS barcode scanner class
    'xenon',         # Honeywell Xenon series
    'voyager',       # Honeywell Voyager series
    'youjie',        # Honeywell Youjie OEM series
    'bematech',
)


def _list_input_devices():
    """Return list of (path, name) tuples for all /dev/input/event* devices."""
    try:
        import evdev
    except ImportError:
        return []
    devices = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
            devices.append((path, d.name))
            d.close()
        except Exception:
            pass
    return devices


def _find_scanner_device():
    """
    Auto-detect the first USB HID barcode scanner device.
    Returns the device path string, or None if not found.
    """
    for path, name in _list_input_devices():
        name_lower = name.lower()
        if any(hint in name_lower for hint in _SCANNER_NAME_HINTS):
            return path
    return None


class Command(BaseCommand):
    help = (
        'USB HID check-in scanner: read codes directly from a Honeywell '
        'USB barcode scanner on Linux / Raspberry Pi OS, check in and print badges.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--device',
            metavar='PATH',
            default=None,
            help=(
                'Path to the evdev input device, e.g. /dev/input/event3. '
                'Auto-detected from device name if omitted.'
            ),
        )
        parser.add_argument(
            '--grab',
            action='store_true',
            default=False,
            help=(
                'Exclusively grab the input device so keystrokes are NOT '
                'forwarded to the desktop or other applications. '
                'Recommended for headless / kiosk deployments.'
            ),
        )
        parser.add_argument(
            '--list-devices',
            action='store_true',
            default=False,
            help='List available /dev/input/event* devices and exit.',
        )
        parser.add_argument(
            '--no-print',
            action='store_true',
            default=False,
            help='Check in without printing a badge label.',
        )
        parser.add_argument(
            '--event',
            metavar='EVENT_ID_OR_NAME',
            default=None,
            help='Restrict check-in to a specific event (UUID or partial name match).',
        )

    # ─────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        # ── --list-devices shortcut ────────────────────────────────────────
        if options['list_devices']:
            self._cmd_list_devices()
            return

        # ── Import evdev (Linux only) ──────────────────────────────────────
        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            self.stderr.write(red(
                'The evdev package is not installed.\n'
                'Install it with:  pip install evdev\n'
                'evdev requires Linux (not macOS / Windows).'
            ))
            return

        no_print = options['no_print']
        event_filter = options['event']
        device_path = options['device']
        do_grab = options['grab']

        # ── Resolve optional event filter ──────────────────────────────────
        event = None
        if event_filter:
            try:
                event = Event.objects.get(id=event_filter)
            except (Event.DoesNotExist, ValueError):
                qs = Event.objects.filter(name__icontains=event_filter, active=True)
                if qs.count() == 1:
                    event = qs.first()
                elif qs.count() > 1:
                    self.stderr.write(red(
                        f'Ambiguous event name "{event_filter}". '
                        f'Found {qs.count()} matches. Use a UUID instead.'
                    ))
                    return
                else:
                    self.stderr.write(red(f'Event "{event_filter}" not found.'))
                    return

        # ── Open input device ──────────────────────────────────────────────
        if not device_path:
            device_path = _find_scanner_device()
            if device_path:
                self.stdout.write(dim(f'Auto-detected scanner: {device_path}'))
            else:
                self.stderr.write(red(
                    'No USB barcode scanner detected automatically.\n'
                    'Run with --list-devices to see available devices, '
                    'then pass --device /dev/input/eventX explicitly.'
                ))
                return

        try:
            scanner = evdev.InputDevice(device_path)
        except PermissionError:
            self.stderr.write(red(
                f'Permission denied: {device_path}\n'
                'Add your user to the "input" group:\n'
                '    sudo usermod -aG input $USER\n'
                'Then log out and back in (or reboot).'
            ))
            return
        except FileNotFoundError:
            self.stderr.write(red(f'Device not found: {device_path}'))
            return
        except Exception as e:
            self.stderr.write(red(f'Cannot open device {device_path}: {e}'))
            return

        if do_grab:
            try:
                scanner.grab()
                self.stdout.write(dim('Device grabbed exclusively.'))
            except Exception as e:
                self.stdout.write(yellow(f'Warning: could not grab device: {e}'))

        # ── Pre-load printers & resolve printall ───────────────────────────
        printall = Printer.objects.filter(printall=True, active=True).exists()
        if not no_print:
            if load_all_printer():
                self.stdout.write(dim('Printers loaded.'))
            else:
                self.stdout.write(yellow(
                    'Warning: no printers configured. Badges will NOT be printed.'
                ))
                no_print = True

        if printall and no_print:
            no_print = False
            self.stdout.write(yellow('printall=True on a printer — overriding --no-print.'))

        # ── Banner ─────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(bold('═' * 52))
        self.stdout.write(bold('  BadgePrint — USB HID Check-in Scanner'))
        self.stdout.write(bold(f'  Device: {scanner.name}'))
        self.stdout.write(bold(f'  Path  : {device_path}'))
        if event:
            self.stdout.write(bold(f'  Event : {event.name}'))
        print_mode = 'always (printall)' if printall else ('disabled' if no_print else 'enabled')
        self.stdout.write(bold(f'  Print : {print_mode}'))
        grab_mode = 'exclusive (--grab)' if do_grab else 'shared'
        self.stdout.write(bold(f'  Grab  : {grab_mode}'))
        self.stdout.write(bold('═' * 52))
        self.stdout.write(dim('Waiting for barcode scans…'))
        self.stdout.write(dim('Press Ctrl-C to quit.\n'))

        # ── Main read loop ─────────────────────────────────────────────────
        stats = {'checked_in': 0, 'already': 0, 'not_found': 0, 'errors': 0}
        buf = []          # character buffer for current barcode
        shift = False     # track shift key state

        try:
            while True:
                # Use select so KeyboardInterrupt is not swallowed on Pi
                r, _, _ = select.select([scanner.fd], [], [], 1.0)
                if not r:
                    continue

                for event_obj in scanner.read():
                    if event_obj.type != ecodes.EV_KEY:
                        continue

                    key_event = evdev.categorize(event_obj)
                    keycode = key_event.keycode   # str like 'KEY_A' or list

                    # evdev may return a list when multiple keys share a code
                    if isinstance(keycode, list):
                        keycode = keycode[0]

                    # Track shift state (value 0=up, 1=down, 2=held)
                    if keycode in ('KEY_LEFTSHIFT', 'KEY_RIGHTSHIFT'):
                        shift = (key_event.keystate != 0)
                        continue

                    # Only act on key-down (1) and key-held (2)
                    if key_event.keystate == 0:
                        continue

                    # Enter → submit the buffered barcode
                    if keycode in ('KEY_ENTER', 'KEY_KPENTER'):
                        raw = ''.join(buf).strip()
                        buf.clear()
                        shift = False
                        if raw:
                            self.stdout.write(cyan('Scanned> ') + raw)
                            self._process(raw, event, no_print, printall, stats)
                        continue

                    # Backspace support (unlikely from a scanner, but handle it)
                    if keycode == 'KEY_BACKSPACE':
                        if buf:
                            buf.pop()
                        continue

                    # Map key code → character
                    char = (_KEY_MAP_SHIFT if shift else _KEY_MAP).get(keycode)
                    if char:
                        buf.append(char)

        except KeyboardInterrupt:
            pass
        finally:
            if do_grab:
                try:
                    scanner.ungrab()
                except Exception:
                    pass
            scanner.close()

        # ── Summary ────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(bold('─' * 52))
        self.stdout.write(bold('Session summary'))
        self.stdout.write(f'  Checked in : {green(str(stats["checked_in"]))}')
        self.stdout.write(f'  Already in : {yellow(str(stats["already"]))}')
        self.stdout.write(f'  Not found  : {red(str(stats["not_found"]))}')
        if stats['errors']:
            self.stdout.write(f'  Errors     : {red(str(stats["errors"]))}')
        self.stdout.write(bold('─' * 52))

    # ── --list-devices ─────────────────────────────────────────────────────

    def _cmd_list_devices(self):
        devices = _list_input_devices()
        if not devices:
            self.stdout.write(yellow('No input devices found (or evdev not installed).'))
            return
        self.stdout.write(bold(f'{"Path":<25}  {"Device name"}'))
        self.stdout.write(bold('─' * 70))
        for path, name in sorted(devices):
            name_lower = name.lower()
            is_scanner = any(h in name_lower for h in _SCANNER_NAME_HINTS)
            marker = green(' ← scanner') if is_scanner else ''
            self.stdout.write(f'{path:<25}  {name}{marker}')

    # ── Internal helpers ───────────────────────────────────────────────────

    def _find_participant(self, code, event):
        """Locate a participant by code string or UUID id, optionally within an event."""
        qs = Participant.objects.filter(active=True)
        if event:
            qs = qs.filter(event=event)

        p = qs.filter(code=code).first()
        if p:
            return p

        try:
            uid = uuid.UUID(code)
            p = qs.filter(id=uid).first()
            if p:
                return p
        except ValueError:
            pass

        return None

    def _process(self, code, event, no_print, printall, stats):
        ts = timezone.localtime().strftime('%H:%M:%S')

        participant = self._find_participant(code, event)

        if not participant:
            stats['not_found'] += 1
            self.stdout.write(f'[{dim(ts)}] {red("NOT FOUND")}  {dim(code)}')
            return

        name = f'{participant.first_name} {participant.last_name or ""}'.strip()
        company = participant.company or ''
        event_name = participant.event.name

        should_print = (not no_print) or printall

        printer_qs = Printer.objects.filter(active=True)
        printer = printer_qs.filter(printall=True).first() or printer_qs.first()

        if participant.status == 'Attended':
            stats['already'] += 1
            self.stdout.write(
                f'[{dim(ts)}] {yellow("ALREADY IN")}  '
                f'{bold(name)}'
                + (f'  {dim(company)}' if company else '')
            )
            if printall:
                self._print_label(code, printer)
            return

        # ── Check in ──
        try:
            participant.status = 'Attended'
            participant.save()

            service_meta = {
                'code': code,
                'participant_id': str(participant.id),
            }
            Service.objects.create(
                title='Event Checkin',
                description=code,
                metadata=service_meta,
            )
            stats['checked_in'] += 1
            self.stdout.write(
                f'[{dim(ts)}] {green("CHECKED IN")}   '
                f'{bold(name)}'
                + (f'  {dim(company)}' if company else '')
                + f'  {dim("·")}  {dim(event_name)}'
            )
        except Exception as e:
            stats['errors'] += 1
            self.stdout.write(f'[{dim(ts)}] {red("ERROR")} check-in failed: {e}')
            return

        # ── Print label ──
        if should_print:
            self._print_label(code, printer)

    def _print_label(self, code, printer=None):
        try:
            result = print_raster_file_by_code(code)
            print_status = result.get('status', 'unknown')
            if print_status in ('ok', 'success', True):
                Service.objects.create(
                    title='Badge Print',
                    description=code,
                    metadata={
                        'code': code,
                        'device': 'checkin_usb_scanner',
                        'printer': str(printer.id) if printer else None,
                    },
                )
                self.stdout.write('           ' + dim('Printed \u2713'))
            else:
                self.stdout.write('           ' + yellow('Print: %s' % print_status))
        except Exception as e:
            self.stdout.write('           ' + yellow('Print error: %s' % e))
