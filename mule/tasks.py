from celery.task import task
from celery.worker.control import Panel

import subprocess
import shlex

@Panel.register
def mule_provision(panel, build_id):
    """
    This task has two jobs:

    1. Leaves the default Mule queue, and joins a new build-specific queue.

    2. Ensure that we're bootstrapped for this build.

       This includes:
         - Doing a git fetch
         - Setting up a virtualenv
         - Building our DB
    """
    queue_name = 'mule-%s' % build_id

    cset = panel.consumer.task_consumer
    
    if 'default' not in [q.name for q in cset.queues]:
        return {"fail": "worker is already in use"}
    
    cset.cancel_by_queue('default')
    
    declaration = dict(queue=queue_name, exchange_type='direct')
    queue = cset.add_consumer_from_dict(**declaration)
    # XXX: There's currently a bug in Celery 2.2.5 which doesn't declare the queue automatically
    channel = cset.connection.channel()
    try:
        queue(channel).declare()
    finally:
        channel.close()
    cset.consume()
    panel.logger.info("Started consuming from %r" % (declaration, ))

    return {
        "status": "ok",
        "build_id": build_id,
    }

@Panel.register
def mule_teardown(panel, build_id):
    """
    This task has two jobs:
    
    1. Run any bootstrap teardown

    2. Leaves the build-specific queue, and joins the default Mule queue.
    """
    queue = 'mule-%s' % build_id

    cset = panel.consumer.task_consumer

    cset.cancel_by_queue(queue)
    
    cset.add_consumer_from_dict(queue='default')
    # XXX: There's currently a bug in Celery 2.2.5 which doesn't declare the queue automatically
    channel = cset.connection.channel()
    try:
        queue(channel).declare()
    finally:
        channel.close()
    cset.consume()

    panel.logger.info("Rejoined default queue")

    return {
        "status": "ok",
        "build_id": build_id,
    }


@task(ignore_result=False)
def run_test(build_id, runner, job):
    """
    Spawns a test runner and reports the result.
    """
    logger = run_test.get_logger()
    cmd = runner.encode('utf-8')
    logger.info('Job received: %s', cmd)
    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={'TEST': job})
    (stdout, stderr) = proc.communicate()
    proc.wait()
    retcode = proc.returncode

    return {
        "stdout": stdout,
        "stderr": stderr,
        "retcode": retcode,
        "build_id": build_id,
        "job": job,
    }

    logger.info('Finished!')
