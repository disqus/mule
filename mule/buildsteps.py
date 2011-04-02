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

class StartQueueServer(ShellCommand):
    name = 'start queue server'
    description = 'starting queue server'
    descriptionDone = 'started queue server'
    
    def __init__(self, **kwargs):
        command = [
            r'VENV=$PWD/env;',
            
            # Add our venv to sys path
            r'PATH=$PATH:$VENV/bin;',

            # Tell mule to start its queue server
            r'mule start --host=%s:%s --pid=%s',
        ]
        
        kwargs['command'] = WithProperties("\n".join(command))
        
        ShellCommand.__init__(self, **kwargs)

class StopQueueServer(ShellCommand):
    name = 'start queue server'
    description = 'starting queue server'
    descriptionDone = 'started queue server'

    def __init__(self, **kwargs):
        command = [
            r'VENV=$PWD/env;',
            
            # Add our venv to sys path
            r'PATH=$PATH:$VENV/bin;',

            # Tell mule to start its queue server
            r'mule stop --pid=%s',

        ]
        
        kwargs['command'] = WithProperties("\n".join(command))
        
        ShellCommand.__init__(self, **kwargs)

class ProcessQueue(Trigger):
    name = 'publish queue'
    description = 'publishing queue'
    descriptionDone = 'published queue'
    
    def __init__(self, schedulerNames=['run_tests'], waitForFinish=True, **kwargs):
        Trigger.__init__(self, schedulerNames=schedulerNames, waitForFinish=waitForFinish, **kwargs)

class Bootstrap(ShellCommand):
    """
    Updates (or creates) the virtualenv, installing dependencies as needed.
    """
    
    name = 'bootstrap'
    flunkOnFailure = True
    haltOnFailure = True
    
    def __init__(self, **kwargs):
        command = [
            r'VENV=$PWD/env;',
            
            # Create or update the virtualenv
            r'$PYTHON virtualenv --no-site-packages $VENV || exit 1;',

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
        command.append("$PIP install -q -E $VENV -r requirements/global.txt")
        command.append("$PIP install -q -E $VENV -r requirements/test.txt")
        command.append("$PYTHON setup.py --quiet develop")
        
        kwargs['command'] = WithProperties("\n".join(command))
        
        ShellCommand.__init__(self, **kwargs)
        
        self.addFactoryArguments()

class TestDisqus(Test):
    """
    Runs Disqus' tests.
    """
    name = 'test'
        
    def __init__(self, verbosity=2, **kwargs):
        import uuid
        kwargs['command'] = [
            '$PWD/env/bin/python'
            'disqus/manage.py test',
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