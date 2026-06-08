import uuid
from tabnanny import verbose

from django.conf import settings
from django.db import models


def user_directory_path(instance, filename):
    return 'user_{0}/{1}'.format(instance.owner.id, filename)

class BaseCommunity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(verbose_name='Name', max_length=100)
    description = models.TextField(verbose_name='Description', blank=True)
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)
    admins = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name='Admins', related_name='admin_communities', blank=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name='Members', related_name='communities', blank=True)
    public = models.BooleanField(verbose_name='Public', default=False)
    active = models.BooleanField(verbose_name='Active', default=True)

    def __str__(self):
        return self.name

    class Meta:
        abstract = True
        verbose_name_plural = 'Communities'
        ordering = ['name']


class Community(BaseCommunity):
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Creator', on_delete=models.CASCADE, related_name='badgeprint_community_creator')


class BaseEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(verbose_name='Platform', max_length=30, default='badgeprint')
    code = models.CharField(verbose_name='Code', max_length=60, null=True, blank=True)
    name = models.CharField(verbose_name='Name', max_length=120)
    description = models.TextField(verbose_name='Description', null=True, blank=True)
    start_time = models.DateTimeField(verbose_name='Start Time', null=True, blank=True)
    end_time = models.DateTimeField(verbose_name='End Time', null=True, blank=True)
    website_url = models.URLField(verbose_name='Website URL', null=True, blank=True)
    rsvp_url = models.URLField(verbose_name='RSVP URL', null=True, blank=True)
    rsvp_start_time = models.DateTimeField(verbose_name='RSVP Start Time', null=True, blank=True)
    rsvp_end_time = models.DateTimeField(verbose_name='RSVP End Time', null=True, blank=True)
    city = models.CharField(verbose_name='City', max_length=120, null=True, blank=True)
    public = models.BooleanField(verbose_name='Public', default=False)
    highlight = models.BooleanField(verbose_name='Highlight', default=False)
    rsvp = models.BooleanField(verbose_name='RSVP', default=False)
    logo = models.ImageField(upload_to=user_directory_path, verbose_name="Logo", null=True, blank=True)
    label_tpl = models.CharField(verbose_name='Label Template', max_length=60, null=True, blank=True)
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        abstract = True


class Event(BaseEvent):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Event Owner', null=True, blank=True, on_delete=models.SET_NULL, related_name='badgeprint_event_owner')
    community = models.ForeignKey(Community, verbose_name='Community', null=True, blank=True, on_delete=models.SET_NULL)

    #def link(self):
    #    return reverse('list_all_event', kwargs={'id': self.id})


class Printer(models.Model):
    LABEL_CHOICES = (
        ('62x100', 'DK-11202 (62x100)'),
        ('62x29', 'DK-11209 (62x29)'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.CharField(verbose_name='Location', max_length=60, default="This Counter")
    ip = models.GenericIPAddressField(verbose_name='IP Address', null=True, blank=True)
    uri = models.CharField(verbose_name='URI', max_length=120, null=True, blank=True)
    label = models.CharField(verbose_name='Label', max_length=20, default="62x29", choices=LABEL_CHOICES)
    event = models.ManyToManyField(Event, verbose_name='Event', blank=True)
    debug = models.BooleanField(verbose_name='Debug', default=False)
    printall = models.BooleanField(verbose_name='Print All', default=False, help_text='Always print badge label regardless of print_label flag')
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)
    active = models.BooleanField(verbose_name='Active', default=True)

    def __str__(self):
        return self.location


class PrinterUser(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE)
    printer = models.ForeignKey(Printer, verbose_name='Printer', on_delete=models.CASCADE)
    ticket_type = models.CharField(verbose_name='Label', max_length=60, null=True, blank=True)

    def __str__(self):
        return "%s - %s"%(self.user, self.printer)


class UserPrinter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE)
    printer = models.ForeignKey(Printer, verbose_name='Printer', on_delete=models.CASCADE)
    event = models.ForeignKey(Event, verbose_name='Event', null=True, blank=True, on_delete=models.SET_NULL)


class BaseParticipant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(verbose_name='Code', max_length=100, null=True, blank=True)
    first_name = models.CharField(verbose_name='First Name', max_length=60)
    last_name = models.CharField(verbose_name='Last Name', max_length=60, null=True, blank=True)
    company = models.CharField(verbose_name='Company Name', max_length=80, null=True, blank=True)
    phone = models.CharField(verbose_name='Phone', max_length=60, null=True, blank=True)
    email = models.EmailField(verbose_name='Email', null=True, blank=True)
    status = models.CharField(verbose_name='Status', max_length=10, default="Attending")
    ticket_type = models.CharField(verbose_name='Ticket Type', max_length=60, null=True, blank=True)
    other = models.TextField(verbose_name="Others", null=True, blank=True)
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)
    active = models.BooleanField(verbose_name='Active', default=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        abstract = True


class Participant(BaseParticipant):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='User', null=True, blank=True, on_delete=models.SET_NULL, related_name='badgeprint_participant_user')
    event = models.ForeignKey(Event, verbose_name='Event', on_delete=models.CASCADE)


class BaseService(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(verbose_name='Title', max_length=100)
    description = models.TextField(verbose_name='Description', null=True, blank=True)
    metadata = models.JSONField(verbose_name='Metadata', null=True, blank=True)
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)

    class Meta:
        abstract = True


class Service(BaseService):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='User', null=True, blank=True, on_delete=models.SET_NULL)
