# badgeprint - Badge label print on Brother QL printers

badgeprint is a django app to check in and print badge labels at Brother QL printers in conferences and events. It is also a simple event management solution.

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
* Python 3 and Django 1.x
* fontconfig
  * OSX: brew install fontconfig
* a supported Brother QL printer connected through network (Wifi/Ethernet)

## Redirect root URL (/) to badgeprint at Django

At <django_project_name>/urls.py, add the following required django classes.

```
from django.conf.urls import url, include
from django.views.generic.base import RedirectView
```

and then add the following lines to urlpatterns array:
```
    url(r'^badgeprint/', include('badgeprint.urls')),
    url(r'^$', RedirectView.as_view(url='/badgeprint', permanent=False), name='index')
```

## Use Cases

* [Hong Kong Open Source Conference](http://hkoscon.org)
* [PyCon HK](http://pycon.hk)
* Few formal tech events organised by HKCOTA and OSHK.

## Commercial Service

For commercial service (eg. on-site solution, event management, etc), you are welcome
to contact with author [Sammy Fung](https://sammy.hk) <sammy@sammy.hk> to support open
source works. Non-profit making organisations and open source community organisers may
receive discount off on service costs.

## Sponsors

Henry Law, Calvin Tsang.

Thanks for my sponsors, please consider to [sponsor](https://github.com/sponsors/sammyfung) my works.

# Special Thanks

* [Hong Kong Creative Open Technology Association (HKCOTA)](http://cota.hk)
* [Open Source Hong Kong (OSHK)](https://opensource.hk)
