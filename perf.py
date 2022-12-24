#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gc
import itertools
import sys
import time


template = """
def inner(__iterator, __timer):
{setup}
{init}
    __t0 = __timer()
    for _ in __iterator:
{code}
    __t1 = __timer()
    return __t1 - __t0
"""


def indent(lines):
    for idx, line in enumerate(lines):
        lines[idx] = f"    {line}"


def extract_code(path):
    name = None
    setup = []
    functions = {}

    with open(path) as file:
        for line in file:

            if line.startswith("def "):
                name = line[4:].partition("(")[0].strip()
                functions[name] = lines = []

            elif name:
                if line.startswith(" "):
                    lines.append(line)
                else:
                    name = None
                    setup.append(line)

            else:
                setup.append(line)

    return setup, functions


def build_function(code, setup=()):
    for idx, line in enumerate(code):
        if line.strip() == "###":
            init = code[:idx]
            code = code[idx+1:]
            break
    else:
        init = ()

    indent(code)

    # generate and compile code
    join = "".join
    source = template.format(
        setup=join(setup), init=join(init), code=join(code))
    code_object = compile(source, "<perf-src>", "exec")

    # 'run' code to generate timing function
    namespace = {}
    exec(code_object, namespace)
    return namespace["inner"]


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


def main():
    path = sys.argv[1]
    setup, functions = extract_code(path)
    indent(setup)

    baseline = iterations = None
    length = max(map(len, functions))
    stdout_write = sys.stdout.write
    stdout_flush = sys.stdout.flush

    for name, source in functions.items():

        stdout_write(f"{name}{' ' * (length - len(name))}: ")
        stdout_flush()

        function = build_function(source, setup=setup)

        if iterations is None:
            iterations = 1
            while True:
                timing = benchmark(function, iterations)
                iterations *= 10
                if timing >= 0.1:
                    break

        timing = benchmark(function, iterations)

        if baseline is None:
            baseline = timing

        stdout_write(f"{timing:3.5f}s{timing / baseline: 3.2f}\n")


if __name__ == "__main__":
    sys.exit(main())
