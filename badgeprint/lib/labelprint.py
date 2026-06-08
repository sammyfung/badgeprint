# -*- coding:utf8 -*-
# labelprint.py by Sammy Fung <sammy@sammy.hk>
import io, logging, subprocess, re, os
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
from brother_ql.devicedependent import label_type_specs
from brother_ql.devicedependent import ENDLESS_LABEL, DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL
from brother_ql import BrotherQLRaster, create_label
from brother_ql.backends import backend_factory, guess_backend

logger = logging.getLogger(__name__)

BACKEND_CLASS = None
BACKEND_STRING_DESCR = None

# Module-level font cache: path -> size -> ImageFont object
_FONT_CACHE = {}

def _get_font(font_path, size, encoding=None):
    """Return a cached ImageFont, loading it only once per (path, size)."""
    key = (font_path, size, encoding)
    if key not in _FONT_CACHE:
        if encoding:
            _FONT_CACHE[key] = ImageFont.truetype(font_path, size, encoding=encoding)
        else:
            _FONT_CACHE[key] = ImageFont.truetype(font_path, size)
    return _FONT_CACHE[key]

# Module-level FONTS dict cache so get_fonts() isn't re-run on every call
_FONTS_CACHE = None

def _get_fonts_cached(font_folder=None):
    """Return FONTS dict, rebuilding only when not yet loaded."""
    global _FONTS_CACHE
    if _FONTS_CACHE is None:
        _FONTS_CACHE = get_fonts()
        if font_folder:
            _FONTS_CACHE.update(get_fonts(font_folder))
    return _FONTS_CACHE

def invalidate_font_cache():
    """Call this if fonts on disk change at runtime."""
    global _FONTS_CACHE, _FONT_CACHE
    _FONTS_CACHE = None
    _FONT_CACHE.clear()

# Module-level logo cache: logo path/name -> bytes read into memory
_LOGO_CACHE = {}

def _get_logo_image(logo):
    """
    Open a logo file exactly once, read it fully into a BytesIO buffer,
    cache the bytes, and return a new Image object backed by memory.
    This prevents PIL from holding the original file descriptor open.
    """
    # Derive a stable cache key (works for FieldFile, str path, or Path)
    if hasattr(logo, 'name'):
        key = logo.name  # Django FieldFile
    else:
        key = str(logo)

    if key not in _LOGO_CACHE:
        if hasattr(logo, 'open'):
            # Django FieldFile — use the storage API
            with logo.open('rb') as f:
                _LOGO_CACHE[key] = f.read()
        else:
            with open(str(logo), 'rb') as f:
                _LOGO_CACHE[key] = f.read()

    return Image.open(io.BytesIO(_LOGO_CACHE[key]))

def invalidate_logo_cache():
    """Call this when an event logo is updated."""
    _LOGO_CACHE.clear()


def get_label_context(first_name, last_name, company, default_label_size):
    # For labels in English, it uses font 'Open Sans'.
    # For labels in non-English, it assumes Traditional Chinese font is required,
    #     it uses font 'Noto Sans CJK TC'.
    context = {
      'first_name':    first_name,
      'last_name':     last_name,
      'name':          f'{first_name} {last_name}',
      'company':       company,
      'font_size':     int(90),
      'company_font_size': int(40),
      'font_family':   'Noto Sans',
      'font_style':    'Regular',
      'label_size':    default_label_size,
      'margin':        int(10),
      'threshold':     int(70),
      'align':         'center',
      'orientation':   'standard',
      'margin_top':    float(24)/100.,
      'margin_bottom': float(45)/100.,
      'margin_left':   float(35)/100.,
      'margin_right':  float(35)/100.,
    }
    context['margin_top']    = int(context['font_size']*context['margin_top'])
    context['margin_bottom'] = int(context['font_size']*context['margin_bottom'])
    context['margin_left']   = int(context['font_size']*context['margin_left'])
    context['margin_right']  = int(context['font_size']*context['margin_right'])


    def get_font_path(font_family, font_style):
        try:
            if font_family is None:
                font_family = DEFAULT_FONT['family']
                font_style =  DEFAULT_FONT['style']
            if font_style is None:
                font_style =  'Regular'
            font_path = FONTS[font_family][font_style]
        except KeyError:
            raise LookupError("Could't find the font & style")
        return font_path

    context['font_path'] = get_font_path(context['font_family'], context['font_style'])
    # Use Chinese font if first name is not starting with A-Z
    if not re.search(r'^[A-Za-z0-9,.()\/\- ]*$', last_name):
        context['name'] = "%s%s" % (first_name, last_name)
        context['font_path'] = get_font_path('Noto Sans TC', 'ExtraBold')

    if not re.search(r'^[A-Za-z0-9,.()\/\- ]*$', first_name):
        context['name'] = "%s%s" % (last_name, first_name)
        context['font_path'] = get_font_path('Noto Sans TC', 'ExtraBold')

    if not re.search(r'^[A-Za-z0-9,.()\/\- ]*$', company):
        context['font_path'] = get_font_path('Noto Sans TC', 'ExtraBold')

    def get_label_dimensions(label_size):
        try:
            ls = label_type_specs[context['label_size']]
        except KeyError:
            raise LookupError("Unknown label_size")
        return ls['dots_printable']

    width, height = get_label_dimensions(context['label_size'])
    if height > width: width, height = height, width
    if context['orientation'] == 'rotated': height, width = width, height
    context['width'], context['height'] = width, height

    return context


# Brother Label DK-11209: 62x29 (696x271px)
def create_label_im_62x29(**kwargs):
    label_type = label_type_specs[kwargs['label_size']]['kind']
    label_dimension = label_type_specs[kwargs['label_size']]['dots_printable']
    im_font = _get_font(kwargs['font_path'], kwargs['font_size'])
    company_font = _get_font(kwargs['font_path'], kwargs['company_font_size'])
    im = Image.new('L', (20, 20), 'white')
    draw = ImageDraw.Draw(im)
    company_textsize = draw.textbbox((0, 0), kwargs['company'], font=company_font)
    textsize = draw.textbbox((0, 0), kwargs['name'], font=im_font)
    im.close()
    # Label DK-11209 is 696x271px
    if textsize[2] > label_dimension[0]:
        kwargs['name'] = f"{kwargs['first_name']}\n{kwargs['last_name']}"
        textsize = draw.textbbox((0, 0), kwargs['name'], font=im_font)
    width, height = kwargs['width'], kwargs['height']
    if kwargs['orientation'] == 'standard':
        if label_type in (ENDLESS_LABEL,):
            height = textsize[3] + company_textsize[3] + kwargs['margin_top'] + kwargs['margin_bottom']
    elif kwargs['orientation'] == 'rotated':
        if label_type in (ENDLESS_LABEL,):
            width = textsize[2] + company_textsize[2] + kwargs['margin_left'] + kwargs['margin_right']
    im = Image.new('L', (width, height), 'white')
    draw = ImageDraw.Draw(im)
    if kwargs['orientation'] == 'standard':
        if label_type in (DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL):
            vertical_offset  = (height - textsize[3] - company_textsize[3] - 10)//2
            vertical_offset += (kwargs['margin_top'] - kwargs['margin_bottom'])//2
        else:
            vertical_offset = kwargs['margin_top']
        horizontal_offset = max((width - textsize[2])//2, 0)
    elif kwargs['orientation'] == 'rotated':
        vertical_offset  = (height - textsize[3])//2
        vertical_offset += (kwargs['margin_top'] - kwargs['margin_bottom'])//2
        if label_type in (DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL):
            horizontal_offset = max((width - textsize[2])//2, 0)
        else:
            horizontal_offset = kwargs['margin_left']
    offset = horizontal_offset, vertical_offset
    draw.multiline_text(offset, kwargs['name'], (0), font=im_font, align=kwargs['align'])
    company_vertical_offset = vertical_offset + textsize[3] + 20
    company_horizontal_offset = max((width - company_textsize[2]) // 2, 0)
    company_offset = company_horizontal_offset, company_vertical_offset
    draw.multiline_text(company_offset, kwargs['company'], (0), font=company_font, align=kwargs['align'])
    return im


# Brother Label DK-11202: 62x100 (696x1109px)
def create_label_im_62x100(**kwargs):
    label_type = label_type_specs[kwargs['label_size']]['kind']
    label_dimension = label_type_specs[kwargs['label_size']]['dots_printable']
    im_font = _get_font(kwargs['font_path'], kwargs['font_size'], encoding="utf-8")
    company_font = _get_font(kwargs['font_path'], kwargs['company_font_size'])
    im = Image.new('L', (20, 20), 'white')
    draw = ImageDraw.Draw(im)
    company_textsize = draw.textbbox((0, 0), kwargs['company'], font=company_font)
    textsize = draw.textbbox((0, 0), kwargs['name'], font=im_font)
    im.close()
    # Label DK-11202 is 696x1109px
    if textsize[2] > label_dimension[0]:
        kwargs['name'] = f"{kwargs['first_name']}\n{kwargs['last_name']}"
        textsize = draw.textbbox((0, 0), kwargs['name'], font=im_font)
    width, height = kwargs['width'], kwargs['height']
    if kwargs['orientation'] == 'standard':
        if label_type in (ENDLESS_LABEL,):
            height = textsize[3] + company_textsize[3] + kwargs['margin_top'] + kwargs['margin_bottom']
    elif kwargs['orientation'] == 'rotated':
        if label_type in (ENDLESS_LABEL,):
            width = textsize[2] + company_textsize[2] + kwargs['margin_left'] + kwargs['margin_right']
    im = Image.new('L', (width, height), 'white')
    draw = ImageDraw.Draw(im)
    if kwargs['orientation'] == 'standard':
        if label_type in (DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL):
            vertical_offset  = (height - textsize[3] - company_textsize[3] - 10)//2
            vertical_offset += (kwargs['margin_top'] - kwargs['margin_bottom'])//2
        else:
            vertical_offset = kwargs['margin_top']
        horizontal_offset = max((width - textsize[2])//2, 0)
    elif kwargs['orientation'] == 'rotated':
        vertical_offset  = (height - textsize[3])//2
        vertical_offset += (kwargs['margin_top'] - kwargs['margin_bottom'])//2
        if label_type in (DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL):
            horizontal_offset = max((width - textsize[2])//2, 0)
        else:
            horizontal_offset = kwargs['margin_left']
    offset = horizontal_offset, vertical_offset
    if kwargs['logo'] is not None and kwargs['logo'] != '':
        with _get_logo_image(kwargs['logo']) as logo:
            logo_width = logo.size[0]
            logo_offset = int((width - logo_width)/2), 20
            im.paste(logo, logo_offset)
    draw.multiline_text(offset, kwargs['name'], (0), font=im_font, align=kwargs['align'])
    company_vertical_offset = vertical_offset + textsize[3] + 20
    company_horizontal_offset = max((width - company_textsize[2]) // 2, 0)
    company_offset = company_horizontal_offset, company_vertical_offset
    draw.multiline_text(company_offset, kwargs['company'], (0), font=company_font, align=kwargs['align'])
    draw.line((3, 10, width - 3, 10), fill=0, width=3)
    if re.search('^type-', kwargs['label_tpl']):
        if re.search('^type-non-', kwargs['label_tpl']):
            label_tpl = re.sub('^type-non-', '', kwargs['label_tpl'])
            ticket_type = kwargs['ticket_type']
            if label_tpl != ticket_type:
                ticket_type = ticket_type.upper()
                ticket_type_font = ImageFont.truetype(kwargs['font_path'], 60)
                ticket_type_textsize = draw.textbbox((0, 0), ticket_type, font=ticket_type_font)
                ticket_type_vertical_offset = height - ticket_type_textsize[3] - 20
                ticket_type_horizontal_offset = max((width - ticket_type_textsize[2]) // 2, 0)
                ticket_type_offset = ticket_type_horizontal_offset, ticket_type_vertical_offset
                draw.multiline_text(ticket_type_offset, ticket_type, (0), font=ticket_type_font, align=kwargs['align'])
                line_height = height - 20 - ticket_type_textsize[3]/2 + 8
                draw.line((3, line_height, ticket_type_horizontal_offset-10, line_height), fill=0, width=3)
                draw.line((ticket_type_horizontal_offset+ticket_type_textsize[2]+10, line_height, width-3, line_height), fill=0, width=3)
            else:
                draw.line((3, height-10, width-3, height-10),fill=0, width=3)
                im.show()
    else:
        eventname_font = ImageFont.truetype(kwargs['font_path'], 26)
        eventname = kwargs['event_name']
        eventname_textsize = draw.textbbox((0, 0), eventname, font=eventname_font)
        eventname_vertical_offset = height - eventname_textsize[3] - 20
        eventname_horizontal_offset = max((width - eventname_textsize[2]) // 2, 0)
        eventname_offset = eventname_horizontal_offset, eventname_vertical_offset
        draw.multiline_text(eventname_offset, eventname, (0), font=eventname_font, align=kwargs['align'])

    return im


def print_text(**data):
    global DEBUG, FONTS, DEFAULT_FONT, MODEL, BACKEND_CLASS, DEFAULT_ORIENTATION, DEFAULT_LABEL_SIZE
    font_folder = "./static/fonts"
    selected_backend = guess_backend(data['printer_uri'])
    BACKEND_CLASS = backend_factory(selected_backend)['backend_class']
    MODEL = data['printer_model'] # "QL-720NW"
    DEFAULT_LABEL_SIZE  = data['label_size'] # "62x100"
    DEFAULT_ORIENTATION = data['orientation'] # "rotated"

    FONTS = _get_fonts_cached(font_folder)

    try:
        context = get_label_context(data['first_name'], data['last_name'], data['company'], data['label_size'])
    except LookupError as e:
        return f'print_text() LookupError error: {e}'

    if context['name'] is None:
        return f'context name is empty.'

    if context['company'] is None:
        context['company'] = ''

    if context['last_name'] is None:
        context['name'] = context['first_name']

    context['event_name'] = data['event_name']
    context['logo'] = data['logo']
    context['label_tpl'] = data['label_tpl']
    context['ticket_type'] = data['ticket_type']
    im = eval('create_label_im_' + data['label_size'])(**context)
    image_path = f'{settings.MEDIA_ROOT}/badgeprint/labels'
    os.makedirs(image_path, exist_ok=True)
    image_file = f"{image_path}/{data['code']}-{data['label_size']}.png"
    im.save(image_file)

    qlr = BrotherQLRaster(MODEL)
    rotate = 0 if data['orientation'] == 'standard' else 90
    if context['label_size'] == '62x29':
        rotate = 0
    create_label(qlr, im, context['label_size'], threshold=context['threshold'], cut=True, rotate=rotate)
    im.close()

    logger.debug('qlr.data (%s) len:%d', type(qlr.data), len(qlr.data))

    # Save raster bytes to a file
    raster_file = f"{image_path}/{data['code']}-{data['label_size']}.raster"
    with open(raster_file, 'wb') as f:
        f.write(qlr.data)
    status = True
    # status = send_raster_file_to_printer(data['printer_uri'], raster_file)
    return status


def send_raster_file_to_printer(printer_uri, raster_file_path, model='QL-720NW'):
    global DEBUG, FONTS, DEFAULT_FONT, MODEL, BACKEND_CLASS, DEFAULT_ORIENTATION, DEFAULT_LABEL_SIZE
    selected_backend = guess_backend(printer_uri)
    BACKEND_CLASS = backend_factory(selected_backend)['backend_class']
    MODEL = model

    status = 'ok'
    qlr = BrotherQLRaster(MODEL)

    # Read the file as bytes
    try:
        with open(raster_file_path, "rb") as file:
            qlr.data = file.read()
    except FileNotFoundError:
        return 'raster file not found'

    try:
        be = BACKEND_CLASS(printer_uri)
        be.write(qlr.data)
        be.dispose()
        del be
    except Exception as e:
        print(f'send_raster_file_to_printer() write to printer exception {e}')
        status = f'printer exception: {e}'
    return status


def send_label_by_code(code, printer_uri=None, model='QL-720NW'):
    """
    Find the pre-rendered raster file for *code* in MEDIA_ROOT and send it
    directly to the label printer.

    The raster file is expected at:
        <MEDIA_ROOT>/badgeprint/labels/<code>-<label_size>.raster

    If multiple raster files exist for the same code (different label sizes),
    the most recently modified one is used.

    Parameters
    ----------
    code        : str   Participant code (or UUID).
    printer_uri : str   Printer URI, e.g. 'tcp://192.168.1.10:9100'.
                        Reads settings.BROTHER_QL_PRINTER_URI when omitted.
    model       : str   Brother QL model string (default 'QL-720NW').

    Returns
    -------
    str  'ok' on success, or an error description string.
    """
    # ── Resolve printer URI ────────────────────────────────────────────────
    if not printer_uri:
        try:
            printer_uri = settings.BROTHER_QL_PRINTER_URI
        except AttributeError:
            pass
    if not printer_uri:
        return 'no printer URI configured'

    # ── Locate raster file(s) for this code ───────────────────────────────
    label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
    if not os.path.isdir(label_dir):
        return 'label directory not found: %s' % label_dir

    # Glob for any raster file whose name starts with the code
    prefix = code + '-'
    candidates = [
        os.path.join(label_dir, f)
        for f in os.listdir(label_dir)
        if f.startswith(prefix) and f.endswith('.raster')
    ]

    if not candidates:
        return 'raster file not found for code: %s' % code

    # Pick the most recently modified file if there are multiple sizes
    raster_path = max(candidates, key=os.path.getmtime)
    logger.debug('send_label_by_code: using raster file %s', raster_path)

    # ── Send to printer ────────────────────────────────────────────────────
    return send_raster_file_to_printer(printer_uri, raster_path, model=model)


def get_fonts(folder=None):
    """
    Scan a folder (or the system) for .ttf / .otf fonts and
    return a dictionary of the structure  family -> style -> file path.

    For a local folder, tries fc-scan first; falls back to a pure-Python
    walk that derives family/style from the filename when fc-scan is
    unavailable or returns a non-zero exit code.
    """
    fonts = {}

    if folder:
        # ── Try fc-scan; fall back to filename-based scan on any failure ──
        lines = _fc_scan_lines(folder)
        if lines is not None:
            _parse_fc_lines(lines, fonts)
        else:
            _scan_folder_fallback(folder, fonts)
    else:
        # System fonts via fc-list
        try:
            output = subprocess.check_output(
                ['fc-list', ':', 'file', 'family', 'style'],
                stderr=subprocess.DEVNULL,
            )
            _parse_fc_lines(output.decode('utf-8').split('\n'), fonts)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning('fc-list failed: %s', e)

    return fonts


def _fc_scan_lines(folder):
    """Run fc-scan on *folder*; return list of lines or None on failure."""
    cmd = ['fc-scan', '--format', '%{file}:%{family}:style=%{style}\n', folder]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return output.decode('utf-8').split('\n')
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning('fc-scan failed for %s (%s); using filename fallback.', folder, e)
        return None


def _parse_fc_lines(lines, fonts):
    """Parse fc-list / fc-scan output lines into the *fonts* dict."""
    for line in lines:
        line = line.strip().strip('"')
        if not line:
            continue
        if 'otf' not in line and 'ttf' not in line:
            continue
        parts = line.split(':')
        if len(parts) < 2:
            continue
        path = parts[0].strip()
        if not os.path.isabs(path):
            path = re.sub(r'^\.', '', path)
            path = os.getcwd() + path
        families = [f.strip() for f in parts[1].split(',')]
        try:
            styles = [s.strip() for s in parts[2].split('=')[1].split(',')]
        except Exception:
            styles = ['Regular']
        if len(families) == 1 and len(styles) > 1:
            families = families * len(styles)
        elif len(families) > 1 and len(styles) == 1:
            styles = styles * len(families)
        if len(families) != len(styles):
            logger.debug('Skipping font line (family/style mismatch): %s', line)
            continue
        for family, style in zip(families, styles):
            fonts.setdefault(family, {})[style] = path
            logger.debug('Added font: %s / %s -> %s', family, style, path)


def _scan_folder_fallback(folder, fonts):
    """
    Pure-Python fallback: walk *folder* and register every .ttf / .otf file.
    Family and style are guessed from the filename stem
    (e.g. 'OpenSans-Bold.ttf' -> family='OpenSans', style='Bold').
    """
    ext = ('.ttf', '.otf')
    for dirpath, _, filenames in os.walk(folder):
        for fname in filenames:
            if not fname.lower().endswith(ext):
                continue
            fpath = os.path.join(dirpath, fname)
            stem = os.path.splitext(fname)[0]
            # Split on the last '-' to get family / style
            if '-' in stem:
                family, style = stem.rsplit('-', 1)
            else:
                family, style = stem, 'Regular'
            family = family.replace('_', ' ').strip()
            style  = style.replace('_', ' ').strip() or 'Regular'
            fonts.setdefault(family, {})[style] = fpath
            logger.debug('Fallback font: %s / %s -> %s', family, style, fpath)


def label_print():
    global DEBUG, FONTS, DEFAULT_FONT, MODEL, BACKEND_CLASS, BACKEND_STRING_DESCR, DEFAULT_ORIENTATION, DEFAULT_LABEL_SIZE

    printer = "tcp://192.168.11.106:9100"
    model = "QL-720NW"
    # Default label size is "62x100" (DK-11202) which use "rotated" in orientation.
    # If label size in "62x29" (DK-11209), use "standard" in orientation.
    default_label_size = "62x100"
    default_orientation = "rotated"
    font_folder = "./static/fonts"

    selected_backend = guess_backend(printer)
    BACKEND_CLASS = backend_factory(selected_backend)['backend_class']
    BACKEND_STRING_DESCR = printer
    MODEL = model

    #if default_label_size not in label_sizes:
        #parser.error("Invalid --default-label-size. Please choose on of the following:\n:" + " ".join(label_sizes))
    DEFAULT_LABEL_SIZE  = default_label_size
    DEFAULT_ORIENTATION = default_orientation

    FONTS = _get_fonts_cached(font_folder)


