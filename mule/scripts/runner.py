#!/usr/bin/env python
from optparse import OptionParser
from mule.base import Mule

import sys

def main():
    args = sys.argv
    if len(args) < 2:
        print "usage: mule [command] [options]"
        print
        print "Available subcommands:"
        print "  test"
        sys.exit(1)

    parser = OptionParser()
    if args[1] == 'test':
        parser.add_option("-b", "--basedir", default=".",
                          help="Specify the directory to discover tests from.")
        parser.add_option("-r", "--runner", default="python manage.py mtest #TEST#",
                          help="Specify the test suite runner (use #TEST# for path.to.TestCase substitution).")

    (options, args) = parser.parse_args()
    if args[0] == "test":
        mule = Mule()
        print '\n'.join(mule.process(**options.__dict__))
    sys.exit(0)

if __name__ == '__main__':
    main()