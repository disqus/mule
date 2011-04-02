#!/usr/bin/env python
from twisted.python import usage
import sys

def build_queue(entry_point, prioritize=set()):
    """
    Builds a queue of all TestCase subclasses.
    """

def start_server(pid, host):
    """
    Starts a TCP server for push/pull of the queue
    """
    
    jobs = build_queue()

def stop_server(pid):
    """
    Stops a queue server.
    """

class StartOptions(usage.Options):
    optParameters = [
        ["host", "h", "0.0.0.0:8011",
         "Specify the host (and port) for the server."],
        ["pid", "p", "mule.pid",
         "Specify the pid file for the server."],
    ]

    def getSynopsis(self):
        return "Usage:    mule start [options]"

class StopOptions(usage.Options):
    optParameters = [
        ["pid", "p", "mule.pid",
         "Specify the pid file for the server."],
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

    def opt_version(self):
        import buildbot
        print "Buildbot version: %s" % buildbot.version
        usage.Options.opt_version(self)

    def opt_verbose(self):
        from twisted.python import log
        log.startLogging(sys.stderr)

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

    if command == "start-server":
        start_server(so)
    elif command == "stop-server":
        stop_server(so)
    sys.exit(0)

if __name__ == '__main__':
    main()