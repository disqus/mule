#!/usr/bin/env python

try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

tests_require = []

setup(
    name='Mule',
    version='1.0',
    author='DISQUS',
    author_email='opensource@disqus.com',
    url='http://github.com/disqus/mule',
    description = 'Utilities for sharding test cases in BuildBot',
    packages=find_packages(),
    zip_safe=False,
    install_requires=[],
    dependency_links=[],
    tests_require=tests_require,
    extras_require={'test': tests_require},
    test_suite='mule.runtests.runtests',
    include_package_data=True,
    classifiers=[
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Topic :: Software Development'
    ],
)
