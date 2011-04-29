from django.conf import settings
from mule.tasks import *
from mule.utils.conf import configure

# HACK: ensure Django configuratio is read in
configure(**getattr(settings, 'MULE_CONFIG', {}))
