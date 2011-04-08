from __future__ import absolute_import

from django.conf import settings
# from django.test.utils import get_runner
from mule.suites.django import DjangoTestSuiteRunner

if 'south' in settings.INSTALLED_APPS:
    from south.management.commands.test import Command as TestCommand
    from south.management.commands import patch_for_test_db_setup
else:
    from django.management.commands.test import Command as TestCommand

import sys

TestRunner = DjangoTestSuiteRunner
# TestRunner = make_test_runner(get_runner(settings))

class Command(TestCommand):
    option_list = TestCommand.option_list + tuple(getattr(TestRunner, 'options', []))
    
    def handle(self, *test_labels, **options):
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
            failures = TestRunner(test_labels, **options)
        else:
            test_runner = TestRunner(**options)
            failures = test_runner.run_tests(test_labels)

        if failures:
            sys.exit(bool(failures))