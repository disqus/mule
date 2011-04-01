"""
How changes get from Git into the buildbot.
"""

from buildbot.changes.gitpoller import GitPoller

def get_change_source(giturl):
    return GitPoller(
        repourl = giturl,
        branch='master',
        pollinterval=2, # 2 seconds
    )
