# -*- coding: utf-8 -*-

from __future__ import absolute_import

import sys
import time
import traceback

from unittest import TestResult, _TextTestResult, TextTestRunner
from cStringIO import StringIO

class Streamer(object):
    def __init__(self, fp, *args, **kwargs):
        self.fp = fp
        self.stringio = StringIO()
    
    def write(self, *args, **kwargs):
        self.fp.write(*args, **kwargs)
        self.stringio.write(*args, **kwargs)
    
    def getvalue(self, *args, **kwargs):
        return self.stringio.getvalue(*args, **kwargs)
    
    def read(self, *args, **kwargs):
        return self.stringio.read(*args, **kwargs)

    def flush(self):
        return self.stringio.flush()

class _TestInfo(object):
    """This class is used to keep useful information about the execution of a
    test method.
    """
    
    # Possible test outcomes
    (SUCCESS, FAILURE, ERROR, SKIPPED) = range(4)
    
    def __init__(self, test_result, test_method, outcome=SUCCESS, err=None):
        "Create a new instance of _TestInfo."
        self.test_result = test_result
        self.test_method = test_method
        self.outcome = outcome
        self.err = err
        self.stdout = StringIO()
        self.stderr = StringIO()
    
    def get_elapsed_time(self):
        """Return the time that shows how long the test method took to
        execute.
        """
        if getattr(self.test_result, 'stop_time', None):
            return self.test_result.stop_time - self.test_result.start_time
        return 0
    
    def get_description(self):
        "Return a text representation of the test method."
        return self.test_result.getDescription(self.test_method)
    
    def get_error_info(self):
        """Return a text representation of an exception thrown by a test
        method.
        """
        if not self.err:
            return ''
        return self.test_result._exc_info_to_string(self.err, \
            self.test_method)


class _TextTestResult(_TextTestResult):
    def __init__(self, stream=sys.stderr, descriptions=1, verbosity=1, \
        elapsed_times=True, pdb=False):
        super(_TextTestResult, self).__init__(stream, descriptions, verbosity)
        self.successes = []
        self.skipped = []
        self.callback = None
        self.elapsed_times = elapsed_times
        self.pdb = pdb
    
    def _prepare_callback(self, test_info, target_list, verbose_str,
        short_str):
        """Append a _TestInfo to the given target list and sets a callback
        method to be called by stopTest method.
        """
        target_list.append(test_info)

        def callback():
            """This callback prints the test method outcome to the stream,
            as well as the elapsed time.
            """
            # Ignore the elapsed times for a more reliable unit testing
            if not self.elapsed_times:
                self.start_time = self.stop_time = 0
            
            if self.showAll:
                self.stream.writeln('%s (%.3fs)' % \
                    (verbose_str, test_info.get_elapsed_time()))
            elif self.dots:
                self.stream.write(short_str)
        self.callback = callback
    
    def startTest(self, test):
        "Called before execute each test method."
        self._patch_standard_output(test)
        self.start_time = time.time()
        TestResult.startTest(self, test)

        if self.showAll:
            self.stream.write('  ' + self.getDescription(test))
            self.stream.write(" ... ")
    
    def stopTest(self, test):
        "Called after execute each test method."
        super(_TextTestResult, self).stopTest(test)
        self.stop_time = time.time()
        
        if self.callback and callable(self.callback):
            self.callback()
            self.callback = None
        self._restore_standard_output(test)

    def addSuccess(self, test):
        "Called when a test executes successfully."
        self._prepare_callback(_TestInfo(self, test), \
            self.successes, 'OK', '.')
    
    def addFailure(self, test, err):
        "Called when a test method fails."
        self._prepare_callback(_TestInfo(self, test, _TestInfo.FAILURE, err), \
            self.failures, 'FAIL', 'F')
    
    def addError(self, test, err):
        "Called when a test method raises an error."
        if self.pdb:
            import pdb; pdb.set_trace()
        tracebacks = traceback.extract_tb(err[2])
        if tracebacks[-1][-1] and tracebacks[-1][-1].startswith('raise SkippedTest'):
            self._prepare_callback(_TestInfo(self, test, _TestInfo.SKIPPED, err), \
                self.skipped, 'SKIP', 'S')
        else:
            self._prepare_callback(_TestInfo(self, test, _TestInfo.ERROR, err), \
                self.errors, 'ERROR', 'E')

    def printErrorList(self, flavour, errors):
        "Write some information about the FAIL or ERROR to the stream."
        for test_info in errors:
            self.stream.writeln(self.separator1)
            self.stream.writeln('%s [%.3fs]: %s' % \
                (flavour, test_info.get_elapsed_time(), \
                test_info.get_description()))
            self.stream.writeln(self.separator2)
            self.stream.writeln('%s' % test_info.get_error_info())

    def _patch_standard_output(self, test):
        """Replace the stdout and stderr streams with string-based streams
        in order to capture the tests' output.
        """
        test.stdout = Streamer(sys.stdout)
        test.stderr = Streamer(sys.stderr)
        
        (self.old_stdout, self.old_stderr) = (sys.stdout, sys.stderr)
        (sys.stdout, sys.stderr) = (test.stdout, test.stderr)
    
    def _restore_standard_output(self, test):
        "Restore the stdout and stderr streams."
        
        (sys.stdout, sys.stderr) = (self.old_stdout, self.old_stderr)

class TextTestRunner(TextTestRunner):
    def __init__(self, elapsed_times=True, pdb=False, **kwargs):
        super(TextTestRunner, self).__init__(**kwargs)
        self.elapsed_times = elapsed_times
        self.pdb = pdb
    
    def _makeResult(self):
        """Create the TestResult object which will be used to store
        information about the executed tests.
        """
        return _TextTestResult(self.stream, self.descriptions, \
            self.verbosity, self.elapsed_times, self.pdb)
    
    def run(self, test):
        "Run the given test case or test suite."
        
        # Prepare the test execution
        result = self._makeResult()
        
        # Print a nice header
        self.stream.writeln()
        self.stream.writeln('Running tests...')
        self.stream.writeln(result.separator2)
        
        # Execute tests
        start_time = time.time()
        test(result)
        stop_time = time.time()
        time_taken = stop_time - start_time
        
        # Print results
        result.printErrors()
        self.stream.writeln(result.separator2)
        run = result.testsRun
        self.stream.writeln("Ran %d test%s in %.3fs" %
            (run, run != 1 and "s" or "", time_taken))
        self.stream.writeln()
        
        # Error traces
        if not result.wasSuccessful():
            self.stream.write("FAILED (")
            failed, errored, skipped = (len(result.failures), len(result.errors), len(result.skipped))
            if failed:
                self.stream.write("failures=%d" % failed)
            if errored:
                if failed:
                    self.stream.write(", ")
                self.stream.write("errors=%d" % errored)
            if skipped:
                if failed or errored:
                    self.stream.write(", ")
                self.stream.write("skipped=%d" % skipped)
            self.stream.writeln(")")
        else:
            self.stream.writeln("OK")
        
        # Generate reports
        self.stream.writeln()
        
        return result
