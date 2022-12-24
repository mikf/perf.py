#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gc
import itertools
import sys
import time

__version__ = "0.1.0"


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

    append_setup = setup.append

    with open(path) as file:
        for line in file:

            if line.startswith("def "):
                name = line[4:].partition("(")[0].strip()
                functions[name] = lines = []
                append_lines = lines.append

            elif name:
                if line.startswith(" "):
                    append_lines(line)
                else:
                    name = None
                    append_setup(line)

            else:
                append_setup(line)

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

    # execute code to generate timing function
    namespace = {}
    exec(code_object, namespace)
    return namespace["inner"]


def benchmark(function, iterations):
    iterator = itertools.repeat(None, iterations)
    timer = time.perf_counter

    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        return function(iterator, timer)
    finally:
        if gc_enabled:
            gc.enable()


def guess_iterations(function, threshold=1.0):
    iterations = 10
    threshold /= 10.0

    while True:
        timing = benchmark(function, iterations)
        iterations *= 10
        if timing >= threshold:
            return iterations


def parse_arguments(args=None):
    import argparse

    class Formatter(argparse.HelpFormatter):
        """Custom HelpFormatter class to customize help output"""
        def __init__(self, *args, **kwargs):
            super().__init__(max_help_position=30, *args, **kwargs)

        def _format_action_invocation(self, action):
            opts = action.option_strings[:]
            if opts:
                if action.nargs != 0:
                    args_string = self._format_args(action, "ARG")
                    opts[-1] += " " + args_string
                return ", ".join(opts)
            else:
                return self._metavar_formatter(action, action.dest)(1)[0]

    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTION]... PATH",
        formatter_class=Formatter,
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help",
        action="help",
        help="Print this help message and exit",
    )
    parser.add_argument(
        "--version",
        action="version", version=__version__,
        help="Print program version and exit",
    )
    parser.add_argument(
        "-n", "--iterations",
        dest="iterations", metavar="N", type=int, default=0,
        help="",
    )
    parser.add_argument(
        "-t", "--threshold",
        dest="threshold", metavar="SECONDS", type=float, default=1.0,
        help="",
    )
    parser.add_argument(
        "path",
        metavar="PATH",
        help=argparse.SUPPRESS,
    )

    return parser.parse_args(args)


def main():
    args = parse_arguments()

    setup, functions = extract_code(args.path)
    indent(setup)

    baseline = None
    iterations = args.iterations
    length = max(map(len, functions))
    stdout_write = sys.stdout.write
    stdout_flush = sys.stdout.flush

    for name, source in functions.items():

        stdout_write(f"{name}{' ' * (length - len(name))}: ")
        stdout_flush()

        function = build_function(source, setup=setup)

        if not iterations:
            iterations = guess_iterations(function, args.threshold)

        timing = benchmark(function, iterations)

        if baseline is None:
            baseline = timing

        stdout_write(f"{timing:6.3f}s {timing / baseline:5.2f}\n")


if __name__ == "__main__":
    sys.exit(main())
