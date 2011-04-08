from celery.task import task

import subprocess
import shlex

class TestRunnerException(Exception):
    pass

@task(ignore_result=False)
def run_test(build_id, runner, job):
    """
    This task has two jobs:
    
    1. Ensure that we're already bootstrapped for this build.

       This includes:
         - Doing a git fetch
         - Setting up a virtualenv
         - Building our DB
    
    2. Run the given job (TestCase).
    """
    logger = run_test.get_logger()
    cmd = runner.replace('#TEST#', job).encode('utf-8')
    logger.info('Job received: %s', cmd)
    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, stderr) = proc.communicate()
    proc.wait()
    retcode = proc.returncode
    if retcode != 0:
        raise TestRunnerException(stderr)

    logger.info('Finished!')
    return stdout.strip()