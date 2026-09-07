"""Keep Python 3.9 deployments on aiohttp's unaffected Python response parser."""

import os
import sys

# aiohttp 3.14.3 fixes CVE-2026-69244 but requires Python >= 3.10.
# The upstream workaround for older Python is to disable the C extensions.
# This must run before the first aiohttp import. TLS/authentication are unchanged.
if sys.version_info < (3, 10):
    os.environ['AIOHTTP_NO_EXTENSIONS'] = '1'
