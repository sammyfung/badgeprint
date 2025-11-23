from rest_framework import serializers
from .models import Participant, Printer

class PrinterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Printer
        fields = ['id', 'location', 'uri', 'label', 'debug']

class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participant
        fields = [
            'id', 'event', 'user', 'code', 'first_name', 'last_name',
            'company', 'phone', 'email', 'status', 'ticket_type',
            'other', 'create_time', 'update_time', 'active'
        ]
        read_only_fields = ['id', 'create_time', 'update_time']

    def validate(self, data):
        if not data.get('first_name'):
            raise serializers.ValidationError({"first_name": "First name is required"})
        if data.get('status') and data['status'] not in ['Attending', 'Attended']:
            raise serializers.ValidationError({"status": "Invalid status value"})
        return data