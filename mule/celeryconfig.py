# This is just an example configuration file

CELERY_RESULT_BACKEND = 'redis'
CELERY_IMPORTS = ('mule.tasks', )

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

BROKER_BACKEND = 'redis'

BROKER_HOST = 'localhost'  # Maps to redis host.
BROKER_PORT = 6379         # Maps to redis port.
BROKER_VHOST = '0'         # Maps to database number.
