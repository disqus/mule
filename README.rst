Mule is a generic framework for distributing tests using Celery. It also provides many tools
such as xunit, multi-processing (without Celery), and general optimizations for unittest/2.

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

With that in mind, continue to the install guide :)

(Please read the TODO to get an idea of what direction the project is heading)

Install
=======

You'll need to be running Django 1.2 or newer currently.

If you are using Redis you will need to install a patched version of Kombu after other dependancies. The repo is available
on GitHub and solves a problem with dynamic queue creation and consumption in Redis. https://github.com/disqus/kombu

Add Mule to your ``INSTALLED_APPS``::

    INSTALLED_APPS = (
        # placement doesnt matter
        'mule.contrib.django',
    )

Run ``python manage.py mule`` in place of the ``test`` command.

Mule provides the following features on top of the default Django test runner:

- XUnit integration (with --xunit, --xunit-output).

- Distributed testing with Celery (with --distributed), and single box multi-processing (with --multiprocess).

- Inclusion and exclusion support by TestCase class (with --include and --exclude).

- The ability to specify the full paths to module and tests to run (rather than just shorthand app.TestName).

- Specification of the database name to use at run-time (with --db-prefix)

Distributed Flow
================

1. You run ./manage.py mule --distributed

2. Mule collects all of the jobs, and dynamically adds a new queue called "mule-<build_id>"

3. Mule broadcasts "provision" tasks to <max_workers> in "default" queue.

4. When a worker executes a provision task, it leaves the "default" queue, and joins "mule-<build_id>".
   Within this same task, it bootstraps itself, based on the users defined method (e.g. git fetch, checkout, and venv setup)

5. Mule fires off a <num_test_cases> "run_test" tasks to "mule-<build_id>" queue.

6. When all processes have returned (or timed out), mule broadcasts the teardown task.
   This task does database cleanup and other things (configurable), and also leaves "mule-<build_id>" and rejoins "default".

TODO
====

General
-------

- Build a JSONTestRunner

- run_test would be awesome if it expected a JSON result from the test runner (or at least our runners gave it that)
  we could then store additional data like "I did this as part of the build" including timing/profiling data
  
  otherwise we have to hack up xunit :(

- The Django test suite runner should be mostly a mixin class so that we can reuse the core of it as a generic unittest/2
  suite runner.
  
Django Integration
------------------

- Text runner output doesnt support verbosity levels correctly (for non-errors/failures):

  (Should it?)
  ::

    if self.showAll:
        self.stream.writeln('%s (%.3fs)' % \
            (verbose_str, test_info.get_elapsed_time()))

- The Disqus selenium test should have been reported as skipped, but wasn't. It caused metric tons of timeouts and consumed way too
  much cpu time.
 
- Add proper KeyboardInterrupt support (for non-failfast) as exists in Django proper.

- Mule should import app.mule for registering hooks

- Mule should support a post_setup, and pre_teardown method so that things like REDIS_DB can be changed based on runner.