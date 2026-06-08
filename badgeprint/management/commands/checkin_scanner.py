"""
Django management command: checkin_scanner
==========================================
Reads participant codes from stdin (keyboard / barcode scanner in HID mode)
one line at a time, checks in the participant, and prints their badge label.

Usage:
    python manage.py checkin_scanner
    python manage.py checkin_scanner --no-print
    python manage.py checkin_scanner --event <event-id-or-code>

The command runs until Ctrl-C or Ctrl-D (EOF).
"""

import sys
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from badgeprint.badgeprint.models import Participant, Printer, Service, Event
from badgeprint.badgeprint.views import print_raster_file_by_code, load_all_printer


# ── ANSI colour helpers (fall back gracefully on Windows / dumb terminals) ──
_USE_COLOR = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

def _c(code, text):
    return f'\033[{code}m{text}\033[0m' if _USE_COLOR else text

def green(t):   return _c('32;1', t)
def yellow(t):  return _c('33;1', t)
def red(t):     return _c('31;1', t)
def cyan(t):    return _c('36;1', t)
def bold(t):    return _c('1', t)
def dim(t):     return _c('2', t)


class Command(BaseCommand):
    help = 'Interactive check-in scanner: read codes from stdin, check in and print badges.'

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        no_print = options['no_print']
        event_filter = options['event']

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

        # If printall is set, force printing on regardless of --no-print
        if printall and no_print:
            no_print = False
            self.stdout.write(yellow('printall=True on a printer — overriding --no-print.'))

        # ── Banner ─────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(bold('═' * 52))
        self.stdout.write(bold('  BadgePrint — Check-in Scanner'))
        if event:
            self.stdout.write(bold(f'  Event : {event.name}'))
        print_mode = 'always (printall)' if printall else ('disabled' if no_print else 'enabled')
        self.stdout.write(bold(f'  Print : {print_mode}'))
        self.stdout.write(bold('═' * 52))
        self.stdout.write(dim('Scan a QR / barcode, or type a code and press Enter.'))
        self.stdout.write(dim('Press Ctrl-C or Ctrl-D to quit.\n'))

        # ── Main loop ──────────────────────────────────────────────────────
        stats = {'checked_in': 0, 'already': 0, 'not_found': 0, 'errors': 0}

        try:
            while True:
                try:
                    raw = input(cyan('Code> ')).strip()
                except EOFError:
                    break

                if not raw:
                    continue

                # Strip leading ESC sequences added by some barcode scanners
                # e.g. ^[^[ (two ESC chars, \x1b\x1b) before the real code
                code = raw.lstrip('\x1b')
                if code != raw:
                    n_stripped = len(raw) - len(code)
                    self.stdout.write(dim('  (stripped %d ESC prefix char(s))' % n_stripped))

                if not code:
                    continue

                self._process(code, event, no_print, printall, stats)

        except KeyboardInterrupt:
            pass

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

    # ── Internal helpers ───────────────────────────────────────────────────

    def _find_participant(self, code, event):
        """Locate a participant by code string or UUID id, optionally within an event."""
        qs = Participant.objects.filter(active=True)
        if event:
            qs = qs.filter(event=event)

        # Try code field first
        p = qs.filter(code=code).first()
        if p:
            return p

        # Try UUID primary key
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

        # Resolve printer once: prefer printall printer, else first active printer
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
                        'device': 'checkin_scanner',
                        'printer': str(printer.id) if printer else None,
                    },
                )
                self.stdout.write('           ' + dim('Printed \u2713'))
            else:
                self.stdout.write('           ' + yellow('Print: %s' % print_status))
        except Exception as e:
            self.stdout.write('           ' + yellow('Print error: %s' % e))
