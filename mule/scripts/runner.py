#!/usr/bin/env python
from optparse import OptionParser
from mule import VERSION
from mule.base import Mule, MultiProcessMule

import sys

def main():
    args = sys.argv
    if len(args) < 2:
        print "usage: mule [command] [options]"
        print
        print "Available subcommands:"
        print "  test"
        sys.exit(1)

    parser = OptionParser(version="%%prog %s" % VERSION)
    if args[1] == 'test':
        parser.add_option('--basedir', default='.', metavar='PATH',
                          help='Specify the directory to discover tests from.')
        parser.add_option('--runner', default='unit2 $TEST', metavar='RUNNER',
                          help='Specify the test suite runner (use $TEST for path.to.TestCase substitution).')
        parser.add_option('--max-workers', dest='max_workers', type='int', metavar="NUM",
                          help='Number of workers to consume. With multi-process this is the number of processes to spawn. With distributed this is the number of Celeryd servers to consume.')
        parser.add_option('--multiprocess', dest='multiprocess', action='store_true',
                          help='Use multi-process on the same machine instead of the Celery distributed system.')
        parser.add_option('--workspace', dest='workspace', metavar="WORKSPACE",
                          help='Specifies the workspace for this build.')

    (options, args) = parser.parse_args()
    if args[0] == "test":
        if options.multiprocess:
            cls = MultiProcessMule
        else:
            cls = Mule
        mule = cls(max_workers=options.max_workers, workspace=options.workspace)
        jobs = mule.discover_tests(options.basedir)
        print '\n'.join(mule.process(jobs, options.runner))

    sys.exit(0)

if __name__ == '__main__':
    main()