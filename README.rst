Mule is a generic framework for distributing tests using Celery. It also provides many tools
such as xunit, multi-processing (without Celery), and general optimizations for unittest/2.

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

MULE IS IN DEVELOPMENT AND UNSTABLE

With that in mind, continue to the install guide :)

Install
=======

You'll need to be running Django 1.2 or newer currently.

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

3. Mule fires off <max_workers> "provision" tasks to "default" queue.

4. When a worker executes a provision task, it leaves the "default" queue, and joins "mule-<build_id>".
   Within this same task, it bootstraps itself, based on the users defined method (e.g. git fetch, checkout, and venv setup)

5. Mule fires off a <num_test_cases> "run_test" tasks to "mule-<build_id>" queue.

6. When all processes have returned (or timed out), mule fires <max_workers> "teardown" tasks.
   This task does database cleanup and other things (configurable), and also leaves "mule-<build_id>" and rejoins "default".
