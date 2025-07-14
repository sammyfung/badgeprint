from django.shortcuts import render, Http404
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from .models import Event, Printer, PrinterUser, Participant, Service
from .lib.labelprint import print_text, send_raster_file_to_printer
from .serializers import PrinterSerializer
import json, os

def list_all_event(request):
    # List all events
    if request.user.is_authenticated:
        return render(request, 'badgeprint/events.html')
    else:
        return HttpResponseRedirect(reverse('badgeprint_logon'))


def json_all_event(request):
    # return all events in json
    if request.user.is_authenticated:
        item_list = Event.objects.filter(id__gte=0, active=True).order_by('-id')
        total = item_list.count()
        json_items = {'total': total, 'data': []}
        for i in item_list:
            json_item = {}
            json_item['id'] = i.id
            if i.platform=='eventbrite':
                json_item['code'] = "%s" % (i.platform, i.code)
            else:
                json_item['code'] = "%s" % i.platform
            json_item['name'] = "%s" % i.name
            json_item['logo'] = "%s" % i.logo
            json_item['start_time'] = i.start_time
            json_items['data'].append(json_item)
        return JsonResponse(json_items)
    else:
        raise Http404("Authentication is required.")


def list_event_participant(request, event_id):
    # List all participants from requested event.
    if request.user.is_authenticated:
        event = Event.objects.get(id=event_id)
        return render(request, 'badgeprint/participants.html', {'id': event_id,
                                                                'event_name': event.name})
    else:
        raise Http404("Authentication is required.")


def json_event_participant(request, event_id):
    # return all events in json
    if request.user.is_authenticated:
        item_list = Participant.objects.filter(event=event_id).order_by('first_name')
        total = item_list.count()
        attended = item_list.filter(status='Attended').count()
        json_items = {'total': total, 'attended': attended, 'data': []}
        for i in item_list:
            json_item = {}
            json_item['id'] = i.id
            json_item['event'] = "%s" % i.event
            json_item['code'] = "%s" % i.code
            json_item['ticket_type'] = "%s" % i.ticket_type
            json_item['first_name'] = "%s" % i.first_name
            json_item['last_name'] = "%s" % i.last_name
            json_item['company'] = "%s" % i.company
            json_item['phone'] = "%s" % i.phone
            json_item['email'] = "%s" % i.email
            json_item['status'] = "%s" % i.status
            json_items['data'].append(json_item)
        return JsonResponse(json_items)
    else:
        raise Http404("Authentication is required.")


def json_event_stats(request, event_id):
    # return all events in json
    if request.user.is_authenticated:
        item_list = Participant.objects.filter(event=event_id).order_by('first_name')
        total = item_list.count()
        attended = item_list.filter(status='Attended').count()
        json_items = {'total': total, 'attended': attended}
        return JsonResponse(json_items)
    else:
        raise Http404("Authentication is required.")


def event_checkinreset(request, event_id):
    if request.user.is_authenticated:
        participant_list = Participant.objects.filter(event=event_id)
        for participant in participant_list:
            participant.status = "Attending"
            participant.save()
        return HttpResponseRedirect('/')
    else:
        raise Http404("Authentication is required.")


def print_participant_label(request, participant_id):
    if request.user.is_authenticated:
        # Retrieve participant information
        participant = Participant.objects.get(id=participant_id)
        # Additional: marking participant
        description = f'For {participant} in {participant.event}.'
        if participant.status != 'Attended':
            participant.status = 'Attended'
            participant.save()
            metadata = {
                'event_id': participant.event.id,
                'participant_id': participant.id,
                'provider_id': request.user.id
            }
            service = Service(title='Event checkin', description=description, metadata=metadata)
            service.save()
        # Log badge print to Service
        metadata = {
            'event_id': participant.event.id,
            'participant_id': participant.id,
            'provider_id': request.user.id
        }
        service = Service(title='Badge print', description=description, metadata=metadata)
        service.save()
        # Print to label printer
        try:
            printer = PrinterUser.objects.filter(user=request.user, ticket_type=participant.ticket_type)[0].printer
        except IndexError:
            printer = PrinterUser.objects.filter(user=request.user)[0].printer
        data = {
            'code': participant.code,
            'participant': participant,
            'printer': printer,
            'event_name': participant.event.name,
            'first_name': participant.first_name,
            'last_name': participant.last_name,
            'company': participant.company,
            'label_size': printer.label,
            'printer_uri': printer.uri,
            'printer_model': 'QL-720NW',
            'orientation': 'rotated',
            'logo': participant.event.logo,
            'label_tpl': participant.event.label_tpl if participant.event.label_tpl else '',
            'ticket_type': participant.ticket_type,
            'debug': printer.debug,
        }
        print_text(**data)
        # return to list_event_participant page
        return HttpResponseRedirect(reverse('list_event_participant', kwargs={'event_id':participant.event.id}))
    else:
        raise Http404("Authentication is required.")


def print_participant_label_api(request, participant_id):
    # Retrieve participant information
    if len(participant_id) == 23:
        participant = Participant.objects.get(code=participant_id)
    else:
        participant = Participant.objects.get(id=participant_id)
    # Additional: marking participant
    description = f'For {participant} in {participant.event}.'
    if participant.status != 'Attended':
        participant.status = 'Attended'
        participant.save()
        metadata = {
            'event_id': participant.event.id,
            'participant_id': participant.id,
            'provider_id': request.user.id
        }
        service = Service(title='Event checkin', description=description, metadata=metadata)
        service.save()
    # Log badge print to Service
    metadata = {
        'event_id': participant.event.id,
        'participant_id': participant.id,
        'provider_id': request.user.id
    }
    service = Service(title='Badge print', description=description, metadata=metadata)
    service.save()
    # Print to label printer
    try:
        printer = PrinterUser.objects.filter(user=User(id=1), ticket_type=participant.ticket_type)[0].printer
    except IndexError:
        printer = PrinterUser.objects.filter(user=User(id=1))[0].printer
    data = {
        'code': participant.code,
        'event_name': participant.event.name,
        'first_name': participant.first_name,
        'last_name': participant.last_name,
        'company': participant.company,
        'label_size': printer.label,
        'printer_uri': printer.uri,
        'printer_model': 'QL-720NW',
        'orientation': 'rotated',
        'logo': participant.event.logo,
        'label_tpl': participant.event.label_tpl,
        'ticket_type': participant.ticket_type,
        'debug': printer.debug,
    }
    print_text(**data)
    # return to list_event_participant page
    return HttpResponse()


def badgeprint_logon(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('list_all_event'))
    else:
        email = request.POST.get('inputEmail', '')
        password = request.POST.get('inputPassword', '')
        if email != '' and password != '':
            try:
                username = User.objects.get(email=email).username
            except ObjectDoesNotExist:
                return render(request, 'badgeprint/logon.html')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
            return HttpResponseRedirect(reverse('list_all_event'))
        else:
            return render(request, 'badgeprint/logon.html')


def badgeprint_logoff(request):
    if request.user.is_authenticated():
        logout(request)
    return HttpResponseRedirect(reverse('badgeprint_logon'))


def create_label(code):
    participant = Participant.objects.get(code=code)
    printer_reload = False
    printers = cache.get('badgeprint_printers')
    if not printers:
        printer_reload = True
        if load_all_printer():
            printers = cache.get('badgeprint_printers')
        else:
            status = 'no printer found.'
    printer = printers[0]
    print(f"printers = {printers}")
    data = {
        'code': participant.code,
        'participant': participant,
        'printer': printer,
        'event_name': participant.event.name,
        'first_name': participant.first_name,
        'last_name': participant.last_name,
        'company': participant.company,
        'label_size': printer['label'],
        'printer_uri': printer['uri'],
        'printer_model': 'QL-720NW',
        'orientation': 'rotated',
        'logo': participant.event.logo,
        'label_tpl': participant.event.label_tpl if participant.event.label_tpl else '',
        'ticket_type': participant.ticket_type,
        'debug': printer['debug'],
    }
    print_text(**data)

def load_all_printer():
    printers = Printer.objects.all()
    serializer = PrinterSerializer(printers, many=True)
    if not printers:
        return False
    cache.set('badgeprint_printers', serializer.data, timeout=3600)
    return True

def print_raster_file_by_code(code):
    printer_reload = False
    printers = cache.get('badgeprint_printers')
    if not printers:
        printer_reload = True
        if load_all_printer():
            printers = cache.get('badgeprint_printers')
        else:
            status = 'no printer found.'
    printer = printers[0]
    raster_file_path = f"{settings.MEDIA_ROOT}/badgeprint/labels/{code}-{printer['label']}.raster"
    if not os.path.exists(raster_file_path):
        create_label(code)
    if os.path.exists(raster_file_path):
        status = send_raster_file_to_printer(printer['uri'], raster_file_path)
        result = {'status': status, 'printer_reload': printer_reload}
    else:
        result = {'status': 'participant not exist', 'printer_reload': printer_reload}
    return result

@csrf_exempt
@api_view(['PUT'])
def config_load_printers(request):
    if load_all_printer():
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({
            'status': 'error',
            'message': 'No printers found.'
        }, status=404)

@csrf_exempt
@api_view(['PUT'])
def print_raster_file(request):
    data = json.loads(request.body)
    code = data.get('code')
    service_metadata = {
        'code': code,
        'print_label': 1
    }
    service = Service(title='Badge Print', description=f'{code}', metadata=service_metadata)
    service.save()
    status = print_raster_file_by_code(code)
    return JsonResponse({'status': status['status'], 'printer_reload': status['printer_reload']})

@api_view(['PUT'])
def api_check_in(request):
    data = json.loads(request.body)
    code = data.get('code')
    print_label = data.get('print_label')
    participant = Participant.objects.get(code=code)
    participant.status = 'Attended'
    participant.save()
    service_metadata = {
        'code': code,
        'print_label': print_label,
        'participant_id': str(participant.id)
    }
    service = Service(title='Event Checkin', description=f'{code}', metadata=service_metadata)
    service.save()
    if print_label:
        service = Service(title='Badge Print', description=f'{code}', metadata=service_metadata)
        service.save()
        status = print_raster_file_by_code(code)
    else:
        status = {'status': 'success', 'printer_reload': 0}
    return JsonResponse({'status': status['status'], 'printer_reload': status['printer_reload']})

@api_view(['PUT'])
def api_check_out(request):
    data = json.loads(request.body)
    code = data.get('code')
    print_label = data.get('print_label')
    participant = Participant.objects.get(code=code)
    participant.status = 'Attending'
    participant.save()
    service_metadata = {
        'code': code,
        'print_label': print_label,
        'participant_id': str(participant.id)
    }
    service = Service(title='Event Checkout', description=f'{code}', metadata=service_metadata)
    service.save()
    if print_label:
        service = Service(title='Badge Print', description=f'{code}', metadata=service_metadata)
        service.save()
        status = print_raster_file_by_code(code)
    else:
        status = {'status': 'success', 'printer_reload': 0}
    return JsonResponse({'status': status['status'], 'printer_reload': status['printer_reload']})