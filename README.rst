===========
TestInspect
===========

TestInspect is a `pytest <https://docs.pytest.org/en/6.2.x/>`_ plugin to measure various properties about test cases.

Installing
==========

TestInspect can be easily installed using ``pip install PATH`` where ``PATH`` is the path to the directory containing ``setup.py``.

Usage
=====

TestInspect offers a single command line option ``--testinspect=BASE_FILENAME`` and is disabled if this option is not used. TestInspect assumes that the current working directory is the top-level project directory and that this directory is a `git <https://git-scm.com/>`_ repository containing at least 75 previous commits.

Output
======

TestInspect generates three files: ``BASE_FILENAME.sqlite3``, ``BASE_FILENAME.tsv``, and ``BASE_FILENAME.pkl``, where BASE_FILENAME is given via the ``--testinspect`` option.

Coverage
--------

Line coverage data for each test case is stored in the `SQLite 3 <https://www.sqlite.org/index.html>`_ database ``BASE_FILENAME.sqlite3``. TestInspect uses `Coverage.py <https://coverage.readthedocs.io/en/coverage-5.5/>`_ to measure coverage.

Resource Usage
--------------

TestInspect measures resource usage metrics about each test case. These are stored in the tab-separated values file ``BASE_FILENAME.tsv``. The columns of this file are as follows:

- Wall-clock elapsed time (milliseconds).
- Number of read-related system calls.
- Number of write-related system calls.
- Number of voluntary context switches.
- Peak number of concurrently running threads (excluding the main thread).
- Peak memory usage (unique set size, bytes).
- The unique name of the test case, known as a *node ID*.

Static Metrics
--------------

As well as dynamic properties such as coverage and resource usage, TestInspect also measure various static metrics about the source code of test functions, stored in ``BASE_FILENAME.pkl``. This is a pickled ``list`` object containing the following elements:

- A ``dict`` mapping test case node IDs to test function IDs.
- A ``dict`` mapping test function IDs to ``lists`` containing the following elements:

    - Maximum depth of nested program statements.
    - Number of assertion statements.
    - Number of external modules used.
    - Halstead volume.
    - Cyclomatic complexity.
    - Number of lines of code.
    - Maintainability index.
    
- A ``set`` of file names containing the project's test cases.
- A ``dict`` mapping file names to ``dicts`` mapping line numbers to the number of times the line has been modified in the last 75 commits.