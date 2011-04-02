"""
Auth provider that authenticates against django.contrib.auth.

This is currently half-assed and assumes that django.settings.configure() has
already been called by the time that DjangoAuth.authenticate gets called, and
that the database is set up correctly, etc.

Bu default, this only authenticates users who are is_staff=True, but you can
override that by subclassing and overriding user_has_access().
"""

from zope.interface import implements
from buildbot.status.web import auth

class DisqusAuth(auth.AuthBase):
    implements(auth.IAuth)
    
    def user_has_access(self, user):
        return True

    def authenticate(self, username, password):
        # TODO:
        return True
        # from django.contrib.auth.models import User
        # try:
        #     user = User.objects.get(username=username)
        # except User.DoesNotExist:
        #     return False
        #     
        # return user.check_password(password) and self.user_has_access(user)