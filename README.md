# badgeprint - Badge label print on Brother QL printers

badgeprint is a django app project to check in and print badge labels to Brother QL printers for conferences and events. It is also a simple event management solution.

## Features

* supports Brother QL-720-NW label printer for label print (badge print), and 2 Brother label tapes - DK-11202 and DK-11209.
* prints participant name, company name. For DK-11202, it also prints event/organiser logo and other information,  etc.
* supports multiple events, multiple printers, multiple users.
* check-in thru web UI, supports search by name, phone number, email, etc.
* check-in thru API, tested to use QR code scanner (iOS/Android) to call URL, simple & fast 'scan & print' at conference check-in.
* support management thru Django web admin UI.
* an example script to import participant details from CSV file (eg. CSV file 
export from eventbrite.com) to badge print in Django.
* and some minor features.

## System Requirement

* Linux / OSX
* Python 3 and Django 4.2
* fontconfig
  * OSX: brew install fontconfig
* a supported Brother QL printer connected through network (Wifi/Ethernet)

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

