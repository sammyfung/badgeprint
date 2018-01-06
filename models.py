from django.db import models
from django.contrib.auth.models import User


def user_directory_path(instance, filename):
    return 'user_{0}/{1}'.format(instance.owner.id, filename)


class Event(models.Model):
    platform = models.CharField(verbose_name='Platform', max_length=30, default='local')
    code = models.CharField(verbose_name='Code', max_length=60, null=True, blank=True)
    name = models.CharField(verbose_name='Name', max_length=120)
    logo = models.ImageField(upload_to=user_directory_path, verbose_name="Logo", null=True, blank=True)
    owner = models.ForeignKey(User, verbose_name='Event Owner')
    label_tpl = models.CharField(verbose_name='Label Template', max_length=60, null=True, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Printer(models.Model):
    LABEL_CHOICES = (
        ('62x29', 'DK-11209 (62x29)'),
        ('62x100', 'DK-11202 (62x100)'),
    )
    location = models.CharField(verbose_name='Location', max_length=60, default="This Counter")
    uri = models.CharField(verbose_name='URI', max_length=120)
    label = models.CharField(verbose_name='Label', max_length=20, default="62x29", choices=LABEL_CHOICES)
    debug = models.BooleanField(verbose_name='Debug', default=False)

    def __str__(self):
        return self.location


class PrinterUser(models.Model):
    user = models.ForeignKey(User, verbose_name='User')
    printer = models.ForeignKey(Printer, verbose_name='Printer')
    ticket_type = models.CharField(verbose_name='Label', max_length=60, null=True, blank=True)

    def __str__(self):
        return "%s - %s"%(self.user, self.printer)


class Participant(models.Model):
    event = models.ForeignKey(Event, verbose_name='Event')
    code = models.CharField(verbose_name='Code', max_length=60, null=True, blank=True)
    first_name = models.CharField(verbose_name='First Name', max_length=60)
    last_name = models.CharField(verbose_name='Last Name', max_length=60, null=True, blank=True)
    company = models.CharField(verbose_name='Company Name', max_length=80, null=True, blank=True)
    phone = models.CharField(verbose_name='Phone', max_length=60, null=True, blank=True)
    email = models.EmailField(verbose_name='Email', null=True, blank=True)
    status = models.CharField(verbose_name='Status', max_length=10, default="Attending")
    ticket_type = models.CharField(verbose_name='Ticket Type', max_length=60, null=True, blank=True)

    def __str__(self):
        return "%s %s"%(self.first_name, self.last_name)


class Log(models.Model):
    event = models.ForeignKey(Event, verbose_name='Event', null=True, blank=True)
    user = models.ForeignKey(User, verbose_name='User', null=True, blank=True)
    participant = models.ForeignKey(Participant, verbose_name='Participant', null=True, blank=True)
    time = models.DateTimeField(verbose_name='Log Time', auto_now_add=True)
    type = models.CharField(verbose_name='Type', max_length=20, default='system')
    action = models.CharField(verbose_name='Action Name', max_length=20)
    message = models.CharField(verbose_name='Company Name', max_length=80, null=True, blank=True)

    def __str__(self):
        return self.time


class Checkin(models.Model):
    event = models.CharField(verbose_name='Event ID', max_length=20, null=True, blank=True)
    attendee = models.CharField(verbose_name='Attendee ID', max_length=20, null=True, blank=True)
    time = models.DateTimeField(verbose_name='Checkin Time')