#!/usr/bin/env python

from celery import current_app
from os.path import dirname, abspath
from unittest2.loader import defaultTestLoader

class TestConf:
    CELERY_RESULT_BACKEND = 'redis'
    CELERY_IMPORTS = ('mule.tasks', )

    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    REDIS_DB = 0

    BROKER_BACKEND = 'redis'

    BROKER_HOST = 'localhost'  # Maps to redis host.
    BROKER_PORT = 6379         # Maps to redis port.
    BROKER_VHOST = '0'         # Maps to database number.

def runtests():
    parent = dirname(abspath(__file__))
    #sys.path.insert(0, parent)
    current_app.config_from_object(TestConf)
    return defaultTestLoader.discover(parent)

if __name__ == '__main__':
    runtests()