# -*- coding: utf-8 -*-

# Copyright 2022-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

import gc
import itertools
import sys
import time

__version__ = "0.4.2"

TIMER = time.perf_counter_ns
TICKS_PER_SECOND = 1_000_000_000

TEMPLATE = """
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


class GC():

    def __init__(self, enable):
        self.enable = enable

    def __enter__(self):
        self._previous_state = gc.isenabled()
        self._set_state(self.enable)

    def __exit__(self, exc, value, tb):
        self._set_state(self._previous_state)

    def _set_state(self, state):
        gc.enable() if state else gc.disable()


def extract_code(path):
    name = None
    fidx = 0
    setup = []
    functions = {}

    with open(path) as file:
        for line in file:

            if line.startswith("def "):
                name = (line[4:].partition(":")[0].rstrip("()")
                                .partition("(")[0].strip())
                if name.startswith("_"):
                    name = None
                    setup.append(line)
                else:
                    if name != "base":
                        fidx += 1
                        name = f"{fidx} {name}"
                    functions[name] = lines = []

            elif name:
                if line.startswith((" ", "\n")):
                    lines.append(line)
                else:
                    name = None
                    setup.append(line)

            else:
                setup.append(line)

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

            lines[idx] = f"{ws}{line[wslen+2:-1].lstrip()}\n"
            if idx + 1 < len(lines):
                lines[idx] += f"{ws}continue\n"
        else:
            lines[idx] = f"    {line}"


def unindent(lines):
    for idx, line in enumerate(lines):
        lines[idx] = line[4:]


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
    return TEMPLATE.format(
        setup=join(setup), init=join(init), code=join(code))


def benchmark_compile(source, name="inner"):
    code_object = compile(source, "<perf-src>", "exec")

    # execute code to generate timing function
    namespace = {}
    exec(code_object, namespace)
    return namespace[name]


def benchmark_run(function, iterations, timer=TIMER, enable_gc=False):
    iterator = itertools.repeat(None, iterations)
    with GC(enable_gc):
        return function(iterator, timer)


def guess_iterations(function, threshold=TICKS_PER_SECOND):
    iterations = 1_000
    timing = benchmark_run(function, iterations)
    return int(threshold / timing * iterations)


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
        "-s", "-S", "--show-source",
        dest="show", action="append_const", const="source",
        help="Display generated benchmark code",
    )
    parser.add_argument(
        "-b", "-B", "--show-bytecode",
        dest="show", action="append_const", const="bytecode",
        help="Display bytecode",
    )
    parser.add_argument(
        "-r", "-R", "--show-results",
        dest="show", action="append_const", const="result",
        help="Display return values",
    )
    parser.add_argument(
        "-p", "-P", "--show-python",
        dest="python", action="store_true",
        help="Display Python version",
    )
    parser.add_argument(
        "-n", "--iterations",
        dest="iterations", metavar="N", type=int, default=0,
        help="Number of iterations",
    )
    parser.add_argument(
        "-t", "--threshold",
        dest="threshold", metavar="SECONDS", type=float, default=0.0,
        help="Number of seconds to run a benchmark for",
    )
    parser.add_argument(
        "-g", "--gc",
        dest="gc", action="store_true",
        help="Enable garbage collection during benchmark runs",
    )
    parser.add_argument(
        "-l", "--loop",
        dest="loop", action="store_false",
        help="Keep loop overhead in benchmark timings",
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

    mode = mode_show if args.show else mode_benchmark
    return mode(args, functions, setup)


def mode_benchmark(args, functions, setup):
    indent(setup)

    baseline = error = None
    iterations = args.iterations
    length = max(map(len, functions))
    stdout_write = sys.stdout.write
    stdout_flush = sys.stdout.flush

    if args.threshold:
        args.threshold = int(args.threshold * TICKS_PER_SECOND)
    else:
        args.threshold = TICKS_PER_SECOND

    if source := functions.pop("base", None):
        code = benchmark_generate(source, setup=setup)
        func = benchmark_compile(code)
        iters = iterations or guess_iterations(func, args.threshold)
        ns_base = benchmark_run(func, iters, enable_gc=args.gc) / iters
    elif args.loop:
        iters = 1_000_000
        ns_base = benchmark_run(benchmark_compile(benchmark_generate(
            ["    pass"])), iters, enable_gc=False) / iters
    else:
        ns_base = 0.0

    if args.python:
        stdout_write(f"{sys.version}\n")

    for name, source in functions.items():
        code = benchmark_generate(source, setup=setup)
        func = benchmark_compile(code)

        try:
            benchmark_run(func, 1)
        except Exception as exc:
            stdout_write(f"{name}:  {exc.__class__.__name__}: {exc}\n")
            error = True

        functions[name] = func

    if error:
        return 1

    for name, function in functions.items():
        stdout_write(f"{name}{' ' * (length - len(name))}: ")
        stdout_flush()

        iters = iterations or guess_iterations(function, args.threshold)
        timing = benchmark_run(function, iters, enable_gc=args.gc)

        ns_iter = timing / iters - ns_base
        if baseline is None:
            baseline = ns_iter

        stdout_write(f"{ns_iter:,.2f}ns "
                     f"{ns_iter / baseline:5.2f}\n")


def mode_show(args, functions, setup):
    show = args.show
    show_result = ("result" in show)
    show_source = ("source" in show)
    show_bytecode = ("bytecode" in show)

    stdout_write = sys.stdout.write
    stdout_flush = sys.stdout.flush

    if args.python:
        stdout_write(f"{sys.version}\n")
    if show_bytecode:
        import dis

    indent(setup)
    functions.pop("base", None)

    for name, source in functions.items():

        stdout_write(f"{name}:\n")

        if show_result:
            code = benchmark_generate(source, setup=setup, return_stmt=True)
            try:
                result = benchmark_run(benchmark_compile(code), 1)
                stdout_write(f">> Result: {repr(result)}\n")
            except Exception as exc:
                stdout_write(f">> Result: {exc.__class__.__name__}: {exc}\n")

        if show_source:
            code = benchmark_generate(source, setup=setup)
            stdout_write(f">> Source:{code}\n")

        if show_bytecode:
            unindent(source)
            stdout_write(">> Bytecode:\n")
            dis.dis("\n".join(source))

        stdout_flush()
