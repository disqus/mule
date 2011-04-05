#!/usr/bin/env python
from fnmatch import fnmatch
from mule.daemon import Daemon
from twisted.python import usage
import os, os.path
import re
import sys
import unittest
import zmq

class Server(Daemon):
    def run(self, host, basedir, pattern='test*.py'):
        host = host
        basedir = basedir
        pattern = pattern

        jobs = list(self.discover_tests(basedir, pattern))

        print "Found %d test cases" % len(jobs)

        context = zmq.Context(1)

        server = context.socket(zmq.REP)
        server.bind('tcp://%s' % host)

        while jobs:
            request = server.recv()

            if request == 'GET':
                job = jobs.pop()

                server.send('%s.%s' % (job.__module__, job.__name__))
            else:
                server.send('ERR Unknown Command')

    def _match_path(self, path, full_path, pattern):
        # override this method to use alternative matching strategy
        return fnmatch(path, pattern)

    def _get_name_from_path(self, path, top_level_dir):
        path = os.path.splitext(os.path.normpath(path))[0]

        _relpath = os.path.relpath(path, top_level_dir)
        assert not os.path.isabs(_relpath), "Path must be within the project"
        assert not _relpath.startswith('..'), "Path must be within the project"

        name = _relpath.replace(os.path.sep, '.')
        return name

    def _get_module_from_name(self, name):
        __import__(name)
        return sys.modules[name]

    def load_tests_from_module(self, module, use_load_tests=True):
        """Return a suite of all tests cases contained in the given module"""
        tests = []
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
                tests.append(obj)

        return tests

    def discover_tests(self, start_dir, pattern='test*.py', top_level_dir=None):
        """
        Used by discovery. Yields test suites it loads.

        (Source: unittest2)
        """

        if not top_level_dir:
            top_level_dir = os.path.abspath(os.path.join(start_dir, os.pardir))
            sys.path.insert(0, top_level_dir)

        VALID_MODULE_NAME = re.compile(r'[_a-z]\w*\.py$', re.IGNORECASE)

        paths = os.listdir(start_dir)

        for path in paths:
            full_path = os.path.join(start_dir, path)
            if os.path.isfile(full_path):
                if not VALID_MODULE_NAME.match(path):
                    # valid Python identifiers only
                    continue
                if not self._match_path(path, full_path, pattern):
                    continue
                # if the test file matches, load it
                name = self._get_name_from_path(full_path, top_level_dir)
                try:
                    module = self._get_module_from_name(name)
                except:
                    # TODO: should this be handled more gracefully?
                    # yield _make_failed_import_test(name, self.suiteClass)
                    raise
                else:
                    mod_file = os.path.abspath(getattr(module, '__file__', full_path))
                    realpath = os.path.splitext(mod_file)[0]
                    fullpath_noext = os.path.splitext(full_path)[0]
                    if realpath.lower() != fullpath_noext.lower():
                        module_dir = os.path.dirname(realpath)
                        mod_name = os.path.splitext(os.path.basename(full_path))[0]
                        expected_dir = os.path.dirname(full_path)
                        msg = ("%r module incorrectly imported from %r. Expected %r. "
                               "Is this module globally installed?")
                        raise ImportError(msg % (mod_name, module_dir, expected_dir))
                    for test in self.load_tests_from_module(module):
                        yield test
            elif os.path.isdir(full_path):
                if not os.path.isfile(os.path.join(full_path, '__init__.py')):
                    continue

                load_tests = None
                tests = None
                if fnmatch(path, pattern):
                    # only check load_tests if the package directory itself matches the filter
                    name = self._get_name_from_path(full_path, top_level_dir)
                    package = self._get_module_from_name(name)
                    load_tests = getattr(package, 'load_tests', None)
                    tests = self.load_tests_from_module(package, use_load_tests=False)

                if tests is not None:
                    # tests loaded from package file
                    yield tests
                # recurse into the package
                for test in self.discover_tests(full_path, pattern, top_level_dir):
                    yield test

def start_server(pid, logfile, host, basedir, pattern='test*.py'):
    """
    Starts a TCP server for push/pull of the queue
    """
    Server(pid, logfile).start(host=host, basedir=basedir, pattern=pattern)

def stop_server(pid, logfile):
    """
    Stops a queue server.
    """
    Server(pid, logfile).stop()

class StartOptions(usage.Options):
    optParameters = [
        ["host", "h", "0.0.0.0:8011",
         "Specify the host (and port) for the server."],
        ["pid", "p", "mule.pid",
         "Specify the pid file for the server."],
        ["logfile", "l", "mule.log",
         "Specify the log file for the server."],
    ]

    def getSynopsis(self):
        return "Usage:    mule start [project] [options]"

    def parseArgs(self, *args):
        if len(args) > 0:
            self['basedir'] = os.path.realpath(args[0])
        else:
            # Use the current directory if no basedir was specified.
            self['basedir'] = os.getcwd()
        if len(args) > 1:
            raise usage.UsageError("I wasn't expecting so many arguments")

class StopOptions(usage.Options):
    optParameters = [
        ["pid", "p", "mule.pid",
         "Specify the pid file for the server."],
        ["logfile", "l", "mule.log",
         "Specify the log file for the server."],
    ]

    def getSynopsis(self):
        return "Usage:    mule stop [options]"

class Options(usage.Options):
    synopsis = "Usage:    mule <command> [command options]"

    subCommands = [
        # the following are all admin commands
        ['start', None, StartOptions,
         "Starts up a new queue (and server)"],
        ['stop', None, StopOptions,
         "Shuts down a running queue server"],
    ]

    def postOptions(self):
        if not hasattr(self, 'subOptions'):
            raise usage.UsageError("must specify a command")

def main():
    config = Options()
    try:
        config.parseOptions()
    except usage.error, e:
        print "%s:  %s" % (sys.argv[0], e)
        print
        c = getattr(config, 'subOptions', config)
        print str(c)
        sys.exit(1)

    command = config.subCommand
    so = config.subOptions

    if command == "start":
        start_server(**so)
    elif command == "stop":
        stop_server(**so)
    sys.exit(0)

if __name__ == '__main__':
    main()