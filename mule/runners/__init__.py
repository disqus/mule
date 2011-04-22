import signal
import sys

def make_test_runner(parent):
    class new(parent):
        def __init__(self, failfast=False, run_callback=None, **kwargs):
            super(new, self).__init__(**kwargs)
            self.failfast = failfast
            self.run_callback = run_callback
            self._keyboard_interrupt_intercepted = False

        def run(self, *args, **kwargs):
            """
            Runs the test suite after registering a custom signal handler
            that triggers a graceful exit when Ctrl-C is pressed.
            """
            self._default_keyboard_interrupt_handler = signal.signal(signal.SIGINT,
                self._keyboard_interrupt_handler)

            if self.run_callback:
                self.run_callback(self)

            try:
                result = super(new, self).run(*args, **kwargs)
            finally:
                signal.signal(signal.SIGINT, self._default_keyboard_interrupt_handler)
            return result

        def _keyboard_interrupt_handler(self, signal_number, stack_frame):
            """
            Handles Ctrl-C by setting a flag that will stop the test run when
            the currently running test completes.
            """
            self._keyboard_interrupt_intercepted = True
            sys.stderr.write(" <Test run halted by Ctrl-C> ")
            # Set the interrupt handler back to the default handler, so that
            # another Ctrl-C press will trigger immediate exit.
            signal.signal(signal.SIGINT, self._default_keyboard_interrupt_handler)

        def _makeResult(self):
            result = super(new, self)._makeResult()
            failfast = self.failfast

            def stoptest_override(func):
                def stoptest(test):
                    # If we were set to failfast and the unit test failed,
                    # or if the user has typed Ctrl-C, report and quit
                    if (failfast and not result.wasSuccessful()) or \
                        self._keyboard_interrupt_intercepted:
                        result.stop()
                    func(test)
                return stoptest

            setattr(result, 'stopTest', stoptest_override(result.stopTest))
            return result
    new.__name__ = parent.__name__
    return new