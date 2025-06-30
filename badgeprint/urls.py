from django.urls import path
from . import views

urlpatterns = [
    path(r'event/<int:event_id>', views.list_event_participant, name='list_event_participant'),
    path(r'event/<int:event_id>', views.event_checkinreset, name='event_checkinreset'),
    path(r'participant/<int:participant_id>/print', views.print_participant_label, name='print_participant_label'),
    path(r'api/participant/<int:participant_id>/print', views.print_participant_label_api,
        name='print_participant_label_api'),
    path(r'api/event.json', views.json_all_event, name='json_all_event'),
    path(r'api/event/<int:event_id>.json', views.json_event_participant, name='json_event_participant'),
    path(r'api/event/stats/<int:event_id>.json', views.json_event_stats, name='json_event_stats'),
    path(r'print_raster/<str:code>', views.print_raster, name='print_raster'),
    path(r'logon', views.badgeprint_logon, name='badgeprint_logon'),
    path(r'logoff', views.badgeprint_logoff, name='badgeprint_logoff'),
    path(r'', views.list_all_event, name='list_all_event'),
]
