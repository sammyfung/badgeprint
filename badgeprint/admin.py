from django.contrib import admin
from .models import Community, Event, Printer, PrinterUser, Participant, Service

class CommunityAdmin(admin.ModelAdmin):
    list_display = ['name']
    list_filter = ['active']
    search_fields = ['name', 'description']
    raw_id_fields = ['admins', 'members']

class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'platform', 'active')
    list_filter = ['platform', 'active']
    search_fields = ['code', 'name', 'owner']

class PrinterAdmin(admin.ModelAdmin):
    list_display = ('ip', 'uri', 'location', 'label')

class PrinterUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'printer', 'ticket_type')
    list_filter = ['printer', 'user']
    search_fields = ['user__username', 'printer__location', 'ticket_type']

class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'code', 'first_name', 'last_name', 'company', 'phone', 'email', 'ticket_type', 'status')
    list_filter = ['event', 'status']
    search_fields = ['first_name', 'last_name', 'company', 'phone', 'email']

class ServiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'description', 'user', 'create_time')

admin.site.register(Community, CommunityAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(Printer, PrinterAdmin)
admin.site.register(PrinterUser, PrinterUserAdmin)
admin.site.register(Participant, ParticipantAdmin)
admin.site.register(Service, ServiceAdmin)


