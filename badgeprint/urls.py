from django.urls import path
from . import views

urlpatterns = [
    path(r'event/<uuid:event_id>', views.list_event_participant, name='list_event_participant'),
    path(r'event/checkinreset/<uuid:event_id>', views.event_checkinreset, name='event_checkinreset'),
    path(r'participant/<uuid:participant_id>/print', views.print_participant_label, name='print_participant_label'),
    path(r'api/participant/<uuid:participant_id>/print', views.print_participant_label_api,
        name='print_participant_label_api'),
    path(r'api/event.json', views.json_all_event, name='json_all_event'),
    path(r'api/event/<uuid:event_id>.json', views.json_event_participant, name='json_event_participant'),
    path(r'api/event/stats/<uuid:event_id>.json', views.json_event_stats, name='json_event_stats'),
    path(r'api/print', views.print_raster_file, name='print_raster_file'),
    path(r'api/checkin', views.api_check_in, name='api_check_in'),
    path(r'api/checkout', views.api_check_out, name='api_check_out'),
    path(r'api/config/load_printers', views.config_load_printers, name='config_load_printers'),
    path(r'logon', views.badgeprint_logon, name='badgeprint_logon'),
    path(r'logoff', views.badgeprint_logoff, name='badgeprint_logoff'),
    path(r'', views.list_all_event, name='list_all_event'),
]
