from celery import task

import subprocess
import shlex

@task
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
    print runner, job
    proc = subprocess.Popen(shlex.split(runner.replace('#TEST#', job)), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, stderr) = proc.communicate()
    proc.wait()
