from django.dispatch.dispatcher import Signal

# Sent after our test suite is fully initialized
post_test_setup = Signal()
