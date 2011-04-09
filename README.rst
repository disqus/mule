Basic flow (assuming Django):

1. You run ./manage.py mule --distributed

2. Mule collects all of the jobs, and dynamically adds a new queue called "mule-<build_id>"

3. Mule fires off <max_workers> "provision" tasks to "default" queue.

4. When a worker executes a provision task, it leaves the "default" queue, and joins "mule-<build_id>".
   Within this same task, it bootstraps itself, based on the users defined method (e.g. git fetch, checkout, and venv setup)

5. Mule fires off a <num_test_cases> "run_test" tasks to "mule-<build_id>" queue.

6. When all processes have returned (or timed out), mule fires <max_workers> "teardown" tasks.
   This task does database cleanup and other things (configurable), and also leaves "mule-<build_id>" and rejoins "default".
