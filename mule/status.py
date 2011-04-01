from buildbot.status import html, words
from buildbot.status.web.authz import Authz
from .auth import DisqusAuth

authz = Authz(
    auth = DisqusAuth(),
    gracefulShutdown = 'auth',
    forceBuild = 'auth',
    forceAllBuilds = 'auth',
    pingBuilder = 'auth',
    stopBuild = 'auth',
    stopAllBuilds = 'auth',
    cancelPendingBuild = 'auth',
    stopChange = 'auth',
    cleanShutdown = 'auth',
)

def get_status(secrets):
    return [
        html.WebStatus(
            http_port = '8010',
            authz = authz,
            order_console_by_time = True,
            revlink = 'http://code.disqus.net/projects/disqus/repository/revisions/%s',
            changecommentlink = (
                r'\b#(\d+)\b',
                r'http://code.disqus.net/issues/\1',
                r'Ticket \g<0>'
            )
        ),
   
        words.IRC(
            host = 'irc.freenode.net',
            channels = ['#disqus'],
            nick = 'dsq-buildbot',
            password = str(secrets['irc']['password']),
            notify_events = {
                'successToFailure': True,
                'failureToSuccess': True,
            }
        ),
    ]