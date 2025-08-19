import uuid
from tabnanny import verbose

from django.db import models
from django.contrib.auth.models import User


def user_directory_path(instance, filename):
    return 'user_{0}/{1}'.format(instance.owner.id, filename)

class Community(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(verbose_name='Name', max_length=100)
    description = models.TextField(verbose_name='Description', blank=True)
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)
    creator = models.ForeignKey(User, verbose_name='Creator', on_delete=models.CASCADE, related_name='created_communities')
    admins = models.ManyToManyField(User, verbose_name='Admins', related_name='admin_communities', blank=True)
    members = models.ManyToManyField(User, verbose_name='Members', related_name='communities', blank=True)
    public = models.BooleanField(verbose_name='Public', default=False)
    active = models.BooleanField(verbose_name='Active', default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = 'Communities'
        ordering = ['name']

class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(verbose_name='Platform', max_length=30, default='badgeprint')
    code = models.CharField(verbose_name='Code', max_length=60, null=True, blank=True)
    name = models.CharField(verbose_name='Name', max_length=120)
    description = models.TextField(verbose_name='Description', null=True, blank=True)
    start_time = models.DateTimeField(verbose_name='Start Time', null=True, blank=True)
    end_time = models.DateTimeField(verbose_name='End Time', null=True, blank=True)
    website_url = models.URLField(verbose_name='Website URL', null=True, blank=True)
    rsvp_url = models.URLField(verbose_name='RSVP URL', null=True, blank=True)
    city = models.CharField(verbose_name='City', max_length=120, null=True, blank=True)
    public = models.BooleanField(verbose_name='Public', default=False)
    logo = models.ImageField(upload_to=user_directory_path, verbose_name="Logo", null=True, blank=True)
    owner = models.ForeignKey(User, verbose_name='Event Owner', null=True, blank=True, on_delete=models.SET_NULL)
    community = models.ForeignKey(Community, verbose_name='Community', null=True, blank=True, on_delete=models.SET_NULL)
    label_tpl = models.CharField(verbose_name='Label Template', max_length=60, null=True, blank=True)
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


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
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)
    active = models.BooleanField(verbose_name='Active', default=True)

    def __str__(self):
        return self.location


class PrinterUser(models.Model):
    user = models.ForeignKey(User, verbose_name='User', on_delete=models.CASCADE)
    printer = models.ForeignKey(Printer, verbose_name='Printer', on_delete=models.CASCADE)
    ticket_type = models.CharField(verbose_name='Label', max_length=60, null=True, blank=True)

    def __str__(self):
        return "%s - %s"%(self.user, self.printer)


class UserPrinter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, verbose_name='User', on_delete=models.CASCADE)
    printer = models.ForeignKey(Printer, verbose_name='Printer', on_delete=models.CASCADE)
    event = models.ForeignKey(Event, verbose_name='Event', null=True, blank=True, on_delete=models.SET_NULL)


class Participant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, verbose_name='Event', on_delete=models.CASCADE)
    user = models.ForeignKey(User, verbose_name='User', null=True, blank=True, on_delete=models.SET_NULL)
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


class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(verbose_name='Title', max_length=100)
    user = models.ForeignKey(User, verbose_name='User', null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(verbose_name='Description', null=True, blank=True)
    metadata = models.JSONField(verbose_name='Metadata', null=True, blank=True)
    create_time = models.DateTimeField(verbose_name='Create Time', auto_now_add=True)
    update_time = models.DateTimeField(verbose_name='Update Time', auto_now=True)