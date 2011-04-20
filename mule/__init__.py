"""
Sentry
~~~~~~
"""
from mule.utils.conf import configure

__all__ = ('VERSION', 'configure')

try:
    VERSION = __import__('pkg_resources') \
        .get_distribution('Mule').version
except Exception, e:
    VERSION = 'unknown'

