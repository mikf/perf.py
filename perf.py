#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gc
import itertools
import sys
import time

__version__ = "0.1.3"


template = """
def inner(__iterator, __timer):
# setup
{setup}
# init
{init}
# loop
    __t0 = __timer()
    for _ in __iterator:
{code}
    __t1 = __timer()
    return __t1 - __t0
"""


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
                if line.startswith((" ", "\n")):
                    append_lines(line)
                else:
                    name = None
                    append_setup(line)

            else:
                append_setup(line)

    return setup, functions


def indent(lines):
    for idx, line in enumerate(lines):
        lines[idx] = f"    {line}"


def indent_strip_return(lines):
    for idx, line in enumerate(lines):
        sline = line.lstrip()
        if sline.startswith("return "):
            wslen = len(line) - len(sline) + 4
            ws = " " * wslen
            lines[idx] = f"{ws}({line[wslen+3:-1]})\n{ws}continue\n"
        else:
            lines[idx] = f"    {line}"


def benchmark_generate(code, setup=(), return_stmt=False):
    for idx, line in enumerate(code):
        if line.strip() == "###":
            init = code[:idx]
            code = code[idx+1:]
            break
    else:
        init = ()
        code = code.copy()

    if return_stmt:
        indent(code)
        code.append("    return")
    else:
        indent_strip_return(code)

    join = "".join
    return template.format(
        setup=join(setup), init=join(init), code=join(code))


def benchmark_compile(source):
    code_object = compile(source, "<perf-src>", "exec")

    # execute code to generate timing function
    namespace = {}
    exec(code_object, namespace)
    return namespace["inner"]


def benchmark_run(function, iterations):
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
        timing = benchmark_run(function, iterations)
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
        "-S", "--show-source",
        dest="show_source", action="store_true",
        help="Display generated benchmark code",
    )
    parser.add_argument(
        "-R", "--show-result",
        dest="show_result", action="store_true",
        help="Display function return values",
    )
    parser.add_argument(
        "-n", "--iterations",
        dest="iterations", metavar="N", type=int, default=0,
        help="Number of iterations",
    )
    parser.add_argument(
        "-t", "--threshold",
        dest="threshold", metavar="SECONDS", type=float, default=1.0,
        help="Number of seconds to run a benchmark for",
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

        code = benchmark_generate(source, setup=setup)

        if args.show_source:
            stdout_write(f"\n{code}\n")
            continue

        function = benchmark_compile(code)

        if args.show_result:
            result = benchmark_run(benchmark_compile(benchmark_generate(
                source, setup=setup, return_stmt=True)), 1)
            stdout_write(f"{result} ")
            stdout_flush()

        if not iterations:
            iterations = guess_iterations(function, args.threshold)

        timing = benchmark_run(function, iterations)

        if baseline is None:
            baseline = timing

        stdout_write(f"{timing:6.3f}s {timing / baseline:5.2f}\n")


if __name__ == "__main__":
    sys.exit(main())
