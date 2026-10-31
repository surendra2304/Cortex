"""Cortex test suite package.

Making ``tests`` a regular package (rather than an implicit namespace package)
keeps ``from tests.conftest import ...`` resolving to this suite even when an
unrelated ``tests`` package is installed into site-packages by a third-party
dependency.
"""
