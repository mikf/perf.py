#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gc
import inspect
import itertools
import os
import re
import sys
import time


template = """
def func(_it, _timer):
{setup}
{init}
    _t0 = _timer()
    for _i in _it:
{code}
    _t1 = _timer()
    return _t1 - _t0
"""


def import_file(path):
    directory, filename = os.path.split(path)
    module_name = re.sub(r"\.(?:pyw?|exe)$", "", filename)

    original_path = sys.path
    try:
        sys.path = (directory,)
        return __import__(module_name)
    finally:
        sys.path = original_path


def extract_code(module):
    module_name = module.__name__

    return {
        name: inspect.getsourcelines(obj)[0][1:]
        for name, obj in module.__dict__.items()
        if callable(obj) and obj.__module__ == module_name
    }


def build_function(code, setup=()):
    for idx, line in enumerate(code):
        if line.strip() == "###":
            init = code[:idx]
            code = code[idx+1:]
            break
    else:
        init = ()

    # indent
    for idx, line in enumerate(code):
        code[idx] = f"    {line}"

    # generate and compile code
    join = "".join
    source = template.format(
        setup=join(setup), init=join(init), code=join(code))
    code_object = compile(source, "<perf-src>", "exec")

    # 'run' code to generate timing function
    namespace = {}
    exec(code_object, namespace)
    return namespace["func"]


def benchmark(function, iterations):
    iterator = itertools.repeat(None, iterations)
    timer = time.perf_counter

    gc_old = gc.isenabled()
    gc.disable()

    try:
        return function(iterator, timer)
    finally:
        if gc_old:
            gc.enable()


def measure(path, iterations=None):
    module = import_file(path)
    code = extract_code(module)
    setup = code.pop("setup", ())

    baseline = None
    l = len(max(code, key=len))
    stdout_write = sys.stdout.write
    stdout_flush = sys.stdout.flush

    for name, source in code.items():

        stdout_write(f"{name}{' ' * (l - len(name))}: ")
        stdout_flush()

        function = build_function(source, setup=setup)

        if iterations is None:
            iterations = 1
            while True:
                timing = benchmark(function, iterations)
                iterations *= 10
                if timing >= 0.05:
                    break

        timing = benchmark(function, iterations)

        if baseline is None:
            baseline = timing

        stdout_write(f"{timing:3.5f}s{timing / baseline: 3.2f}\n")


if __name__ == "__main__":
    measure(sys.argv[1])
