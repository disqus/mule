# -*- coding: utf-8 -*-

from __future__ import absolute_import

"""unittest-xml-reporting is a PyUnit-based TestRunner that can export test
results to XML files that can be consumed by a wide range of tools, such as
build systems, IDEs and Continuous Integration servers.

This module provides the XMLTestRunner class, which is heavily based on the
default TextTestRunner. This makes the XMLTestRunner very simple to use.

The script below, adapted from the unittest documentation, shows how to use
XMLTestRunner in a very simple way. In fact, the only difference between this
script and the original one is the last line:

import random
import unittest
import xmlrunner

class TestSequenceFunctions(unittest.TestCase):
    def setUp(self):
        self.seq = range(10)

    def test_shuffle(self):
        # make sure the shuffled sequence does not lose any elements
        random.shuffle(self.seq)
        self.seq.sort()
        self.assertEqual(self.seq, range(10))

    def test_choice(self):
        element = random.choice(self.seq)
        self.assert_(element in self.seq)

    def test_sample(self):
        self.assertRaises(ValueError, random.sample, self.seq, 20)
        for element in random.sample(self.seq, 5):
            self.assert_(element in self.seq)

if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'))
"""

import os

from mule.runners.text import _TextTestResult, TextTestRunner, _TestInfo

class _XMLTestResult(_TextTestResult):
    "A test result class that can express test results in a XML report."

    def _get_info_by_testcase(self):
        """This method organizes test results by TestCase module. This
        information is used during the report generation, where a XML report
        will be generated for each TestCase.
        """
        tests_by_testcase = {}
        
        for tests in (self.successes, self.failures, self.errors, self.skipped):
            for test_info in tests:
                testcase = type(test_info.test_method)
                
                # Ignore module name if it is '__main__'
                module = testcase.__module__ + '.'
                if module == '__main__.':
                    module = ''
                testcase_name = module + testcase.__name__
                
                if not tests_by_testcase.has_key(testcase_name):
                    tests_by_testcase[testcase_name] = []
                tests_by_testcase[testcase_name].append(test_info)
        
        return tests_by_testcase
    
    @classmethod
    def _report_testsuite(cls, suite_name, tests, xml_document):
        "Appends the testsuite section to the XML document."
        testsuite = xml_document.createElement('testsuite')
        xml_document.appendChild(testsuite)
        
        testsuite.setAttribute('name', suite_name)
        testsuite.setAttribute('tests', str(len(tests)))
        
        testsuite.setAttribute('time', '%.3f' % \
            sum(map(lambda e: e.get_elapsed_time(), tests)))
        
        failures = filter(lambda e: e.outcome==_TestInfo.FAILURE, tests)
        testsuite.setAttribute('failures', str(len(failures)))
        
        errors = filter(lambda e: e.outcome==_TestInfo.ERROR, tests)
        testsuite.setAttribute('errors', str(len(errors)))

        skipped = filter(lambda e: e.outcome==_TestInfo.SKIPPED, tests)
        testsuite.setAttribute('skips', str(len(skipped)))

        
        return testsuite
    
    @classmethod
    def _report_testcase(cls, suite_name, test_result, xml_testsuite, xml_document):
        "Appends a testcase section to the XML document."
        testcase = xml_document.createElement('testcase')
        xml_testsuite.appendChild(testcase)
        
        testcase.setAttribute('classname', suite_name)
        testcase.setAttribute('name', test_result.test_method._testMethodName)
        testcase.setAttribute('time', '%.3f' % test_result.get_elapsed_time())
        
        if (test_result.outcome != _TestInfo.SUCCESS):
            elem_name = ('failure', 'error', 'skip')[test_result.outcome-1]
            failure = xml_document.createElement(elem_name)
            testcase.appendChild(failure)
            
            failure.setAttribute('type', test_result.err[0].__name__)
            failure.setAttribute('message', str(test_result.err[1]))
            
            error_info = test_result.get_error_info()
            failureText = xml_document.createCDATASection(error_info)
            failure.appendChild(failureText)
    
    @classmethod
    def _report_output(cls, suite, tests, test_runner, xml_testsuite, xml_document):
        "Appends the system-out and system-err sections to the XML document."
        systemout = xml_document.createElement('system-out')
        xml_testsuite.appendChild(systemout)
        
        stdout = '\n'.join(filter(None, (t.test_method.stdout.getvalue() for t in tests))).strip()
        systemout_text = xml_document.createCDATASection(stdout)
        systemout.appendChild(systemout_text)
        
        systemerr = xml_document.createElement('system-err')
        xml_testsuite.appendChild(systemerr)
        
        stderr = '\n'.join(filter(None, (t.test_method.stderr.getvalue() for t in tests))).strip()
        systemerr_text = xml_document.createCDATASection(stderr)
        systemerr.appendChild(systemerr_text)
    
    def generate_reports(self, test_runner):
        "Generates the XML reports to a given XMLTestRunner object."
        from xml.dom.minidom import Document
        all_results = self._get_info_by_testcase()
        
        if type(test_runner.output) == str and not \
            os.path.exists(test_runner.output):
            os.makedirs(test_runner.output)
        
        for suite, tests in all_results.items():
            doc = Document()
            
            # Build the XML file
            testsuite = _XMLTestResult._report_testsuite(suite, tests, doc)
            for test in tests:
                _XMLTestResult._report_testcase(suite, test, testsuite, doc)
            _XMLTestResult._report_output(suite, tests, test_runner, testsuite, doc)
            xml_content = doc.toprettyxml(indent='\t')
            
            if type(test_runner.output) is str:
                report_file = open(os.path.join(test_runner.output, '%s.xml' % (suite,)), 'w')
                try:
                    report_file.write(xml_content)
                finally:
                    report_file.close()
            else:
                # Assume that test_runner.output is a stream
                test_runner.output.write(xml_content)

class XMLTestRunner(TextTestRunner):
    """A test runner class that outputs the results in JUnit like XML files."""
    def __init__(self, output='xunit', **kwargs):
        super(XMLTestRunner, self).__init__(**kwargs)
        self.output = output

    def _makeResult(self):
        """Create the TestResult object which will be used to store
        information about the executed tests.
        """
        return _XMLTestResult(self.stream, self.descriptions, \
            self.verbosity, self.elapsed_times, self.pdb)

    def run(self, test):
        "Run the given test case or test suite."
        result = super(XMLTestRunner, self).run(test)

        self.stream.writeln('Generating XML reports...')
        result.generate_reports(self)
        return result