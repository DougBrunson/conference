import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb


class ConflictException(endpoints.ServiceException):

    """ConflictException -- exception mapped to HTTP 409 response"""
    http_status = httplib.CONFLICT
