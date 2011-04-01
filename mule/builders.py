"""
Actual build definitions.

This is kinda complex, so here's a high-level overview of exactly how the build
process works:

The main point is to assume as little as possible about the build slave (and
thus transfer as much smartsfrom the master to the slave as possible). The slave
just needs to assure that Python is installed, a database is accessible (according
to the slave config), and whatever headers needed to build database modules exist.

The steps, then, are:

    * Checkout the repository.
    
    * Bootstrap virtualenv.
    
    * Create a virtualenv sandbox and install any extra prereqs (database
      modules, really).
      
    * Generate a Django settings file from the slave config.
    
    * Run test suite using that settings file.

This sandbox is shared for each (python, database) combination; this prevents
needing to build the database wrappers each time.

However, this *does* mean that we can't test installing Django (via setup.py
install or friends) and that the tests pass against the *installed* files (which
hasn't always been true in the past). If we did, and if a buildslave wanted
to run multuple builds in parallel, we'd get conflicts. Also, if we install
the recommended way (setup.py install), then we can't uninstall easily.

So that's a big FIXME for later. Perhaps there's a clever way to have a new
virtualenv for each build but still avoid re-building database bindings...
"""

from buildbot.config import BuilderConfig
from buildbot.process.factory import BuildFactory
from buildbot.steps.source import Git
from . import buildsteps

def get_next_collector_build(builder, requests):
    """
    Prioritize stable, then master, then all others.
    """
    best = requests[0]
    for r in requests:
        if r.source.branch == 'stable':
            return r
        elif r.source.branch == 'master':
            best = r
    return best

def get_next_collector_slave(available_slaves):
    return available_slaves[0]

def get_next_runner_slave(available_slaves):
    return available_slaves[0]

def get_builders(giturl, slaves):
    """
    Gets a list of builders for entry in BuildmasterConfig['builders']
    """
    # Make a builder config for this combo.
    builders = [BuilderConfig(
        name = 'collector',
        factory = make_collector_factory(giturl),
        nextSlave = get_next_collector_slave,
        nextBuild = get_next_collector_build,
        slavenames = [s.slavename for s in slaves],
    ), BuilderConfig(
        name = 'runner',
        factory = make_runner_factory(giturl),
        nextSlave = get_next_runner_slave,
        slavenames = [s.slavename for s in slaves],
    )]
        
    return builders

def make_collector_factory(giturl):
    f = BuildFactory()
    f.addSteps([
        Git(repourl=giturl, mode='copy'),
        buildsteps.Bootstrap(),
        buildsteps.UpdateVirtualenv(),
        buildsteps.BuildQueue(),
        buildsteps.RunQueueServer(),
        buildsteps.ProcessQueue(),
        buildsteps.StopQueueServer(),
    ])
    return f

def make_runner_factory(giturl):
    """
    Generates the BuildFactory (e.g. set of build steps). The series of steps is described
    in the module docstring, above.
    """
    f = BuildFactory()
    f.addSteps([
        Git(repourl=giturl, mode='copy'),
        buildsteps.Bootstrap(),
        buildsteps.UpdateVirtualenv(),
        buildsteps.TestDisqus(verbosity=1),
    ])
    return f