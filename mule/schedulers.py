from buildbot.schedulers.basic import Scheduler
from buildbot.schedulers.triggerable import Triggerable

def get_schedulers(builders):
    """
    Make a build scheduler.
    """
    return [make_collector_scheduler(builders), make_runner_scheduler(builders)]

def make_collector_scheduler(builders):
    return Scheduler(
        name = 'collect_tests',
        branch = None,
        treeStableTimer = 10,
        builderNames = ['collector']
    )

def make_runner_scheduler(builders):
    return Triggerable(
        name = 'run_tests',
        builderNames = ['runner']
    )