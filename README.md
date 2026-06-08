# badgeprint - Event management & badge label printing

badgeprint is a django app project to check-in and print badge labels to Brother QL printers for conferences and events, now it also provides event management.

## Features

* Label Print: print labels for participants to stick to badge card or clothes directly. 
  * A label includes first name, last name, company/organisation name.
  * For large label, it also includes event logo and event name.
  * Tested with Brother QL-720NW and support DK-11202 and DK-11209 label tapes.
  * DK-11202 (62x100mm) can be sticked on clothes directly without additional badge card.
  * DK-11209 (29x62mm) can be sticked to badge card.
* Check-in with QR code, admin UI, or API.
  * QR code can be scanned by camara (Web based QR scanner)
  * Barcode Scanner (checkin_usb_scanner / checkin_scanner): Tested with Honeywell Genesis 7580g USB scanner.
  * badgeprint admin UI: event participant list check-in button with search feature.
  * badgeprint API: use Android / iOS QR code scanners to call badgeprint check-in URL.
* Django admin can access & modify badgeprint data.
* Import from CSV: import participant list from CSV, RSVP can be done by 3rd party registration services or web forms.
* Import/Export Brother raster files, it speeds up "scan to print" by just sending raster file to Printer when particiapnt checkin.
* Public event list with RSVP (built-in or 3rd party registration / e-form).

## System Requirement

* Linux / OSX
* Python and Django  
* fontconfig
  * OSX: brew install fontconfig
* Optional:
  * Brother QL printer with Wifi / Ethernet and supported by open source community python library for Brother QL printers. Tested QL-720NW.
  * Honeywell Genesis 7580g USB scanner.
  * WebCam.
  * Let us know if you tested with other devices.

## Redirect root URL (/) to badgeprint at Django

In urls.py of your django project, import the path() function and include a path() line to urlpatterns array:

```
from django.urls import path, include
```

```
urlpatterns = [
    path('badgeprint/', include('badgeprint.badgeprint.urls')),
    path('admin/', admin.site.urls),
]
```

## Use Cases

* [Hong Kong Open Source Conference](http://hkoscon.org)
* [PyCon HK](http://pycon.hk)
* Few formal tech events organised by HKCOTA and OSHK.

