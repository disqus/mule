"""
Sentry
~~~~~~
"""

try:
    VERSION = __import__('pkg_resources') \
        .get_distribution('Mule').version
except Exception, e:
    VERSION = 'unknown'