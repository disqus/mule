from celery.task import task
from celery.worker.control import Panel
from mule import conf

import os
import subprocess
import shlex
import time

def execute_bash(workspace, name, script, **env):
    with open(os.path.join(workspace, name), 'w') as fp:
        fp.write(script)

    cmd = 'sh %s' % (name,)

    # Setup our environment variables
    env = os.environ.copy()
    env.update(**env)
    # TODO: confirm this changes dir
    env['CWD'] = workspace
    env['WORKSPACE'] = workspace

    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env)

    (stdout, stderr) = proc.communicate()

    proc.wait()
    
    # check exit code
    if proc.retcode!= 0:
        # TODO: support proper failures on bootstrap
        raise
    
    return (stdout, stderr)

@Panel.register
def mule_provision(panel, build_id, workspace=None, script=None):
    """
    This task has two jobs:

    1. Leaves the default Mule queue, and joins a new build-specific queue.

    2. Ensure that we're bootstrapped for this build.

       This includes:
         - Doing a git fetch
         - Setting up a virtualenv
         - Building our DB
    """
    assert not script or workspace, "Cannot pass scripts without a workspace"
    
    queue_name = '%s-%s' % (conf.BUILD_QUEUE_PREFIX, build_id)

    cset = panel.consumer.task_consumer
    
    if conf.DEFAULT_QUEUE not in [q.name for q in cset.queues]:
        return {
            "status": "fail",
            "reason": "worker is already in use"
        }
    
    cset.cancel_by_queue(conf.DEFAULT_QUEUE)
    
    if workspace:
        work_path = os.path.join(conf.ROOT, 'workspaces', workspace)
    
        # XXX: we could send along a workspace parameter and
        # support concurrent builds on the same machine (to an extent)
        # Setup our workspace and run any bootstrap tasks
        if not os.path.exists(work_path):
            os.makedirs(work_path)
    
        # Create a temporary bash script in workspace, setup env, and
        # execute
        if script:
            execute_bash(work_path, 'setup.sh', script, BUILD_ID=build_id)
    
    declaration = dict(queue=queue_name, exchange_type='direct')
    queue = cset.add_consumer_from_dict(**declaration)
    # XXX: There's currently a bug in Celery 2.2.5 which doesn't declare the queue automatically
    channel = cset.channel
    queue(channel).declare()
    # channel = cset.connection.channel()
    # try:
    #     queue(channel).declare()
    # finally:
    #     channel.close()
    cset.consume()
    panel.logger.info("Started consuming from %r" % (declaration, ))

    return {
        "status": "ok",
        "build_id": build_id,
    }

@Panel.register
def mule_teardown(panel, build_id, workspace=None, script=None):
    """
    This task has two jobs:
    
    1. Run any bootstrap teardown

    2. Leaves the build-specific queue, and joins the default Mule queue.
    """
    assert not script or workspace, "Cannot pass scripts without a workspace"
    
    queue_name = '%s-%s' % (conf.BUILD_QUEUE_PREFIX, build_id)

    cset = panel.consumer.task_consumer
    channel = cset.channel
    # kill all jobs in queue
    channel.queue_purge(queue=queue_name)
    # stop consuming from queue
    cset.cancel_by_queue(queue_name)
    
    if workspace:
        work_path = os.path.join(conf.ROOT, 'workspaces', workspace)
    
        # Create a temporary bash script in workspace, setup env, and
        # execute
        if script:
            execute_bash(work_path, 'teardown.sh', script, BUILD_ID=build_id)
    
    queue = cset.add_consumer_from_dict(queue=conf.DEFAULT_QUEUE)
    # XXX: There's currently a bug in Celery 2.2.5 which doesn't declare the queue automatically
    queue(channel).declare()

    # start consuming from default
    cset.consume()

    panel.logger.info("Rejoined default queue")

    return {
        "status": "ok",
        "build_id": build_id,
    }


@task(ignore_result=False)
def run_test(build_id, runner, job, callback=None):
    """
    Spawns a test runner and reports the result.
    """
    # TODO: we shouldnt need to do this, bash should do it
    build_id = build_id.encode('utf-8')
    job = job.encode('utf-8')

    cmd = runner.encode('utf-8').replace('$TEST', job)
    cmd = cmd.replace('$BUILD_ID', build_id)

    # Setup our environment variables
    env = os.environ.copy()
    env['TEST'] = job
    env['BUILD_ID'] = build_id
    
    start = time.time()
    
    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env)

    (stdout, stderr) = proc.communicate()

    proc.wait()

    stop = time.time()

    result = {
        "timeStarted": start,
        "timeFinished": stop,
        "retcode": proc.returncode,
        "build_id": build_id,
        "job": job,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }

    if callback:
        callback(result)
    return result