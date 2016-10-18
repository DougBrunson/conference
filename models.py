#!/usr/bin/env python

"""models.py

Udacity conference server-side Python App Engine data & ProtoRPC models

$Id: models.py,v 1.1 2014/05/24 22:01:10 wesc Exp $

created/forked from conferences.py by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb


class Profile(ndb.Model):

    """Profile -- User profile object"""
    displayName = ndb.StringProperty()
    mainEmail = ndb.StringProperty()
    conferenceKeysToAttend = ndb.StringProperty(repeated=True)
    sessionKeysToAttend = ndb.IntegerProperty(repeated=True)


class Conference(ndb.Model):

    """Conference -- Conference object"""
    name = ndb.StringProperty(required=True)
    description = ndb.StringProperty()
    organizerUserId = ndb.StringProperty()
    topics = ndb.StringProperty(repeated=True)
    city = ndb.StringProperty()
    startDate = ndb.DateProperty()
    month = ndb.IntegerProperty()
    endDate = ndb.DateProperty()
    maxAttendees = ndb.IntegerProperty()
    seatsAvailable = ndb.IntegerProperty()

# ---------------- begin added models --------------------------------

class Session(ndb.Model):
    conference_key = ndb.StringProperty(required=True)
    title = ndb.StringProperty(required=True)
    session_type = ndb.StringProperty(required=True)
    highlights = ndb.StringProperty(default='')
    organizer_id = ndb.StringProperty()
    speaker_id = ndb.KeyProperty()
    speaker_name = ndb.StringProperty()
    start_time = ndb.TimeProperty()
    duration = ndb.IntegerProperty()
    location = ndb.StringProperty(default='')


class Speaker(ndb.Model):
    name = ndb.StringProperty(required=True)


