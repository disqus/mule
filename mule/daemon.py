import errno
import logging
import os
import signal
import sys
import time

class Daemon(object):
    logger_name = 'daemon'
    loglevel = logging.WARN

    def __init__(self, pidfile, logfile):
        self.pidfile = os.path.abspath(pidfile)
        self.logfile = os.path.abspath(logfile)

    def run(self, **options):
        """Override.

        The terminal has been detached at this point.
        """
        raise NotImplementedError

    def on_sigterm(self, signalnum, frame):
        """Handle segterm by treating as a keyboard interrupt"""
        raise KeyboardInterrupt('SIGTERM')

    def add_signal_handlers(self):
        """Register the sigterm handler"""
        signal.signal(signal.SIGTERM, self.on_sigterm)

    def start(self, **options):
        """Initialize and run the daemon"""
        # The order of the steps below is chosen carefully.
        # - don't proceed if another instance is already running.
        self.check_pid()
        # - start handling signals
        self.add_signal_handlers()
        # - create log file and pid file directories if they don't exist
        self.prepare_dirs()
        # - start_logging must come after check_pid so that two
        # processes don't write to the same log file, but before
        # setup_root so that work done with root privileges can be
        # logged.
        self.start_logging()
        try:
            self.check_pid_writable()

            # - daemonize
            daemonize()
        except:
            self.logger.exception("failed to start due to an exception")
            raise

        # - write_pid must come after daemonizing since the pid of the
        # long running process is known only after daemonizing
        self.write_pid()
        try:
            self.logger.info("started")
            try:
                self.run(**options)
            except (KeyboardInterrupt, SystemExit):
                pass
            except:
                self.logger.exception("stopping with an exception")
                raise
        finally:
            self.remove_pid()
            self.logger.info("stopped")

    def stop(self):
        """Stop the running process"""
        if self.pidfile and os.path.exists(self.pidfile):
            try:
                pid = int(open(self.pidfile).read())
            except (ValueError, TypeError):
                pid = None
            if not pid:
                sys.exit("not running")
            os.kill(pid, signal.SIGTERM)
            # wait for a moment to see if the process dies
            for n in range(10):
                time.sleep(0.25)
                try:
                    # poll the process state
                    os.kill(pid, 0)
                except OSError, why:
                    if why[0] == errno.ESRCH:
                        # process has died
                        break
                    else:
                        raise
            else:
                sys.exit("pid %d did not die" % pid)
        else:
            sys.exit("not running")

    def prepare_dirs(self):
        """Ensure the log and pid file directories exist and are writable"""
        for fn in (self.pidfile, self.logfile):
            if not fn:
                continue
            parent = os.path.dirname(fn)
            if not os.path.exists(parent):
                os.makedirs(parent)

    def start_logging(self):
        """Configure the logging module"""
        try:
            level = int(self.loglevel)
        except ValueError:
            level = int(logging.getLevelName(self.loglevel.upper()))

        handlers = []
        if self.logfile:
            handlers.append(logging.FileHandler(self.logfile))
        # # also log to stderr
        # handlers.append(logging.StreamHandler())

        self.logger = logging.getLogger(self.logger_name)
        self.logger.setLevel(level)
        for h in handlers:
            h.setFormatter(logging.Formatter(
                "%(asctime)s %(process)d %(levelname)s %(message)s"))
            self.logger.addHandler(h)

    def check_pid(self):
        """Check the pid file.

        Stop using sys.exit() if another instance is already running.
        If the pid file exists but no other instance is running,
        delete the pid file.
        """
        if not self.pidfile:
            return
        # based on twisted/scripts/twistd.py
        if os.path.exists(self.pidfile):
            try:
                data = open(self.pidfile).read().strip()
                if not data: return
                pid = int(data)
            except ValueError:
                msg = 'pidfile %s contains a non-integer value' % self.pidfile
                sys.exit(msg)
            try:
                os.kill(pid, 0)
            except OSError, (code, text):
                if code == errno.ESRCH:
                    # The pid doesn't exist, so remove the stale pidfile.
                    self.remove_pid()
                    # os.remove(self.pidfile)
                else:
                    msg = ("failed to check status of process %s "
                           "from pidfile %s: %s" % (pid, self.pidfile, text))
                    sys.exit(msg)
            else:
                msg = ('another instance seems to be running (pid %s), '
                       'exiting' % pid)
                sys.exit(msg)

    def check_pid_writable(self):
        """Verify the user has access to write to the pid file.

        Note that the eventual process ID isn't known until after
        daemonize(), so it's not possible to write the PID here.
        """
        if not self.pidfile:
            return
        if os.path.exists(self.pidfile):
            check = self.pidfile
        else:
            check = os.path.dirname(self.pidfile)
        if not os.access(check, os.W_OK):
            msg = 'unable to write to pidfile %s' % self.pidfile
            sys.exit(msg)

    def write_pid(self):
        """Write to the pid file"""
        if self.pidfile:
            open(self.pidfile, 'wb').write(str(os.getpid()))

    def remove_pid(self, perm=False):
        """Delete the pid file"""
        if self.pidfile and os.path.exists(self.pidfile):
            if perm:
                os.remove(self.pidfile)
            else:
                open(self.pidfile, 'wb')

def daemonize():
    """Detach from the terminal and continue as a daemon"""
    # swiped from twisted/scripts/twistd.py
    # See http://www.erlenstar.demon.co.uk/unix/faq_toc.html#TOC16
    if os.fork():   # launch child and...
        os._exit(0) # kill off parent
    os.setsid()
    if os.fork():   # launch child and...
        os._exit(0) # kill off parent again.
    os.umask(077)
    null=os.open('/dev/null', os.O_RDWR)
    for i in range(3):
        try:
            os.dup2(null, i)
        except OSError, e:
            if e.errno != errno.EBADF:
                raise
    os.close(null)