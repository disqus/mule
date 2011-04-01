"""
Defines slaves and their capabilities.

Some of the ideas here come from Buildbot's buildbot:
http://github.com/buildbot/metabbotcfg/blob/master/slaves.py.
"""

from buildbot.buildslave import BuildSlave

def get_slaves(secrets):
    """
    Get the list of slaves to insert into BuildmasterConfig['slaves'].
    """
    
    # Read in secret passwords (and a default) from the secrets config.
    passwords = secrets['slaves']['passwords']
    default_password = secrets['slaves']['passwords'].get('*')
    
    # Send back a list of BuildSlave instances.
    # (this should be all VMs)
    return [
        BuildSlave("example-slave", passwords.get("example-slave", default_password))
    ]
