from django.conf.urls import url
from . import views


# Add the following lines to urls.py of django project to add this urls.py to system wide.
# from django.conf.urls import include
#     url(r'^badgeprint/', include('badgeprint.urls')),
urlpatterns = [
    url(r'^event/(?P<event_id>[0-9]+)$', views.list_event_participant, name='list_event_participant'),
    url(r'^event/(?P<event_id>[0-9]+)/checkinreset$', views.event_checkinreset, name='event_checkinreset'),
    url(r'^participant/(?P<participant_id>[0-9]+)/print$', views.print_participant_label, name='print_participant_label'),
    url(r'^api/participant/(?P<participant_id>[0-9]+)/print$', views.print_participant_label_api,
        name='print_participant_label_api'),
    url(r'^api/event.json$', views.json_all_event, name='json_all_event'),
    url(r'^api/event/(?P<event_id>[0-9]+).json$', views.json_event_participant, name='json_event_participant'),
    url(r'^api/event/stats/(?P<event_id>[0-9]+).json$', views.json_event_stats, name='json_event_stats'),
    url(r'^logon', views.badgeprint_logon, name='badgeprint_logon'),
    url(r'^logoff', views.badgeprint_logoff, name='badgeprint_logoff'),
    url(r'^$', views.list_all_event, name='list_all_event'),
]
