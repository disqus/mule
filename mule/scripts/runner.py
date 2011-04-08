#!/usr/bin/env python
from optparse import OptionParser
from mule.base import Mule

import sys

def main(*args):
    if len(args) < 2:
        print "%s: [test]" % (args[0],)
        sys.exit(1)

    parser = OptionParser()
    if args[0] == 'test':
        parser.add_option("-b", "--basedir", default=".",
                          help="Specify the directory to discover tests from.")
        parser.add_option("-r", "--runner", default="unit2",
                          help="Specify the test suite runner (use #TEST# for path.to.TestCase substitution).")

    (options, args) = parser.parse_args()
    if args[0] == "test":
        mule = Mule()
        print '\n'.join(mule.process(**options))
    sys.exit(0)

if __name__ == '__main__':
    main(*sys.argv)