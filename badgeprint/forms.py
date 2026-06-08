from django import forms
from .models import Event, Participant

_ctrl = {'class': 'form-control'}
_sel  = {'class': 'form-select'}
_dt   = {'type': 'datetime-local', 'class': 'form-control'}


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['name', 'code', 'description', 'start_time', 'end_time',
                  'website_url', 'rsvp_url', 'rsvp_start_time', 'rsvp_end_time',
                  'city', 'public', 'highlight', 'rsvp', 'logo', 'community']
        widgets = {
            'name':           forms.TextInput(attrs=_ctrl),
            'code':           forms.TextInput(attrs=_ctrl),
            'description':    forms.Textarea(attrs={**_ctrl, 'rows': 4}),
            'start_time':     forms.DateTimeInput(attrs=_dt),
            'end_time':       forms.DateTimeInput(attrs=_dt),
            'website_url':    forms.URLInput(attrs=_ctrl),
            'rsvp_url':       forms.URLInput(attrs=_ctrl),
            'rsvp_start_time': forms.DateTimeInput(attrs=_dt),
            'rsvp_end_time':  forms.DateTimeInput(attrs=_dt),
            'city':           forms.TextInput(attrs=_ctrl),
            'logo':           forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'community':      forms.Select(attrs=_sel),
        }


class RsvpForm(forms.ModelForm):
    class Meta:
        model = Participant
        fields = ['first_name', 'last_name', 'email', 'phone', 'company']
        widgets = {
            'first_name': forms.TextInput(attrs=_ctrl),
            'last_name':  forms.TextInput(attrs=_ctrl),
            'email':      forms.EmailInput(attrs=_ctrl),
            'phone':      forms.TextInput(attrs=_ctrl),
            'company':    forms.TextInput(attrs=_ctrl),
        }
