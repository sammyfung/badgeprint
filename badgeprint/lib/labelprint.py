# -*- coding:utf8 -*-
# labelprint.py by Sammy Fung <sammy@sammy.hk>
import logging, subprocess, re, os
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
from brother_ql.devicedependent import label_type_specs
from brother_ql.devicedependent import ENDLESS_LABEL, DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL
from brother_ql import BrotherQLRaster, create_label
from brother_ql.backends import backend_factory, guess_backend

logger = logging.getLogger(__name__)

BACKEND_CLASS = None
BACKEND_STRING_DESCR = None


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
    if not re.search('^[A-Za-z0-9,.()\-/ ]*$', last_name):
        context['name'] = "%s%s" % (first_name, last_name)
        context['font_path'] = get_font_path('Noto Sans TC', 'ExtraBold')

    if not re.search('^[A-Za-z0-9,.()\-/ ]*$', first_name):
        context['name'] = "%s%s" % (last_name, first_name)
        context['font_path'] = get_font_path('Noto Sans TC', 'ExtraBold')

    if not re.search('^[A-Za-z0-9,.()\-/ ]*$', company):
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
    im_font = ImageFont.truetype(kwargs['font_path'], kwargs['font_size'])
    company_font = ImageFont.truetype(kwargs['font_path'], kwargs['company_font_size'])
    im = Image.new('L', (20, 20), 'white')
    draw = ImageDraw.Draw(im)
    company_textsize = draw.textbbox((0, 0), kwargs['company'], font=company_font)
    textsize = draw.textbbox((0, 0), kwargs['name'], font=im_font)
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
    # Save the badge image to MEDIA_ROOT
    try:
        im.save(f"{settings.MEDIA_ROOT}/badgeprint/labels/{kwargs['name']}.png")
    except FileNotFoundError:
        os.mkdir(settings.MEDIA_ROOT + '/badgeprint')
        os.mkdir(settings.MEDIA_ROOT + '/badgeprint/labels')
        im.save(f"{settings.MEDIA_ROOT}/badgeprint/labels/{kwargs['name']}.png")
    return im


# Brother Label DK-11202: 62x100 (696x1109px)
def create_label_im_62x100(**kwargs):
    label_type = label_type_specs[kwargs['label_size']]['kind']
    label_dimension = label_type_specs[kwargs['label_size']]['dots_printable']
    im_font = ImageFont.truetype(kwargs['font_path'], kwargs['font_size'], encoding="utf-8")
    company_font = ImageFont.truetype(kwargs['font_path'], kwargs['company_font_size'])
    im = Image.new('L', (20, 20), 'white')
    draw = ImageDraw.Draw(im)
    company_textsize = draw.textbbox((0, 0), kwargs['company'], font=company_font)
    textsize = draw.textbbox((0, 0), kwargs['name'], font=im_font)
    # Label DK-11209 is 696x1109px
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
        logo = Image.open(kwargs['logo'], 'r')
        logo_width, logo_height = logo.size
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

    # Save the badge image to MEDIA_ROOT
    try:
        im.save(f"{settings.MEDIA_ROOT}/badgeprint/labels/{kwargs['name']}.png")
    except FileNotFoundError:
        os.mkdir(settings.MEDIA_ROOT + '/badgeprint')
        os.mkdir(settings.MEDIA_ROOT + '/badgeprint/labels')
        im.save(f"{settings.MEDIA_ROOT}/badgeprint/labels/{kwargs['name']}.png")
    return im


def print_text(**data):
    global DEBUG, FONTS, DEFAULT_FONT, MODEL, BACKEND_CLASS, DEFAULT_ORIENTATION, DEFAULT_LABEL_SIZE
    font_folder = "./static/fonts"
    selected_backend = guess_backend(data['printer_uri'])
    BACKEND_CLASS = backend_factory(selected_backend)['backend_class']
    MODEL = data['printer_model'] # "QL-720NW"
    DEFAULT_LABEL_SIZE  = data['label_size'] # "62x100"
    DEFAULT_ORIENTATION = data['orientation'] # "rotated"

    FONTS = get_fonts()
    if font_folder:
        FONTS.update(get_fonts(font_folder))

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
    data['image'] = im
    image_path = f'{settings.MEDIA_ROOT}/badgeprint/labels'
    image_file = f"{image_path}/{data['code']}-{data['label_size']}.png"
    # Save the badge image to MEDIA_ROOT
    try:
        im.save(image_file)
    except FileNotFoundError:
        os.makedirs(image_path, exist_ok=True)  # Ensure the directory exists
        im.save(image_file)

    qlr = BrotherQLRaster(MODEL)
    rotate = 0 if data['orientation'] == 'standard' else 90
    if context['label_size'] == '62x29':
        rotate = 0
    create_label(qlr, im, context['label_size'], threshold=context['threshold'], cut=True, rotate=rotate)
    print(f'qlr.data ({type(qlr.data)}) len:{len(qlr.data)}')

    # Save raster bytes to a file
    raster_file = f"{image_path}/{data['code']}-{data['label_size']}.raster"
    os.makedirs(os.path.dirname(raster_file), exist_ok=True) # Ensure the directory exists
    with open(raster_file, 'wb') as file:
        file.write(qlr.data)
    file.close()
    status = True
    # status = send_raster_file_to_printer(data['printer_uri'], raster_file)
    return status


def send_raster_file_to_printer(printer_uri, raster_file_path):
    global DEBUG, FONTS, DEFAULT_FONT, MODEL, BACKEND_CLASS, DEFAULT_ORIENTATION, DEFAULT_LABEL_SIZE
    selected_backend = guess_backend(printer_uri)
    BACKEND_CLASS = backend_factory(selected_backend)['backend_class']
    MODEL = "QL-720NW"
    # DEFAULT_LABEL_SIZE  = "62x100"
    # DEFAULT_ORIENTATION = "rotated"

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


def get_fonts(folder=None):
    """
    Scan a folder (or the system) for .ttf / .otf fonts and
    return a dictionary of the structure  family -> style -> file path
    """
    fonts = {}
    if folder:
        cmd = ['fc-scan', '--format', '"%{file}:%{family}:style=%{style}\n"', folder]
    else:
        cmd = ['fc-list', ':', 'file', 'family', 'style']
    for line in subprocess.check_output(cmd).decode('utf-8').split("\n"):
        logger.debug(line)
        line.strip()
        if not line: continue
        if 'otf' not in line and 'ttf' not in line: continue
        parts = line.split(':')
        path = parts[0]
        if not re.search('^/', path):
            path = re.sub(r'"', '', path)
            path = re.sub(r'^\.', '', path)
            path = os.getcwd() + path
        families = parts[1].strip().split(',')
        try:
            styles = parts[2].split('=')[1].split(',')
        except Exception:
            styles = ''
        if len(families) == 1 and len(styles) > 1:
            families = [families[0]] * len(styles)
        elif len(families) > 1 and len(styles) == 1:
            styles = [styles[0]] * len(families)
        if len(families) != len(styles):
            logger.debug("Problem with this font: " + line)
            continue
        for i in range(len(families)):
            try: fonts[families[i]]
            except: fonts[families[i]] = dict()
            fonts[families[i]][styles[i]] = path
            logger.debug("Added this font: " + str((families[i], styles[i], path)))
    return fonts


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

    FONTS = get_fonts()
    if font_folder:
        FONTS.update(get_fonts(font_folder))


