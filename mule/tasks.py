from celery.task import task
from celery.worker.control import Panel
from mule import conf

import os
import subprocess
import shlex
import time

__all__ = ('mule_setup', 'mule_teardown', 'run_test')

def join_queue(cset, name, **kwargs):
    queue = cset.add_consumer_from_dict(queue=name, **kwargs)
    # XXX: There's currently a bug in Celery 2.2.5 which doesn't declare the queue automatically
    channel = cset.channel
    queue(channel).declare()

    # start consuming from default
    cset.consume()

def execute_bash(workspace, name, script, **env_kwargs):
    script_path = os.path.join(workspace, name)

    with open(script_path, 'w') as fp:
        fp.write(script)

    cmd = 'sh %s' % script_path.encode('utf-8')

    # Setup our environment variables
    env = os.environ.copy()
    for k, v in env_kwargs.iteritems():
        env[k] = v
    env['CWD'] = workspace
    env['WORKSPACE'] = workspace

    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env)

    (stdout, stderr) = proc.communicate()

    # check exit code
    if proc.returncode!= 0:
        # TODO: support proper failures on bootstrap
        raise Exception(stderr)
    
    return (stdout.strip(), stderr.strip())

@Panel.register
def mule_setup(panel, build_id, workspace=None, script=None):
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
    
    script_result = ('', '')
    
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
            try:
                script_result = execute_bash(work_path, 'setup.sh', script, BUILD_ID=build_id)
            except:
                # If our teardown fails we need to ensure we rejoin the queue
                join_queue(cset, name=conf.DEFAULT_QUEUE)
                raise
    
    join_queue(cset, name=queue_name, exchange_type='direct')

    panel.logger.info("Started consuming from %s", queue_name)

    return {
        "status": "ok",
        "build_id": build_id,
        "stdout": script_result[0],
        "stderr": script_result[1],
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
    
    script_result = ('', '')
    
    if workspace:
        work_path = os.path.join(conf.ROOT, 'workspaces', workspace)
    
        # Create a temporary bash script in workspace, setup env, and
        # execute
        try:
            script_result = execute_bash(work_path, 'teardown.sh', script, BUILD_ID=build_id)
        except:
            # If our teardown fails we need to ensure we rejoin the queue
            join_queue(cset, name=conf.DEFAULT_QUEUE)
            raise
    
    join_queue(cset, name=conf.DEFAULT_QUEUE)

    panel.logger.info("Rejoined default queue")

    return {
        "status": "ok",
        "build_id": build_id,
        "stdout": script_result[0],
        "stderr": script_result[1],
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