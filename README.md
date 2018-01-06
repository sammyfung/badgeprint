# badgeprint - Badge Print in Django

badgeprint is a django app which manages check-in and label print for badges at
conferences and events. It provides part of event management solution.

Author & Commercial Service Contact: [Sammy Fung](https://sammy.hk) <sammy@sammy.hk>

# Features

* supports multiple events
* check-in thru web UI
* check-in thru API, tested to use QR code scanner to call URL, simple & fast 
'scan & print' at conference check-in.
* support management thru Django web admin UI.
* Example script to import participant details from CSV file (eg. CSV file 
export from eventbrite.com) to badge print in Django.
* and some minor features.

# Redirect root URL (/) to badgeprint at Django

At <django_project_name>/urls.py, add the following required django classes.

from django.conf.urls import url, include
from django.views.generic.base import RedirectView

and then add the following lines to urlpatterns array:
    url(r'^badgeprint/', include('badgeprint.urls')),
    url(r'^$', RedirectView.as_view(url='/badgeprint', permanent=False), name='index')

# Use Cases

* [Hong Kong Open Source Conference](http://hkoscon.org)
* [PyCon HK](http://pycon.hk)
* Few formal tech events organised by HKCOTA and OSHK.

# Commercial Service

For commercial service (eg. on-site solution, event management, etc), you are welcome
to contact with author [Sammy Fung](https://sammy.hk) <sammy@sammy.hk> to support open
source works. Non-profit making organisations and open source community organisers may
receive discount off on service costs.

# Special Thanks

* Henry Law
* [Hong Kong Creative Open Technology Association (HKCOTA)](http://cota.hk)
* [Open Source Hong Kong (OSHK)](https://opensource.hk)

