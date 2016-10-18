#!/usr/bin/env python

from datetime import datetime
import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from exceptions import *
from models import *
from forms import *
from utils import *
from settings import *


@endpoints.api(name='conference',
               version='v1',
               audiences=[ANDROID_AUDIENCE],
               allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID,
                                   ANDROID_CLIENT_ID, IOS_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):

    """Conference API v0.1"""

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm"""
        user = endpoints.get_current_user()
        user_id = check_auth()

        if not request.name:
            raise endpoints.BadRequestException(
                "Conference 'name' field required")

        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        if data['startDate']:
            data['startDate'] = datetime.strptime(
                data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(
                data['endDate'][:10], "%Y-%m-%d").date()

        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        Conference(**data).put()
        taskqueue.add(params={'email': user.email(),
                              'conferenceInfo': repr(request)},
                      url='/tasks/send_confirmation_email')
        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user_id = check_auth()

        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}

        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        for field in request.all_fields():
            data = getattr(request, field.name)
            if data not in (None, []):
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(ConferenceForm, ConferenceForm,
                      path='conference',
                      http_method='POST',
                      name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='PUT',
                      name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='GET',
                      name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='getConferencesCreated',
                      http_method='POST',
                      name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        user_id = check_auth()

        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        return ConferenceForms(
            items=[self._copyConferenceToForm(
                conf, getattr(prof, 'displayName')) for conf in confs]
        )

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""

        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(
                filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name)
                     for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator.")

            if filtr["operator"] != "=":
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences',
                      http_method='POST',
                      name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        organisers = [(ndb.Key(Profile, conf.organizerUserId))
                      for conf in conferences]
        profiles = ndb.get_multi(organisers)

        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in
                   conferences])

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return Profile from datastore. create new one if non-existent."""
        user_id = check_auth()
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
            )
            profile.put()

        return profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        prof = self._getProfileFromUser()

        if save_request:
            for field in ('displayName'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        prof.put()
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm,
                      path='profile',
                      http_method='GET',
                      name='get_profile')
    def get_profile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm,
                      path='profile',
                      http_method='POST',
                      name='save_profile')
    def save_profile(self, request):
        """Update profile."""
        return self._doProfile(request)

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)
        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/announcement/get',
                      http_method='GET',
                      name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        if reg:
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        else:
            if wsck in prof.conferenceKeysToAttend:
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET',
                      name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck)
                     for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)
        organisers = [ndb.Key(Profile, conf.organizerUserId)
                      for conf in conferences]
        profiles = ndb.get_multi(organisers)
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])
                                      for conf in conferences])

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='POST',
                      name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='DELETE',
                      name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)

    def _copySpeakerToForm(self, speaker):
        """Copy relevant fields from Speaker to SpeakerForm."""
        sf = SpeakerForm()
        for field in sf.all_fields():
            if hasattr(speaker, field.name):
                setattr(sf, field.name, getattr(speaker, field.name))
        sf.check_initialized()
        return sf

    def _createSpeakerObject(self, request):
        """Create or update Speaker object, returning SpeakerForm/request."""
        user_id = check_auth()
        if not request.name:
            raise endpoints.BadRequestException(
                "Speaker 'name' field required")

        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}
        Speaker(**data).put()
        return request

    @endpoints.method(SpeakerForm, SpeakerForm,
                      path='speaker/new',
                      http_method='POST',
                      name='new_speaker')
    def new_speaker(self, request):
        """Create a new Speaker"""
        return self._createSpeakerObject(request)

    @endpoints.method(SPEAKER_REQUEST, SpeakerForms,
                      path='speakers/{websafeConferenceKey}',
                      http_method='POST',
                      name='get_speakers')
    def get_speakers(self, request):
        """Return all Speakers for given Conference."""
        user_id = check_auth()
        sessions = Session.query(
            Session.conference_key == request.conference_key)
        speakers = ndb.get_multi([i.speaker_id for i in sessions])

        return SpeakerForms(
            items=[self._copySpeakerToForm(s) for s in speakers])

    @staticmethod
    def _checkFeaturedSpeaker(confKey, speaker):
        """Checks featured speaker"""
        q = Session.query(ndb.AND(
            Session.speaker_id == speaker,
            Session.conference_key == confKey))
        return True if q.count() >= 2 else False

    @staticmethod
    def _setFeaturedSpeaker(confKey, speaker_id):
        """Sets memcache Featured Speakers announcement"""
        speaker = ndb.Key(Speaker, int(speaker_id))
        q = Session.query(ndb.AND(
            Session.speaker_id == speaker,
            Session.conference_key == confKey))
        sessions = [i.title for i in q]

        if q.count() >= 2:
            speakerAnounncement = FEATURED_SPEAKER % (
                speaker.get().name, ', '.join(sessions))
            memcache.set(MEMCACHE_SPEAKER_KEY, speakerAnounncement)
        return True

    def _copySessionToForm(self, session):
        """Session to SessionForm"""
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(session, field.name):
                if field.name.endswith('time'):
                    setattr(
                        sf, field.name, getattr(session, field.name).strftime('%H:%M'))
                elif field.name == "speaker_id":
                    print ''
                else:
                    setattr(sf, field.name, getattr(session, field.name))
            elif field.name == "websafeKey":
                setattr(sf, field.name, session.key.urlsafe())
        sf.check_initialized()
        return sf

    def _createSessionObject(self, request):
        """Create or update Session object, returning SessionForm/request."""
        user_id = check_auth()
        organizer = Conference.query(
            Conference.organizerUserId == request.organizer_id)
        if not organizer:
            raise endpoints.UnauthorizedException(
                'Must be conference organizer to create session')

        if not request.title:
            raise endpoints.BadRequestException(
                "Session 'title' field required")

        data = {field.name: getattr(request, field.name)
                for field in request.all_fields()}

        data['start_time'] = datetime.strptime(
            data['start_time'], '%H:%M').time()

        p_key = ndb.Key(Profile, user_id)
        s_id = Session.allocate_ids(size=1, parent=p_key)[0]
        s_key = ndb.Key(Session, s_id, parent=p_key)
        data['key'] = s_key
        data['organizer_id'] = request.organizer_id = user_id
        data['speaker_id'] = ndb.Key(Speaker, request.speaker_id)
        data['speaker_name'] = ndb.Key(Speaker, request.speaker_id).get().name

        Session(**data).put()
        if self._checkFeaturedSpeaker(request.conference_key, data['speaker_id']):
            taskqueue.add(params={
                'speaker_id': request.speaker_id,
                'conf': request.conference_key},
                url='/tasks/set_featured_speaker')
        return request

    @endpoints.method(SessionForm, SessionForm,
                      path='session/new',
                      http_method='POST',
                      name='new_session')
    def new_session(self, request):
        """Creates new session"""
        return self._createSessionObject(request)

    @endpoints.method(SessionByConfForm, SessionForms,
                      path='conference/sessions',
                      http_method='POST',
                      name='conference_sessions')
    def conference_sessions(self, request):
        """Returns session conference."""
        user_id = check_auth()
        query = Session.query().filter(
            Session.conference_key == request.conference_key)

        return SessionForms(
            items=[self._copySessionToForm(session) for session in query])

    @endpoints.method(SessionByLocationForm, SessionForms,
                      path='sessions/location',
                      http_method='POST',
                      name='sessions_by_location')
    def sessions_by_location(self, request):
        """Returns session search by location"""
        user_id = check_auth()
        q = Session.query().filter(Session.conference_key == request.conference_key).filter(
            Session.lcoation == request.location)

        return SessionForms(
            items=[self._copySessionToForm(session) for session in q]
        )

    @endpoints.method(SessionByTypeForm, SessionForms,
                      path='sessions/type',
                      http_method='POST',
                      name='sessions_by_type')
    def sessions_by_type(self, request):
        """Returns session search by type"""
        user_id = check_auth()
        q = Session.query().filter(Session.conference_key == request.conference_key).filter(
            Session.session_type == request.session_type)

        return SessionForms(
            items=[self._copySessionToForm(session) for session in q]
        )

    @endpoints.method(SPEAKER_REQUEST, StringMessage,
                      path='speaker/featured',
                      http_method='GET',
                      name='featured_speaker')
    def featured_speaker(self, request):
        """Returns featured speaker"""
        return StringMessage(data=memcache.get(MEMCACHE_SPEAKER_KEY) or "")

    def _getSessionQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Session.query()
        inequality_filter, filters = self._sessionFormatFilters(
            request.filters)

        if not inequality_filter:
            q = q.order(Session.title)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Session.title)

        for f in filters:
            if f["field"] == "duration":
                try:
                    f["value"] = int(f["value"])
                except:
                    raise endpoints.BadRequestException(
                        "Invalid duration value")

            elif f["field"] == "start_time":
                try:
                    f['value'] = datetime.strptime(
                        f['value'], '%H:%M').time()
                except:
                    raise endpoints.BadRequestException(
                        "Invalid start time value")

                if f['operator'] == '=':
                    q = q.filter(Session.start_time == f['value'])
                elif f['operator'] == '>':
                    q = q.filter(Session.start_time > f['value'])
                elif f['operator'] == '>=':
                    q = q.filter(Session.start_time >= f['value'])
                elif f['operator'] == '<':
                    q = q.filter(Session.start_time < f['value'])
                elif f['operator'] == '<=':
                    q = q.filter(Session.start_time <= f['value'])
                elif f['operator'] == '!=':
                    q = q.filter(Session.start_time != f['value'])

            if f["field"] != "start_time":
                formatted_query = ndb.query.FilterNode(
                    f["field"], f['operator'], f['value'])
                q = q.filter(formatted_query)
        return q

    def _sessionFormatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""

        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name)
                     for field in f.all_fields()}

            try:
                filtr["field"] = SESSIONFIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator.")

            if filtr["operator"] != "=":
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(SessionQueryForms, SessionForms,
                      path='sessions/query',
                      http_method='POST',
                      name='session_query')
    def session_query(self, request):
        """Query for sessions"""
        sessions = self._getSessionQuery(request)
        return SessionForms(items=[self._copySessionToForm(i) for i in sessions])

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='problemQuery',
                      http_method='POST',
                      name='problem_query')
    def problem_query(self, request):
        """Fixed inequality query"""
        a = Session.query(Session.session_type != 'Workshop')
        b = Session.query(Session.start_time < datetime(1970, 01, 01, 19, 00, 00).time())
        keys = set([i.key for i in list(a)]) & set([i.key for i in list(b)])
        sessions = ndb.get_multi(keys)
        return SessionForms(items=[self._copySessionToForm(s) for s in sessions])

    def _updateWishlist(self, request, register=True, msg=True):
        """Add or Remove session from wishlist."""
        prof = self._getProfileFromUser()

        if register and request.sessionKey not in prof.sessionKeysToAttend:
            prof.sessionKeysToAttend.append(request.sessionKey)
        elif not register:
            if request.sessionKey in prof.sessionKeysToAttend:
                prof.sessionKeysToAttend.remove(request.sessionKey)
            else:
                msg = False

        prof.put()
        return BooleanMessage(data=msg)

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='user/wishlist',
                      http_method='GET',
                      name='get_wishlist')
    def get_wishlist(self, request):
        """Get sessions in a user's wishlist"""

        user_id = getUserId(endpoints.get_current_user())
        prof = self._getProfileFromUser()
        s_keys = [ndb.Key(Session, s_id, parent=ndb.Key(Profile, user_id))
                  for s_id in prof.sessionKeysToAttend]
        return SessionForms(
            items=[self._copySessionToForm(i) for i in ndb.get_multi(s_keys)])

    @endpoints.method(WISHLIST_REQUEST, BooleanMessage,
                      path='user/wishlist/add',
                      http_method='POST',
                      name='add_session')
    def add_session(self, request):
        """Add session to wishlist."""
        return self._updateWishlist(request)

    @endpoints.method(WISHLIST_REQUEST, BooleanMessage,
                      path='user/wishlist/remove',
                      http_method='DELETE',
                      name='remove_session')
    def remove_session(self, request):
        """Remove session from wishlist."""
        return self._updateWishlist(request, register=False)


api = endpoints.api_server([ConferenceApi])
