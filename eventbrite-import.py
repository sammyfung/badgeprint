# -*- coding: utf-8 -*-

import csv, re, os, sys

# On Linux/UNIX like OS, use export command to set DJANGO_SETTINGS_MODULE.
# eg. export DJANGO_SETTINGS_MODULE=django_proj_name_here.settings
# Then execute python badgeprint/eventbrite-import.py after the eventbrite file is exist.
#os.environ.setdefault("DJANGO_SETTINGS_MODULE","django_proj_name_here.settings")
path = os.path.join(os.path.dirname(__file__),'..')
sys.path.append(os.path.abspath(path))
import django
django.setup()
from badgeprint.models import Event, Participant

# Default event id is 1
event = Event.objects.get(id=1)

with open('eventbrite.csv', newline='', encoding='utf-8') as csvfile:
    #csvreader = csv.reader(csvfile, delimiter=',')
    csvreader = csv.reader(csvfile, delimiter=',', quotechar='"')
    for row in csvreader:
        # Default CSV columns (start from column 0) used:
        # 0: Order no.
        # 3: First Name
        # 4: Last Name
        # 5: Email
        # 7: Ticket Type
        # 8: Eventbrite code
        # 14: Phone number
        # 16: Company Name
        participant = Participant.objects.filter(code=row[8])
        if len(participant) == 0 and row[0] != 'Order no.':
            if row[16] == '':
                company = ''
            else:
                company = row[16]
            participant = Participant(event=event, code=row[8], first_name=row[3], \
                                      last_name=row[4], company=company, phone=row[14], \
                                      email=row[5], ticket_type=row[7])
            participant.save()
            try:
                print(participant)
            except UnicodeEncodeError:
                print(participant.email)
        else:
            try:
                print(u"Already Exist: %s %s"%(participant[0].first_name,participant[0].last_name))
            except UnicodeEncodeError:
                print(u"Already Exist: %s"%participant[0].email)
