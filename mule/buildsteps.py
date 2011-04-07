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
        kwargs['workdir'] = '.'
        ShellCommand.__init__(self, **kwargs)

    def start(self):
        # set up self.command as a very long sh -c invocation
        command = [
            'VE=$PWD/env',
            
            # Add our venv to sys path
            'PATH=$VE/bin:$PATH',
            
            # Adjust $PYTHON
            'PYTHON=$VE/bin/python',
            
            # Prepend our new $PYTHONPATH
            'PYTHONPATH=$VE/lib/python2.6/site-packages:$PYTHONPATH',
        ]

        # set up the virtualenv if it does not already exist
        command.append("virtualenv --no-site-packages $VE || exit 1")

        # HACK: local only, install mule
        command.append("cd /Users/dcramer/Development/mule/ && $PYTHON setup.py develop && cd - || exit 1")
        # command.append("pip install Mule || exit 1")

        # Install our main package
        command.append("cd $PWD/build/ && $PYTHON setup.py develop && cd - || exit 1")

        self.command = ';\n'.join(command)
        return ShellCommand.start(self)

class StartQueueServer(ShellCommand):
    name = 'start queue serve'
    description = 'starting queue serve'
    descriptionDone = 'started queue serve'
    flunkOnFailure = True
    haltOnFailure = True
    
    def __init__(self, **kwargs):
        kwargs['workdir'] = '.'
        ShellCommand.__init__(self, **kwargs)
    
    def start(self):
        self.build.setProperty('mulepid', 'mule.pid', 'StartQueueServe')
        self.build.setProperty('mulehost', '0.0.0.0:9001', 'StartQueueServe')

        command = [
            'VE=$PWD/env',
            
            # Add our venv to sys path
            'PATH=$VE/bin:$PATH',
            
            # Adjust $PYTHON
            'PYTHON=$VE/bin/python',
            
            # We need the django settings module setup to import
            'DJANGO_SETTINGS_MODULE=disqus.conf.settings.test',
            
            # Tell mule to start its queue server
            'mule start --host=%(mulehost)s --pid=%(mulepid)s $PWD/build/disqus || exit 1',
        ]
        
        self.command = WithProperties("\n".join(command))
        
        ShellCommand.start(self)

class StopQueueServer(ShellCommand):
    name = 'stop queue serve'
    description = 'stopping queue serve'
    descriptionDone = 'stopped queue serve'
    flunkOnFailure = True
    haltOnFailure = True

    def __init__(self, **kwargs):
        kwargs['workdir'] = '.'
        kwargs['alwaysRun'] = True
        
        command = [
            'VE=$PWD/env',
            
            # Add our venv to sys path
            'PATH=$VE/bin:$PATH',

            # Tell mule to start its queue server
            'mule stop --pid=%(mulepid)s || exit 1',
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
            'copy_properties': ['mulehost', 'mulepid']
        })
        Trigger.__init__(self, **kwargs)

class TestDisqus(Test):
    """
    Runs Disqus' tests.
    """
    name = 'test'
        
    def __init__(self, verbosity=2, **kwargs):
        kwargs['workdir'] = '.'

        Test.__init__(self, **kwargs)

        # Make sure not to spuriously count a warning from test cases
        # using the word "warning". So skip any "warnings" on lines starting
        # with "test_"
        self.addSuppression([(None, "^test_", None, None)])
        
        self.addFactoryArguments(verbosity=verbosity)

    def start(self):
        import uuid
        
        test_command = [
            '$PWD/env/bin/python',
            '$PWD/disqus/manage.py test',
            '--settings=disqus.conf.settings.test',
            '--db-prefix=buildbot_%(buildername)s_%(build_number)s',
            '--xml',
            '--noinput',
            '--verbosity=%(verbosity)s',
        ]

        command = [
            'export VE=$PWD/env',
            
            # Add our venv to sys path
            'export PATH=$VE/bin:$PATH',
            
            # Adjust $PYTHON
            'export PYTHON=$VE/bin/python',
            
            # Prepend our new $PYTHONPATH
            'export PYTHONPATH=$VE/lib/python2.6/site-packages:$PYTHONPATH',
            
            # Tell mule to start its queue server
            'mule runtests --host=%%(mulehost)s $PWD/build/disqus %(command)s || exit 1' % dict(
                command=test_command,
            ),
        ]
        
        self.command = WithProperties(";\n".join(command))
        
        ShellCommand.start(self)