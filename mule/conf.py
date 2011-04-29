DEFAULT_QUEUE = 'default'
BUILD_QUEUE_PREFIX = 'mule'

# TODO: better sane defaults?
WORKSPACE_PATH = 'workspace'

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