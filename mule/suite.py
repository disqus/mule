# TODO: TransactionTestCase should be ordered last, and they need to completely tear down
#       all data in all tables and re-run syncdb (initial fixtures) each time.
#       This same (bad) behavior needs to happen on every TestCase if not connections_support_transactions()

from __future__ import absolute_import

from cStringIO import StringIO
from mule.contextmanager import get_context_managers
from mule.base import Mule, MultiProcessMule, FailFastInterrupt
from mule.loader import reorder_suite
from mule.runners import make_test_runner
from mule.runners.xml import XMLTestRunner
from mule.runners.text import TextTestRunner, _TextTestResult
from mule.utils import import_string
from xml.dom.minidom import parseString

import logging
import os, os.path
import re
import sys
import time
import uuid
import unittest
import unittest2

defaultTestLoader = unittest2.defaultTestLoader

class MuleTestLoader(object):
    def __init__(self, build_id='default', distributed=False, worker=False,
                 multiprocess=False, xunit=False, xunit_output='./xunit/',
                 include='', exclude='', max_workers=None, start_dir=None,
                 loader=defaultTestLoader, base_cmd='unit2 $TEST', 
                 workspace=None, log_level=logging.DEBUG, *args, **kwargs):

        assert not (distributed and worker and multiprocess), "You cannot combine --distributed, --worker, and --multiprocess"
        
        self.build_id = build_id
        
        self.distributed = distributed
        self.worker = worker
        self.multiprocess = multiprocess

        self.xunit = xunit
        self.xunit_output = os.path.realpath(xunit_output)
        if include:
            self.include_testcases = [import_string(i) for i in include.split(',')]
        else:
            self.include_testcases = []
        if exclude:
            self.exclude_testcases = [import_string(i) for i in exclude.split(',')]
        else:
            self.exclude_testcases = []
        self.max_workers = max_workers
        self.start_dir = start_dir
        self.loader = loader
        self.logger = logging.getLogger('mule')
        self.logger.setLevel(log_level)
        
        self.base_cmd = base_cmd
        self.workspace = workspace
    
    def run_suite(self, suite, output=None, run_callback=None):
        kwargs = {
            'verbosity': self.verbosity,
            'failfast': self.failfast,
        }
        if self.worker or self.xunit:
            cls = XMLTestRunner
            kwargs['output'] = output
        else:
            cls = TextTestRunner

        if self.worker:
            # We dont output anything
            kwargs['verbosity'] = 0
        
        cls = make_test_runner(cls)
    
        result = cls(run_callback=run_callback, **kwargs).run(suite)

        return result

    def build_suite(self, test_labels, extra_tests=None, **kwargs):
        suite = unittest2.TestSuite()

        if test_labels:
            for label in test_labels:
                self.loader.loadTestsFromNames(test_labels)
        else:
            self.loader.discover(self.start_dir)

        if extra_tests:
            for test in extra_tests:
                suite.addTest(test)
        
        new_suite = unittest2.TestSuite()
        
        for test in reorder_suite(suite, (unittest.TestCase,)):
            # XXX: Doctests (the way we do it currently) do not work
            if self.include_testcases and not any(isinstance(test, c) for c in self.include_testcases):
                continue
            if self.exclude_testcases and any(isinstance(test, c) for c in self.exclude_testcases):
                continue
            new_suite.addTest(test)

        return reorder_suite(new_suite, (unittest2.TestCase,))

    def run_distributed_tests(self, test_labels, extra_tests=None, in_process=False, **kwargs):
        if in_process:
            cls = MultiProcessMule
        else:
            cls = Mule
        build_id = uuid.uuid4().hex
        mule = cls(build_id=build_id, max_workers=self.max_workers, workspace=self.workspace)
        result = mule.process(test_labels, runner=self.base_cmd,
                              callback=self.report_result)
        # result should now be some parseable text
        return result
    
    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        # We need to swap stdout/stderr so that the task only captures what is needed,
        # and everything else goes to our logs
        if self.worker:
            stdout = StringIO()
            sys_stdout = sys.stdout
            sys.stdout = stdout
            output = sys_stdout
        else:
            if self.xunit:
                output = self.xunit_output
            else:
                output = sys.stdout
        
        cms = list()
        for cls in get_context_managers():
            self.logger.info('Entering context for [%r]', cls)
            start = time.time()
            cm = cls(build_id=self.build_id, suite=self)
            cm.__enter__()
            stop = time.time()
            self.logger.info('Context manager opened in %.3fs', stop - start)
            cms.append(cm)

        try:
            suite = self.build_suite(test_labels, extra_tests)

            start = time.time()

            if self.distributed or self.multiprocess:
                # we can only test whole TestCase's currently
                jobs = set(t.__class__ for t in suite._tests)
                result = self.run_distributed_tests(jobs, extra_tests=None, in_process=self.multiprocess, **kwargs)
            else:
                result = self.run_suite(suite, output=output)

            stop = time.time()

            result = self.suite_result(suite, result, stop-start)

        finally:
            if self.worker:
                sys.stdout = sys_stdout
            
            for cm in reversed(cms):
                self.logger.info('Exiting context for [%r]', cls)
                start = time.time()
                cm.__exit__(None, None, None)
                stop = time.time()
                self.logger.info('Context manager closed in %.3fs', stop - start)
                
        
        return result

    def report_result(self, result):
        if result['stdout']:
            match = re.search(r'errors="(\d+)".*failures="(\d+)".*skips="(\d+)".*tests="(\d+)"', result['stdout'])
            if match:
                errors = int(match.group(1))
                failures = int(match.group(2))
                skips = int(match.group(3))
                tests = int(match.group(4))
        else:
            errors = 1
            tests = 1
            failures = 0
            skips = 0
        
        if self.failfast and (errors or failures):
            raise FailFastInterrupt(result)
    
    def suite_result(self, suite, result, total_time, **kwargs):
        if self.distributed or self.multiprocess:
            # Bootstrap our xunit output path
            if self.xunit and not os.path.exists(self.xunit_output):
                os.makedirs(self.xunit_output)
            
            failures, errors = 0, 0
            skips, tests = 0, 0

            had_res = False
            res_type = None
            
            for r in result:
                if isinstance(r, dict):
                    # XXX: stdout (which is our result) is in XML, which sucks life is easier with regexp
                    match = re.search(r'errors="(\d+)".*failures="(\d+)".*skips="(\d+)".*tests="(\d+)"', r['stdout'])
                    if match:
                        errors += int(match.group(1))
                        failures += int(match.group(2))
                        skips += int(match.group(3))
                        tests += int(match.group(4))
                else:
                    # Handles cases when our runners dont return correct output
                    had_res = True
                    res_type = 'error'
                    sys.stdout.write(_TextTestResult.separator1 + '\n')
                    sys.stdout.write('EXCEPTION: unknown exception\n')
                    if r:
                        sys.stdout.write(_TextTestResult.separator1 + '\n')
                        sys.stdout.write(str(r).strip() + '\n')
                    errors += 1
                    tests += 1
                    continue
                    
                if self.xunit:
                    # Since we already get xunit results back, let's just write them to disk
                    if r['stdout']:
                        fp = open(os.path.join(self.xunit_output, r['job'] + '.xml'), 'w')
                        try:
                            fp.write(r['stdout'])
                        finally:
                            fp.close()
                    elif r['stderr']:
                        sys.stderr.write(r['stderr'])
                        # Need to track this for the builds
                        errors += 1
                        tests += 1
                elif r['stdout']:
                    # HACK: Ideally we would let our default text runner represent us here, but that'd require
                    #       reconstructing the original objects which is even more of a hack
                    try:
                        xml = parseString(r['stdout'])
                    except Exception, e:
                        had_res = True
                        res_type = 'error'
                        sys.stdout.write(_TextTestResult.separator1 + '\n')
                        sys.stdout.write('EXCEPTION: %s (%s)\n' % (e, r['job']))
                        if r['stdout']:
                            sys.stdout.write(_TextTestResult.separator1 + '\n')
                            sys.stdout.write(r['stdout'].strip() + '\n')
                        if r['stderr']:
                            sys.stdout.write(_TextTestResult.separator1 + '\n')
                            sys.stdout.write(r['stdout'].strip() + '\n')
                        errors += 1
                        tests += 1
                        continue

                    for xml_test in xml.getElementsByTagName('testcase'):
                        for xml_test_res in xml_test.childNodes:
                            if xml_test_res.nodeName not in ('failure', 'skip', 'error'):
                                continue
                            had_res = True
                            res_type = xml_test.getAttribute('name')
                            desc = '%s (%s)' % (xml_test.getAttribute('name'), xml_test.getAttribute('classname'))
                            sys.stdout.write(_TextTestResult.separator1 + '\n')
                            sys.stdout.write('%s [%.3fs]: %s\n' % \
                                (xml_test_res.nodeName.upper(), float(xml_test.getAttribute('time') or '0.0'), desc))
                            sys.stdout.write('(Job was %s)\n' % r['job'])
                            error_msg = (''.join(c.wholeText for c in xml_test_res.childNodes if c.nodeType == c.CDATA_SECTION_NODE)).strip()
                            if error_msg:
                                sys.stdout.write(_TextTestResult.separator2 + '\n')
                                sys.stdout.write('%s\n' % error_msg)

                    if res_type in ('failure', 'error'):
                        syserr = (''.join(c.wholeText for c in xml.getElementsByTagName('system-err')[0].childNodes if c.nodeType == c.CDATA_SECTION_NODE)).strip()
                        if syserr:
                            sys.stdout.write(_TextTestResult.separator2 + '\n')
                            sys.stdout.write('%s\n' % r['stderr'].strip())
                        # if r['stderr']:
                        #     sys.stdout.write(_TextTestResult.separator2 + '\n')
                        #     sys.stdout.write('%s\n' % r['stderr'].strip())
                elif r['stderr']:
                    had_res = True
                    sys.stdout.write(_TextTestResult.separator1 + '\n')
                    sys.stdout.write('EXCEPTION: %s\n' % r['job'])
                    sys.stdout.write(_TextTestResult.separator1 + '\n')
                    sys.stdout.write(r['stderr'].strip() + '\n')
                    errors += 1
                    tests += 1

            if had_res:
                sys.stdout.write(_TextTestResult.separator2 + '\n')

            run = tests - skips
            sys.stdout.write("\nRan %d test%s in %.3fs\n\n" % (run, run != 1 and "s" or "", total_time))
            
            if errors or failures:
                sys.stdout.write("FAILED (")
                if failures:
                    sys.stdout.write("failures=%d" % failures)
                if errors:
                    if failures:
                        sys.stdout.write(", ")
                    sys.stdout.write("errors=%d" % errors)
                if skips:
                    if failures or errors:
                        sys.stdout.write(", ")
                    sys.stdout.write("skipped=%d" % skips)
                sys.stdout.write(")")
            else:
                sys.stdout.write("OK")
                if skips:
                    sys.stdout.write(" (skipped=%d)" % skips)

            sys.stdout.write('\n\n')
            return failures + errors
        return super(MuleTestLoader, self).suite_result(suite, result, **kwargs)