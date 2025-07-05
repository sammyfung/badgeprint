from django.contrib import admin
from .models import Event, Printer, PrinterUser, Participant, Service


class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'owner', 'platform', 'active')
    list_filter = ['active', 'platform', 'owner']
    search_fields = ['code', 'name', 'owner']


class PrinterAdmin(admin.ModelAdmin):
    list_display = ('location', 'uri', 'label')


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


admin.site.register(Event, EventAdmin)
admin.site.register(Printer, PrinterAdmin)
admin.site.register(PrinterUser, PrinterUserAdmin)
admin.site.register(Participant, ParticipantAdmin)
admin.site.register(Service, ServiceAdmin)


