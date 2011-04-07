"""
How changes get from Git into the buildbot.
"""

from buildbot.changes.gitpoller import GitPoller

import os.path

def get_change_source(giturl, workpath):
    return GitPoller(
        repourl = giturl,
        branch = 'master',
        project = 'disqus',
        workdir = os.path.join(workpath, 'disqus', 'repo'),
        pollinterval = 20000, # 2 seconds
    )
