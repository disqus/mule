"""
Default configuration values for Mule.

These can be overrriden (in bulk) using:

>>> mule.utils.conf.configure(**settings)
"""


DEFAULT_QUEUE = 'default'
BUILD_QUEUE_PREFIX = 'mule'

# TODO: this should be some kind of absolute system path, and a sane default
ROOT = 'mule'

WORKSPACES = {
    'default': {
        # setup/teardown should either be an absolute path to a bash script (/foo/bar.sh)
        # or a string containing bash commands
        #
        # global env variables made available:
        # - $BUILD_ID
        # - $WORKSPACE (full path to workspace directory)
        'setup': None,
        'teardown': None,
    }
}