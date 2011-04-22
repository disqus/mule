from __future__ import absolute_import

from django.test.simple import TEST_MODULE
from imp import find_module
from mule.utils import import_string
from mule.suite import defaultTestLoader

import os, os.path
import types
import unittest

def get_test_module(module):
    try:
        test_module = __import__('%s.%s' % (module.__name__.rsplit('.', 1)[0], TEST_MODULE), {}, {}, TEST_MODULE)
    except ImportError, e:
        # Couldn't import tests.py. Was it due to a missing file, or
        # due to an import error in a tests.py that actually exists?
        try:
            mod = find_module(TEST_MODULE, [os.path.dirname(module.__file__)])
        except ImportError:
            # 'tests' module doesn't exist. Move on.
            test_module = None
        else:
            # The module exists, so there must be an import error in the
            # test module itself. We don't need the module; so if the
            # module was a single file module (i.e., tests.py), close the file
            # handle returned by find_module. Otherwise, the test module
            # is a directory, and there is nothing to close.
            if mod[0]:
                mod[0].close()
            raise
    return test_module

def get_test_by_name(label, loader=defaultTestLoader):
    """Construct a test case with the specified label. Label should be of the
    form model.TestClass or model.TestClass.test_method. Returns an
    instantiated test or test suite corresponding to the label provided.
    """
    # TODO: Refactor this as the code sucks

    try:
        imp = import_string(label)
    except AttributeError:
        # XXX: Handle base_module.TestCase shortcut (assumption)
        module_name, class_name = label.rsplit('.', 1)
        imp = import_string(module_name)
        imp = import_string('%s.%s' % (get_test_module(imp).__name__, class_name))
    
    if isinstance(imp, types.ModuleType):
        return loader.loadTestsFromModule(imp)
    elif issubclass(imp, unittest.TestCase):
        return loader.loadTestsFromTestCase(imp)
    elif issubclass(imp.__class__, unittest.TestCase):
        return imp.__class__(imp.__name__)

    # If no tests were found, then we were given a bad test label.
    raise ValueError("Test label '%s' does not refer to a test" % label)