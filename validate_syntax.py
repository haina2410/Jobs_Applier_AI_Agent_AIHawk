#!/usr/bin/env python
import py_compile
import sys

files = ['test_job_extraction.py', 'QUICK_START.py']
failed = False

for file in files:
    try:
        py_compile.compile(file, doraise=True)
        print(f"✓ {file}")
    except py_compile.PyCompileError as e:
        print(f"✗ {file}")
        print(e)
        failed = True

sys.exit(1 if failed else 0)
