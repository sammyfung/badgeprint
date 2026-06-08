from django.shortcuts import render, redirect, get_object_or_404, Http404
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
from .forms import EventForm, RsvpForm
from .lib.labelprint import print_text, send_raster_file_to_printer
from .lib.brotherql import BrotherQLPrinter
from .serializers import ParticipantSerializer, PrinterSerializer
import csv, glob, io, json, os, requests, uuid, zipfile

def list_all_event(request):
    # List all events (public front page, accessible to all users)
    context = {
        'json_api': 'json_list_public_event',
    }
    return render(request, 'badgeprint/front.html', context)

def list_my_event(request):
    # List my events
    if request.user.is_authenticated:
        context = {
            'json_api': 'json_list_my_event',
        }
        return render(request, 'badgeprint/events.html', context)
    else:
        return HttpResponseRedirect(reverse('badgeprint_logon'))

@login_required
def add_event(request):
    if not request.user.has_perm('badgeprint.add_event'):
        return HttpResponseRedirect(reverse('list_my_event'))
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.owner = request.user
            event.save()
            messages.success(request, 'Event created successfully!')
            return HttpResponseRedirect(reverse('list_my_event'))
    else:
        form = EventForm()
    return render(request, 'badgeprint/event_form.html', {'form': form, 'title': 'Add Event'})

@login_required
def duplicate_event(request, event_id):
    original = get_object_or_404(Event, id=event_id, owner=request.user)
    new_event = Event(
        platform=original.platform,
        code=original.code,
        name=f"Copy of {original.name}",
        description=original.description,
        start_time=original.start_time,
        end_time=original.end_time,
        website_url=original.website_url,
        rsvp_url=original.rsvp_url,
        rsvp_start_time=original.rsvp_start_time,
        rsvp_end_time=original.rsvp_end_time,
        city=original.city,
        public=original.public,
        highlight=original.highlight,
        logo=original.logo,
        label_tpl=original.label_tpl,
        active=original.active,
        owner=request.user,
        community=original.community,
    )
    new_event.save()
    messages.success(request, 'Event duplicated successfully! Edit the details below.')
    return HttpResponseRedirect(reverse('edit_event', kwargs={'event_id': new_event.id}))


@login_required
def edit_event(request, event_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, 'Event updated successfully!')
            return HttpResponseRedirect(reverse('get_my_event', kwargs={'event_id': event_id}))
    else:
        form = EventForm(instance=event)
    return render(request, 'badgeprint/event_form.html', {'form': form, 'title': 'Edit Event', 'event_id': event_id})

def json_list_public_event(request):
    # return all public events in json
    item_list = Event.objects.filter(public=True, active=True).order_by('start_time')
    total = item_list.count()
    json_items = {'total': total, 'data': []}
    for i in item_list:
        json_item = dict()
        json_item['id'] = i.id
        json_item['code'] = f"{i.platform}-{i.code}"
        json_item['name'] = i.name
        json_item['logo'] = f"{i.logo}"
        json_item['start_time'] = i.start_time
        json_item['end_time'] = i.end_time
        json_item['highlight'] = i.highlight
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

def _can_manage_event(user, event):
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if event.owner == user:
        return True
    if user.has_perm('badgeprint.change_event'):
        return True
    return False


def get_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    can_manage = _can_manage_event(request.user, event)
    if not event.public and not can_manage:
        raise Http404
    return render(request, 'badgeprint/event.html', {
        'event': event,
        'can_manage': can_manage,
    })


def list_event_participant(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    if not _can_manage_event(request.user, event):
        return HttpResponseRedirect(reverse('get_event', kwargs={'event_id': event_id}))
    return render(request, 'badgeprint/participants.html', {
        'id': event_id,
        'event_name': event.name,
        'event_id': event.id,
    })


def event_rsvp(request, event_id):
    event = get_object_or_404(Event, id=event_id, public=True, rsvp=True)
    initial = {}
    if request.user.is_authenticated:
        initial = {
            'first_name': request.user.first_name,
            'last_name':  request.user.last_name,
            'email':      request.user.email,
        }
    if request.method == 'POST':
        form = RsvpForm(request.POST)
        if form.is_valid():
            participant = form.save(commit=False)
            participant.event = event
            participant.status = 'Attending'
            if request.user.is_authenticated:
                participant.user = request.user
            participant.save()
            return render(request, 'badgeprint/event_rsvp_done.html', {'event': event})
    else:
        form = RsvpForm(initial=initial)
    return render(request, 'badgeprint/event_rsvp.html', {'event': event, 'form': form})


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
            json_item['event'] = "%s" % i.event
            json_item['code'] = i.code
            json_item['ticket_type'] = i.ticket_type
            json_item['first_name'] = i.first_name
            json_item['last_name'] = i.last_name
            json_item['company'] = i.company
            json_item['phone'] = i.phone
            json_item['email'] = i.email
            json_item['status'] = i.status
            # Resolve label PNG url if it exists
            code_key = i.code or str(i.id)
            label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
            png_candidates = glob.glob(os.path.join(label_dir, '%s-*.png' % code_key))
            if png_candidates:
                png_path = max(png_candidates, key=os.path.getmtime)
                rel = os.path.relpath(png_path, settings.MEDIA_ROOT)
                json_item['label_png_url'] = settings.MEDIA_URL + rel.replace(os.sep, '/')
            else:
                json_item['label_png_url'] = None
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
        code_key = participant.code or str(participant.id)
        label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
        raster_path = _label_raster_path(code_key, label_dir)
        if raster_path:
            send_raster_file_to_printer(printer.uri, raster_path)
        else:
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
    code_key = participant.code or str(participant.id)
    label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
    raster_path = _label_raster_path(code_key, label_dir)
    if raster_path:
        send_raster_file_to_printer(printer.uri, raster_path)
    else:
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
    code_key = participant.code or str(participant.id)
    label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
    if not _label_raster_path(code_key, label_dir):
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
            return {'status': 'no printer found', 'printer_reload': printer_reload}
    printer = printers[0]
    label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
    raster_path = _label_raster_path(code, label_dir)
    if not raster_path:
        # Raster missing — generate image + raster now
        try:
            participant = Participant.objects.filter(code=code).first() \
                or Participant.objects.filter(id=code).first()
        except Exception:
            participant = None
        if not participant:
            return {'status': 'participant not found', 'printer_reload': printer_reload}
        err = _regenerate_participant_label(participant)
        if err:
            return {'status': 'generate failed: %s' % err, 'printer_reload': printer_reload}
        raster_path = _label_raster_path(code, label_dir)
    if raster_path:
        status = send_raster_file_to_printer(printer['uri'], raster_path)
        result = {'status': status, 'printer_reload': printer_reload}
    else:
        result = {'status': 'raster not found after generation', 'printer_reload': printer_reload}
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
    printer_qs = Printer.objects.filter(active=True)
    printer_obj = printer_qs.filter(printall=True).first() or printer_qs.first()
    printer_id = str(printer_obj.id) if printer_obj else None
    status = print_raster_file_by_code(code)
    if status.get('status') in ('ok', 'success', True):
        Service.objects.create(
            title='Badge Print',
            description=code,
            metadata={
                'code': code,
                'device': 'web',
                'printer': printer_id,
            },
        )
    return JsonResponse({'status': status['status'], 'printer_reload': status['printer_reload']})

@api_view(['PUT'])
def api_check_in(request):
    data = json.loads(request.body)
    code = data.get('code')
    print_label = data.get('print_label')
    try:
        participant = Participant.objects.get(code=code, status='Attending')
    except Participant.DoesNotExist:
        participant = None
    if not participant:
        try:
            uuid.UUID(code)
            participant = Participant.objects.get(id=code, status='Attending')
        except ValueError:
            return JsonResponse({'status': 'non valid id'}, status=404)
        except Participant.DoesNotExist:
            return JsonResponse({'status': 'not found'}, status=404)
    participant.status = 'Attended'
    participant.save()
    # Resolve printer: prefer printall printer, else first active printer
    printer_qs = Printer.objects.filter(active=True)
    printer_obj = printer_qs.filter(printall=True).first() or printer_qs.first()
    printer_id = str(printer_obj.id) if printer_obj else None
    # Check if any printer has printall=True
    should_print = print_label or Printer.objects.filter(printall=True, active=True).exists()
    Service.objects.create(
        title='Event Checkin',
        description=code,
        metadata={
            'code': code,
            'print_label': printer_id,
            'participant_id': str(participant.id),
        },
    )
    if should_print:
        status = print_raster_file_by_code(code)
        if status.get('status') in ('ok', 'success', True):
            Service.objects.create(
                title='Badge Print',
                description=code,
                metadata={
                    'code': code,
                    'device': 'web',
                    'printer': printer_id,
                },
            )
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
        participant = Participant.objects.get(code=code, status='Attended')
    except Participant.DoesNotExist:
        participant = None
    if not participant:
        try:
            uuid.UUID(code)
            participant = Participant.objects.get(id=code, status='Attended')
        except ValueError:
            return JsonResponse({'status': 'non valid id'}, status=404)
        except Participant.DoesNotExist:
            return JsonResponse({'status': 'not found'}, status=404)
    participant.status = 'Attending'
    participant.save()
    # Check if any printer has printall=True
    should_print = print_label or Printer.objects.filter(printall=True, active=True).exists()
    service_metadata = {
        'code': code,
        'print_label': should_print,
        'participant_id': str(participant.id)
    }
    service = Service(title='Event Checkout', description=f'{code}', metadata=service_metadata)
    service.save()
    if should_print:
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
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST':
        data = request.POST.copy()
        data['event'] = event_id
        data.setdefault('status', 'Attending')
        serializer = ParticipantSerializer(data=data)
        if serializer.is_valid():
            serializer.save(id=uuid.uuid4(), active=True)
            messages.success(request, 'Participant added successfully.')
            return redirect('get_my_event', event_id=event_id)
        else:
            return render(request, 'badgeprint/participant_form.html', {
                'errors': serializer.errors,
                'event': event,
                'event_id': event_id,
            })
    return render(request, 'badgeprint/participant_form.html', {
        'event': event,
        'event_id': event_id,
    })

IMPORT_FIELDS = ['first_name', 'last_name', 'email', 'company', 'phone', 'ticket_type', 'code']

@login_required
def import_participants_upload(request, event_id):
    """Step 1: upload CSV and show column mapping UI."""
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        try:
            text = csv_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            csv_file.seek(0)
            text = csv_file.read().decode('latin-1')
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            messages.error(request, 'The CSV file is empty.')
            return redirect('import_participants_upload', event_id=event_id)
        headers = rows[0]
        preview = rows[1:6]  # up to 5 sample rows
        # Store CSV in session for step 2
        request.session[f'csv_import_{event_id}'] = {'headers': headers, 'rows': rows[1:]}
        return render(request, 'badgeprint/import_participants.html', {
            'event': event,
            'event_id': event_id,
            'headers': headers,
            'preview': preview,
            'import_fields': IMPORT_FIELDS,
            'step': 'map',
        })
    return render(request, 'badgeprint/import_participants.html', {
        'event': event,
        'event_id': event_id,
        'step': 'upload',
    })


@login_required
def import_participants_confirm(request, event_id):
    """Step 2: receive column mapping, import rows."""
    event = get_object_or_404(Event, id=event_id)
    session_key = f'csv_import_{event_id}'
    csv_data = request.session.get(session_key)
    if not csv_data:
        messages.error(request, 'Session expired. Please upload the CSV again.')
        return redirect('import_participants_upload', event_id=event_id)
    if request.method != 'POST':
        return redirect('import_participants_upload', event_id=event_id)

    headers = csv_data['headers']
    rows = csv_data['rows']

    # Build mapping: field_name -> column index (or '' = skip)
    mapping = {}
    for field in IMPORT_FIELDS:
        col = request.POST.get(f'map_{field}', '')
        if col != '':
            try:
                mapping[field] = int(col)
            except ValueError:
                pass

    if 'first_name' not in mapping:
        messages.error(request, 'First Name column mapping is required.')
        return render(request, 'badgeprint/import_participants.html', {
            'event': event,
            'event_id': event_id,
            'headers': headers,
            'preview': rows[:5],
            'import_fields': IMPORT_FIELDS,
            'step': 'map',
        })

    imported = 0
    updated = 0
    skipped = 0
    errors = []
    for i, row in enumerate(rows, start=2):
        if not any(row):
            continue

        def get_col(field, _row=row):
            idx = mapping.get(field)
            if idx is None:
                return ''
            try:
                return _row[idx].strip()
            except IndexError:
                return ''

        first_name = get_col('first_name')
        if not first_name:
            skipped += 1
            continue

        try:
            code = get_col('code') or None
            existing = None
            if code:
                existing = Participant.objects.filter(event=event, code=code).first()

            if existing:
                existing.first_name = first_name
                existing.last_name = get_col('last_name') or existing.last_name
                existing.email = get_col('email') or existing.email
                existing.company = get_col('company') or existing.company
                existing.phone = get_col('phone') or existing.phone
                existing.ticket_type = get_col('ticket_type') or existing.ticket_type
                existing.active = True
                existing.save()
                updated += 1
            else:
                Participant.objects.create(
                    id=uuid.uuid4(),
                    event=event,
                    first_name=first_name,
                    last_name=get_col('last_name'),
                    email=get_col('email') or None,
                    company=get_col('company') or None,
                    phone=get_col('phone') or None,
                    ticket_type=get_col('ticket_type') or None,
                    code=code,
                    status='Attending',
                    active=True,
                )
                imported += 1
        except Exception as e:
            errors.append(f'Row {i}: {e}')

    del request.session[session_key]
    if errors:
        for err in errors[:5]:
            messages.warning(request, err)
    messages.success(request, f'Import complete: {imported} added, {updated} updated, {skipped} skipped.')
    return redirect('get_my_event', event_id=event_id)


def _label_image_path(code_key, label_dir):
    """Return the most recent PNG path for a code, or None."""
    candidates = glob.glob(os.path.join(label_dir, '%s-*.png' % code_key))
    return max(candidates, key=os.path.getmtime) if candidates else None

def _label_raster_path(code_key, label_dir):
    """Return the most recent raster path for a code, or None."""
    candidates = glob.glob(os.path.join(label_dir, '%s-*.raster' % code_key))
    return max(candidates, key=os.path.getmtime) if candidates else None

def _regenerate_participant_label(participant):
    """Generate PNG + raster for one participant. Returns error string or None."""
    printers = cache.get('badgeprint_printers')
    if not printers:
        if not load_all_printer():
            return 'no printer configured'
        printers = cache.get('badgeprint_printers')
    printer = printers[0]
    data = {
        'code': participant.code or str(participant.id),
        'event_name': participant.event.name,
        'first_name': participant.first_name,
        'last_name': participant.last_name or '',
        'company': participant.company or '',
        'label_size': printer['label'],
        'printer_uri': printer['uri'],
        'printer_model': 'QL-720NW',
        'orientation': 'rotated',
        'logo': participant.event.logo,
        'label_tpl': participant.event.label_tpl or '',
        'ticket_type': participant.ticket_type or '',
        'debug': printer['debug'],
    }
    try:
        print_text(**data)
        return None
    except Exception as e:
        return str(e)


@login_required
def preview_label(request, event_id, participant_id):
    """Return the label PNG as an image response for inline preview."""
    participant = get_object_or_404(Participant, id=participant_id, event__id=event_id)
    code_key = participant.code or str(participant.id)
    label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
    png_path = _label_image_path(code_key, label_dir)
    if not png_path:
        return HttpResponse('Label image not found. Regenerate first.', status=404, content_type='text/plain')
    with open(png_path, 'rb') as f:
        return HttpResponse(f.read(), content_type='image/png')


@login_required
def regenerate_label(request, event_id, participant_id):
    """Regenerate PNG + raster for a single participant."""
    participant = get_object_or_404(Participant, id=participant_id, event__id=event_id)
    err = _regenerate_participant_label(participant)
    if err:
        return JsonResponse({'status': 'error', 'message': err}, status=500)
    code_key = participant.code or str(participant.id)
    label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
    png_path = _label_image_path(code_key, label_dir)
    rel = os.path.relpath(png_path, settings.MEDIA_ROOT)
    png_url = settings.MEDIA_URL + rel.replace(os.sep, '/')
    return JsonResponse({'status': 'ok', 'label_png_url': png_url})


@login_required
def regenerate_all_labels(request, event_id):
    """Regenerate PNG + raster for every participant in the event."""
    event = get_object_or_404(Event, id=event_id)
    participants = Participant.objects.filter(event=event, active=True)
    done, failed = 0, []
    for p in participants:
        err = _regenerate_participant_label(p)
        if err:
            failed.append({'id': str(p.id), 'name': '%s %s' % (p.first_name, p.last_name or ''), 'error': err})
        else:
            done += 1
    return JsonResponse({'status': 'ok', 'generated': done, 'failed': failed})


@login_required
def download_raster_zip(request, event_id):
    """Stream a ZIP of all raster files for the event."""
    event = get_object_or_404(Event, id=event_id)
    participants = Participant.objects.filter(event=event, active=True)
    label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        count = 0
        for p in participants:
            code_key = p.code or str(p.id)
            raster_path = _label_raster_path(code_key, label_dir)
            if raster_path:
                zf.write(raster_path, os.path.basename(raster_path))
                count += 1
    if count == 0:
        return HttpResponse('No raster files found. Regenerate labels first.', status=404, content_type='text/plain')

    buf.seek(0)
    zip_name = 'rasters-%s.zip' % str(event_id)[:8]
    response = HttpResponse(buf.read(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="%s"' % zip_name
    return response


@login_required
def import_raster_zip(request, event_id):
    """Import raster files from an uploaded ZIP into the label directory."""
    if request.method != 'POST' or not request.FILES.get('raster_zip'):
        return JsonResponse({'status': 'error', 'message': 'No file uploaded.'}, status=400)

    label_dir = os.path.join(settings.MEDIA_ROOT, 'badgeprint', 'labels')
    os.makedirs(label_dir, exist_ok=True)

    uploaded = request.FILES['raster_zip']
    imported, skipped = 0, 0
    try:
        with zipfile.ZipFile(io.BytesIO(uploaded.read())) as zf:
            for name in zf.namelist():
                basename = os.path.basename(name)
                if not basename.endswith('.raster'):
                    skipped += 1
                    continue
                # Safety: reject paths with directory traversal
                dest = os.path.join(label_dir, basename)
                if not os.path.abspath(dest).startswith(os.path.abspath(label_dir)):
                    skipped += 1
                    continue
                with zf.open(name) as src, open(dest, 'wb') as dst:
                    dst.write(src.read())
                imported += 1
    except zipfile.BadZipFile:
        return JsonResponse({'status': 'error', 'message': 'Invalid ZIP file.'}, status=400)

    return JsonResponse({'status': 'ok', 'imported': imported, 'skipped': skipped})


def participant_edit(request, participant_id):
    if request.method == 'POST':
        return redirect('list_my_event')
    return render(request, 'badgeprint/participant_form.html', {'events': Event.objects.all()})

def list_my_participant(request):
    if request.method == 'POST':
        return redirect('list_my_event')
    return render(request, 'badgeprint/participant_form.html', {'events': Event.objects.all()})
