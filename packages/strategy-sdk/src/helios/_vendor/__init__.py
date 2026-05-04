"""Vendored third-party code, isolated from the public SDK API.

Each subpackage retains its upstream LICENSE file; nothing here is
re-exported from `helios.*` outside the wrappers in `helios/poseidon.py`.
Vendored rather than depending on PyPI to keep the SDK installable on
Python 3.11 (some upstreams over-pin `requires-python`).
"""
