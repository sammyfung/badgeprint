from django.shortcuts import render, redirect, Http404
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Community, Event, Printer, PrinterUser, Participant, Service
from .lib.labelprint import print_text, send_raster_file_to_printer
from .lib.brotherql import BrotherQLPrinter
from .serializers import ParticipantSerializer, PrinterSerializer
import json, os, requests, uuid

def list_all_event(request):
    # List all events
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('list_my_event'))
    else:
        context = {
            'json_api': 'json_list_public_event',
        }
        return render(request, 'badgeprint/front.html', context)
        # return HttpResponseRedirect(reverse('badgeprint_logon'))

def list_my_event(request):
    # List my events
    if request.user.is_authenticated:
        context = {
            'json_api': 'json_list_my_event',
        }
        return render(request, 'badgeprint/events.html', context)
    else:
        return HttpResponseRedirect(reverse('badgeprint_logon'))

def json_list_public_event(request):
    # return all public events in json
    item_list = Event.objects.filter(public=True, active=True).order_by('-start_time')
    total = item_list.count()
    json_items = {'total': total, 'data': []}
    for i in item_list:
        json_item = dict()
        json_item['id'] = i.id
        json_item['code'] = f"{i.platform}-{i.code}"
        json_item['name'] = i.name
        json_item['logo'] = f"{i.logo}"
        json_item['start_time'] = i.start_time
        json_items['data'].append(json_item)
    return JsonResponse(json_items)

def json_list_my_event(request):
    # return all events in json
    if request.user.is_authenticated:
        #communities_list = Community.objects.filter(admins__contains=1, active=True)
        # item_list = Event.objects.filter((Q(owner=request.user) | Q(community__in=communities_list)) & Q(active=True)).order_by('-start_time')
        item_list = Event.objects.filter((Q(owner=request.user)) & Q(active=True)).order_by('-start_time')
        total = item_list.count()
        json_items = {'total': total, 'data': []}
        for i in item_list:
            json_item = dict()
            json_item['id'] = i.id
            json_item['code'] = f"{i.platform}-{i.code}"
            json_item['name'] = i.name
            json_item['logo'] = f"{i.logo}"
            json_item['start_time'] = i.start_time
            json_items['data'].append(json_item)
        return JsonResponse(json_items)
    else:
        raise Http404("Authentication is required.")

def get_event(request, event_id):
    event = Event.objects.get(id=event_id)
    if request.user.is_authenticated:
        # List all participants from requested event.
        return render(request, 'badgeprint/participants.html', {'id': event_id,
                                                                'event_name': event.name,
                                                                'event_id': event.id})
    else:
        return render(request, 'badgeprint/event.html', {'id': event_id,
                                                        'event_name': event.name,
                                                        'event_id': event.id})


def json_event_participant(request, event_id):
    # return all events in json
    if request.user.is_authenticated:
        item_list = Participant.objects.filter(event=event_id).order_by('first_name')
        total = item_list.count()
        attended = item_list.filter(status='Attended').count()
        json_items = {'total': total, 'attended': attended, 'data': []}
        for i in item_list:
            json_item = dict()
            json_item['id'] = i.id
            json_item['event'] = f"{i.event}"
            json_item['code'] = i.code
            json_item['ticket_type'] = i.ticket_type
            json_item['first_name'] = i.first_name
            json_item['last_name'] = i.last_name
            json_item['company'] = i.company
            json_item['phone'] = i.phone
            json_item['email'] = i.email
            json_item['status'] = i.status
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
    if request.user.is_authenticated:
        logout(request)
    return HttpResponseRedirect(reverse('badgeprint_logon'))


def create_label(code):
    try:
        participant = Participant.objects.get(code=code)
    except Participant.DoesNotExist:
        participant = None
    try:
        if not participant:
            participant = Participant.objects.get(id=code)
    except Participant.DoesNotExist:
        return JsonResponse({'status': 'not found'})
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
    try:
        participant = Participant.objects.get(code=code)
    except Participant.DoesNotExist:
        participant = None
    try:
        if not participant:
            participant = Participant.objects.get(id=code)
    except Participant.DoesNotExist:
        return JsonResponse({'status': 'not found'})
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
    return JsonResponse({'first_name': participant.first_name,
                         'last_name': participant.last_name,
                         'company': participant.company,
                         'status': status['status'],
                         'printer_reload': status['printer_reload']})

@api_view(['PUT'])
def api_check_out(request):
    data = json.loads(request.body)
    code = data.get('code')
    print_label = data.get('print_label')
    try:
        participant = Participant.objects.get(code=code)
    except Participant.DoesNotExist:
        participant = None
    try:
        if not participant:
            participant = Participant.objects.get(id=code)
    except Participant.DoesNotExist:
        return JsonResponse({'status': 'not found'})
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


def qrcode_checkin(request):
    return render(request, 'badgeprint/checkin.html')

@api_view(['GET'])
def api_scan_local_printers(request):
    ql = BrotherQLPrinter()
    results = ql.scan_printers()
    url = "https://sammy.hk/go/badgeprint/api/update_printers"
    url = "http://localhost:8000/badgeprint/api/update_printers"

    headers = {
        "Content-Type": "application/json",
    }
    try:
        # Make the PUT request with a 3-second timeout
        response = requests.put(url, data=json.dumps(data), headers=headers, timeout=3)

        # Check the response
        if response.status_code == 200:
            print("Success:", response.json())
        else:
            print(f"Error: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        print("Request timed out after 3 seconds")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

    return JsonResponse({'printers': results})

@api_view(['PUT'])
def api_update_printers(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        requester_ip = x_forwarded_for.split(',')[0]
    else:
        requester_ip = request.META.get('REMOTE_ADDR')

    # Get the JSON data
    data = request.data
    printers = data.get('printers', [])

    if not isinstance(printers, list):
        return Response(
            {"error": "Printers must be an array"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate printer URLs
    for url in printers:
        if not isinstance(url, str) or not url.startswith('tcp://'):
            return Response(
                {"error": f"Invalid printer URL format: {url}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    try:
        # Get or create printer objects
        printer_objects = []
        for url in printers:
            printer, created = Printer.objects.get_or_create(
                ip=requester_ip,
                uri=url
            )
            if not created:
                # Update existing printer's IP if needed
                printer.added_by_ip = requester_ip
                printer.save()
            printer_objects.append(printer)

        # Serialize the response
        serializer = PrinterSerializer(printer_objects, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('community_list')
    else:
        form = UserCreationForm()
    return render(request, 'badgeprint/register.html', {'form': form})

def community_list(request):
    communities = Community.objects.filter(public=True, active=True)
    return render(request, 'badgeprint/community_list.html', {'communities': communities})

@login_required
def dashboard(request):
    owned_communities = Community.objects.filter(creator=request.user, active=True)
    admin_communities = Community.objects.filter(admins=request.user, active=True)
    member_communities = Community.objects.filter(members=request.user, active=True)
    return render(request, 'communities/dashboard.html', {
        'owned_communities': owned_communities,
        'admin_communities': admin_communities,
        'member_communities': member_communities
    })

@login_required
def create_community(request):
    if request.method == 'POST':
        form = CommunityForm(request.POST)
        if form.is_valid():
            community = form.save(commit=False)
            community.creator = request.user
            community.save()
            community.members.add(request.user)
            messages.success(request, 'Community created successfully!')
            return redirect('dashboard')
    else:
        form = CommunityForm()
    return render(request, 'communities/community_form.html', {'form': form, 'title': 'Create Community'})

@login_required
def update_community(request, community_id):
    community = get_object_or_404(Community, id=community_id, active=True)
    if request.user != community.creator and request.user not in community.admins.all():
        messages.error(request, 'You do not have permission to edit this community.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = CommunityForm(request.POST, instance=community)
        if form.is_valid():
            form.save()
            messages.success(request, 'Community updated successfully!')
            return redirect('dashboard')
    else:
        form = CommunityForm(instance=community)
    return render(request, 'communities/community_form.html', {
        'form': form,
        'title': 'Update Community',
        'community': community
    })

@login_required
def deactivate_community(request, community_id):
    community = get_object_or_404(Community, id=community_id, creator=request.user)
    if request.method == 'POST':
        community.active = False
        community.save()
        messages.success(request, 'Community deactivated successfully!')
        return redirect('dashboard')
    return render(request, 'communities/deactivate_confirm.html', {'community': community})

def community_detail(request, community_id):
    community = get_object_or_404(Community, id=community_id, active=True)
    return render(request, 'communities/community_detail.html', {'community': community})

def participant_create_view(request, event_id):
    if request.method == 'POST':
        data = request.POST.copy()
        data['event'] = event_id
        serializer = ParticipantSerializer(data=data)
        if serializer.is_valid():
            serializer.save(id=uuid.uuid4(), active=True)
            messages.success(request, 'Participant created successfully.')
            return redirect('list_event_participant', event_id=event_id)
        else:
            messages.error(request, 'Error creating participant.')
            return render(request, 'badgeprint/participant_form.html', {'errors': serializer.errors})
    return render(request, 'badgeprint/participant_form.html', {'events': Event.objects.all()})

def participant_edit(request, participant_id):
    if request.method == 'POST':
        return redirect('list_my_event')
    return render(request, 'badgeprint/participant_form.html', {'events': Event.objects.all()})

def list_my_participant(request):
    if request.method == 'POST':
        return redirect('list_my_event')
    return render(request, 'badgeprint/participant_form.html', {'events': Event.objects.all()})
