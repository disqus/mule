from __future__ import absolute_import

from django.conf import settings
# from django.test.utils import get_runner
from mule.contrib.django.suite import DjangoTestSuiteRunner
from mule.utils.conf import configure
from optparse import make_option

if 'south' in settings.INSTALLED_APPS:
    from south.management.commands.test import Command as TestCommand
    from south.management.commands import patch_for_test_db_setup
else:
    from django.management.commands.test import Command as TestCommand

import sys

TestRunner = DjangoTestSuiteRunner
# TestRunner = make_test_runner(get_runner(settings))

class Command(TestCommand):
    option_list = TestCommand.option_list + (
        make_option('--auto-bootstrap', dest='auto_bootstrap', action='store_true',
                    help='Bootstrap a new database automatically.'),
        make_option('--id', dest='build_id', help='Identifies this build within a distributed model.',
                    default='default'),
        make_option('--db-prefix', type='string', dest='db_prefix', default='test',
                    help='Prefix to use for test databases. Default is ``test``.'),
        make_option('--distributed', dest='distributed', action='store_true',
                    help='Fire test jobs off to Celery queue and collect results.'),
        make_option('--multiprocess', dest='multiprocess', action='store_true',
                    help='Spawns multiple processes (controlled within threads) to test concurrently.'),
        make_option('--max-workers', dest='max_workers', type='int', metavar="NUM",
                    help='Number of workers to consume. With multi-process this is the number of processes to spawn. With distributed this is the number of Celeryd servers to consume.'),
        make_option('--worker', dest='worker', action='store_true',
                    help='Identifies this runner as a worker of a distributed test runner.'),
        make_option('--xunit', dest='xunit', action='store_true',
                    help='Outputs results in XUnit format.'),
        make_option('--xunit-output', dest='xunit_output', default="./xunit/", metavar="PATH",
                    help='Specifies the output directory for XUnit results.'),
        make_option('--include', dest='include', default='', metavar="CLASSNAMES",
                    help='Specifies inclusion cases (TestCaseClassName) for the job detection.'),
        make_option('--exclude', dest='exclude', default='', metavar="CLASSNAMES",
                    help='Specifies exclusion cases (TestCaseClassName) for the job detection.'),
    )
    
    def handle(self, *test_labels, **options):
        configure(**getattr(settings, 'MULE_CONFIG', {}))
        
        settings.TEST = True
        settings.DEBUG = False

        if 'south' in settings.INSTALLED_APPS:
            patch_for_test_db_setup()

        if hasattr(TestRunner, 'func_name'):
            # Pre 1.2 test runners were just functions,
            # and did not support the 'failfast' option.
            import warnings
            warnings.warn(
                'Function-based test runners are deprecated. Test runners should be classes with a run_tests() method.',
                PendingDeprecationWarning
            )
            result = TestRunner(test_labels, **options)
        else:
            test_runner = TestRunner(**options)
            result = test_runner.run_tests(test_labels)

        if result:
            sys.exit(bool(result))