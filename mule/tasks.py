from celery import task

@task
def run_test(host_id, test_case_path):
    print host_id, test_case_path
