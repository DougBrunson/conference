import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb


class StringMessage(messages.Message):

    """StringMessage-- outbound (single) string message"""
    data = messages.StringField(1, required=True)


class BooleanMessage(messages.Message):

    """BooleanMessage-- outbound Boolean value message"""
    data = messages.BooleanField(1)


class ProfileMiniForm(messages.Message):

    """ProfileMiniForm -- update Profile form message"""
    displayName = messages.StringField(1)


class ProfileForm(messages.Message):

    """ProfileForm -- Profile outbound form message"""
    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)
    conferenceKeysToAttend = messages.StringField(3, repeated=True)


class ConferenceForm(messages.Message):

    """ConferenceForm -- Conference outbound form message"""
    name = messages.StringField(1)
    description = messages.StringField(2)
    organizerUserId = messages.StringField(3)
    topics = messages.StringField(4, repeated=True)
    city = messages.StringField(5)
    startDate = messages.StringField(6)  # DateTimeField()
    month = messages.IntegerField(7)
    maxAttendees = messages.IntegerField(8)
    seatsAvailable = messages.IntegerField(9)
    endDate = messages.StringField(10)  # DateTimeField()
    websafeKey = messages.StringField(11)
    organizerDisplayName = messages.StringField(12)


class ConferenceForms(messages.Message):

    """ConferenceForms -- multiple Conference outbound form message"""
    items = messages.MessageField(ConferenceForm, 1, repeated=True)


class ConferenceQueryForm(messages.Message):

    """ConferenceQueryForm -- Conference query inbound form message"""
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)


class ConferenceQueryForms(messages.Message):

    """ConferenceQueryForms -- multiple ConferenceQueryForm inbound form message"""
    filters = messages.MessageField(ConferenceQueryForm, 1, repeated=True)


# ---------------- begin added forms --------------------------------

class SessionForm(messages.Message):
    conference_key = messages.StringField(1)
    title = messages.StringField(2)
    session_type = messages.StringField(3)
    highlights = messages.StringField(4)
    organizer_id = messages.StringField(5)
    speaker_id = messages.IntegerField(6)
    speaker_name = messages.StringField(7)
    start_time = messages.StringField(8)
    duration = messages.IntegerField(9)
    location = messages.StringField(10)


class SessionForms(messages.Message):
    items = messages.MessageField(SessionForm, 1, repeated=True)


class SessionByConfForm(messages.Message):
    conference_key = messages.StringField(1)


class SessionByLocationForm(messages.Message):
    location = messages.IntegerField(1)


class SessionByTypeForm(messages.Message):
    conference_key = messages.StringField(1)
    session_type = messages.StringField(2)


class SessionQueryForm(messages.Message):
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)


class SessionQueryForms(messages.Message):
    filters = messages.MessageField(SessionQueryForm, 1, repeated=True)


class SpeakerForm(messages.Message):
    name = messages.StringField(1)


class SpeakerForms(messages.Message):
    items = messages.MessageField(SpeakerForm, 1, repeated=True)
