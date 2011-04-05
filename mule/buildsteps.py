"""
Individual custom build steps for the Django tests.

See the docstring in builders.py for an overview of how these all fit together.

I'm using subclasses (instead of just passing arguments) since it makes the
overall build factory in builders.py easier to read. Unfortunately it makes some
of what's going here a bit more confusing. Win some, lose some.
"""

from buildbot.steps.shell import Test, ShellCommand
from buildbot.steps.trigger import Trigger
from buildbot.process.properties import WithProperties

import zmq

class StartQueueServer(ShellCommand):
    name = 'start queue server'
    description = 'starting queue server'
    descriptionDone = 'started queue server'
    flunkOnFailure = True
    haltOnFailure = True
    
    def __init__(self, **kwargs):
        command = [
            r'VENV=$PWD/env;',
            
            # Add our venv to sys path
            r'PATH=$PATH:$VENV/bin;',
            
            # Prepend our new $PYTHONPATH
            r'PYTHONPATH=$VENV/lib/python2.6/site-packages:$PYTHONPATH;',
            
            # We need the django settings module setup to import
            r'DJANGO_SETTINGS_MODULE=disqus.conf.settings.test',

            # Tell mule to start its queue server
            r'mule start --host=%s:%s --pid=%%(mulepid)s $PWD/disqus' % ('0.0.0.0', '9001',),
        ]
        
        kwargs['command'] = WithProperties("\n".join(command))
        
        ShellCommand.__init__(self, **kwargs)
    
    def start(self):
        self.build.setProperty('mulepid', 'mule.pid', 'StartQueueServer')
        ShellCommand.start(self)

class StopQueueServer(ShellCommand):
    name = 'stop queue server'
    description = 'stopping queue server'
    descriptionDone = 'stopped queue server'
    flunkOnFailure = True
    haltOnFailure = True

    def __init__(self, **kwargs):
        command = [
            r'VENV=$PWD/env;',
            
            # Add our venv to sys path
            r'PATH=$PATH:$VENV/bin;',

            # Tell mule to start its queue server
            r'mule stop --pid=%(mulepid)s',

        ]
        
        kwargs['command'] = WithProperties("\n".join(command))
        
        ShellCommand.__init__(self, **kwargs)

class ProcessQueue(Trigger):
    def __init__(self, schedulerNames=['run_tests'], waitForFinish=True, **kwargs):
        kwargs.update({
            'schedulerNames': schedulerNames,
            'waitForFinish': waitForFinish,
            'updateSourceStamp': True,
            'flunkOnFailure': True,
            'haltOnFailure': True,
            'name': 'publish queue',
        })
        Trigger.__init__(self, **kwargs)

class Bootstrap(ShellCommand):
    """
    Updates (or creates) the virtualenv, installing dependencies as needed.
    """
    
    name = 'bootstrap'
    description = 'bootstrap'
    descriptionDone = 'bootstrapped'
    
    flunkOnFailure = True
    haltOnFailure = True
    
    def __init__(self, **kwargs):
        command = [
            r'VENV=$PWD/env;',
            
            # Create or update the virtualenv
            r'virtualenv --no-site-packages $VENV || exit 1;',

            # Reset $PYTHON and $PIP to the venv python
            r'PYTHON=$VENV/bin/python;',
            r'PIP=$VENV/bin/pip;',
        ]
        
        kwargs['command'] = WithProperties("\n".join(command))
        
        ShellCommand.__init__(self, **kwargs)

class UpdateVirtualenv(ShellCommand):
    """
    Updates (or creates) the virtualenv, installing dependencies as needed.
    """
    
    name = 'virtualenv setup'
    description = 'updating env'
    descriptionDone = 'updated env'
    flunkOnFailure = True
    haltOnFailure = True
    
    def __init__(self, **kwargs):
        command = [
            r'VENV=$PWD/env;',

            # Reset $PYTHON and $PIP to the venv python
            r'PYTHON=$VENV/bin/python;',
            r'PIP=$VENV/bin/pip;',
        ]
        
        # Install database dependencies if needed.
        command.append("$VENV/bin/python setup.py develop")
        
        kwargs['command'] = WithProperties("\n".join(command))
        
        ShellCommand.__init__(self, **kwargs)
        
        self.addFactoryArguments()

class TestDisqus(Test):
    """
    Runs Disqus' tests.
    """
    name = 'test'
        
    def __init__(self, host, verbosity=2, **kwargs):
        import uuid
        kwargs['command'] = [
            '$PWD/env/bin/python',
            '$PWD/disqus/manage.py test',
            '--settings=disqus.conf.settings.test',
            '--db-prefix=buildbot_%s' % uuid.uuid4().hex,
            '--xml',
            '--noinput',
            '--verbosity=%s' % verbosity,
        ]
        kwargs['env'] = {
            'PYTHONPATH': '$PWD:$PWD/tests',
            'LC_ALL': 'en_US.utf8',
        }
        
        Test.__init__(self, **kwargs)
        
        # Make sure not to spuriously count a warning from test cases
        # using the word "warning". So skip any "warnings" on lines starting
        # with "test_"
        self.addSuppression([(None, "^test_", None, None)])
        
        self.addFactoryArguments(verbosity=verbosity)

    def start(self):
        def new_client(context, host):
            client = context.socket(zmq.REQ)
            client.connect('tcp://%s' % host)
            return client

        host = self.build.getProperty('mulehost')

        context = zmq.Context()

        client = new_client(context, host)

        global_retries = 3
        
        # TODO: we should be setting up our database here
        
        while global_retries:
            fetch_retries = 3
            while fetch_retries:
                fetch_retries -= 1
                resp = client.send('GET')
                poller = zmq.Poller()
                poller.register(client, zmq.POLLIN)
                socks = poller.poll()
                # if we got a reply, process it
                if socks:
                    reply = client.recv()
                    if reply:
                        # TODO: this needs to run this job with no db setup/teardown
                        TestDisqus.start(self)
                    else:
                        print 'E: malformed reply from server: %s' % reply
                else:
                    print 'W: no response from server, retrying...'
                    client = new_client(context, host)
                    client.send('GET')

        # TODO: we should be tearing down our database here