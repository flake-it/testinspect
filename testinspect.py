import gc
import os
import re
import ast
import time
import pickle
import pytest
import inspect
import subprocess as sp

from radon import metrics
from importlib import util
from psutil import Process
from coverage import Coverage
from distutils import sysconfig
from multiprocessing import Event, Pipe


COMMIT_WINDOW = 75
PYTHON_LIB = sysconfig.get_python_lib()
WHITESPACE_RE = re.compile("(^[ \t]*)(?:[^ \t\n])")


def get_churn_file(file_name, commit_window=COMMIT_WINDOW):
    l_no = 1
    churn_file = {}

    while True:
        proc = sp.run(
            [
                "git", "--no-pager", "log", "-L", f"{l_no},{l_no}:{file_name}", 
                "--no-patch", f"HEAD~{commit_window}..HEAD"
            ],
            encoding="UTF-8", stdout=sp.PIPE, stderr=sp.PIPE
        )

        if proc.returncode:
            expected = f"fatal: file {file_name} has only {l_no - 1} lines\n"

            if proc.stderr == expected:
                return churn_file

            proc.check_returncode()

        lines = proc.stdout.splitlines()
        churn_l_no = sum(l.startswith("commit") for l in lines)

        if churn_l_no:
            churn_file[l_no] = churn_l_no
            
        l_no += 1


def get_churn(commit_window=COMMIT_WINDOW):
    churn = {}

    stdout = sp.check_output(
        [
            "git", "--no-pager", "diff", "--name-only",
            f"HEAD~{commit_window}..HEAD"
        ],
        encoding="UTF-8"
    )

    for file_name in stdout.splitlines():
        if os.path.exists(file_name) and file_name.endswith(".py"):
            churn_file = get_churn_file(file_name, commit_window)

            if churn_file:
                churn[file_name] = churn_file

    return churn


def fix_indent(lines):
    text = "".join(lines)
    indent = WHITESPACE_RE.findall(lines[0])
    return re.sub(r"(?m)^" + indent[0], "", text) if indent else text


def get_ast_depth(node):
    if isinstance(node, ast.stmt):
        node_iter = ast.iter_child_nodes(node)
        return 1 + max((get_ast_depth(n) for n in node_iter), default=0)
    else:
        return 0


def is_external_module(mod_name):
    try:
        spec = util.find_spec(mod_name)
    except (ValueError, ModuleNotFoundError):
        return False

    if spec is None:
        return False

    origin = spec.origin or ""
    return origin.startswith(PYTHON_LIB)


def iter_mod_names_import(node):
    for n in node.names:
        mod_name = n.name.split(".")[0]

        if is_external_module(mod_name):
            yield mod_name


def iter_mod_names_import_from(node):
    if node.module is None:
        return

    mod_name = node.module.split(".")[0]

    if is_external_module(mod_name):
        yield mod_name


def iter_mod_names_name(node, co_varnames, test_mod):
    if node.id in co_varnames:
        return

    mod = getattr(test_mod, node.id, None)

    if mod is None:
        return

    if not inspect.ismodule(mod):
        mod = inspect.getmodule(mod)

        if mod is None:
            return
    
    try:
        mod_file = inspect.getsourcefile(mod) or ""
    except TypeError:
        return

    if not mod_file.startswith(PYTHON_LIB):
        return

    mod_name = getattr(mod, "__name__", None)

    if mod_name is not None:
        yield mod_name


def get_modules(test_ast, co_varnames, test_mod):
    modules = set()

    class Visitor(ast.NodeVisitor):
        def visit_Import(self, node):
            modules.update(iter_mod_names_import(node))

        def visit_ImportFrom(self, node):
            modules.update(iter_mod_names_import_from(node))

        def visit_Name(self, node):
            modules.update(iter_mod_names_name(node, co_varnames, test_mod))

        def visit_Attribute(self, node):
            outer = node

            while isinstance(outer, ast.Attribute):
                outer = outer.value

            self.visit(outer)

    Visitor().visit(test_ast)        
    return [mod_name for mod_name in modules if "pytest" not in mod_name]


def get_test_fn_data(test_fn):
    try:
        lines, _ = inspect.getsourcelines(test_fn)
    except (TypeError, OSError):
        return None

    try:
        test_ast = ast.parse(fix_indent(lines)).body[0]
    except SyntaxError:
        return None

    if not isinstance(test_ast, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None

    test_mod = inspect.getmodule(test_fn)

    if test_mod is None:
        return None

    ast_depth = max(get_ast_depth(n) for n in test_ast.body)
    n_assert = sum(isinstance(n, ast.Assert) for n in ast.walk(test_ast))
    n_mods = len(get_modules(test_ast, test_fn.__code__.co_varnames, test_mod))
    
    source = fix_indent(lines[test_ast.body[0].lineno - 1:])
    hal_vol, cyc_cmp, lloc, per_com = metrics.mi_parameters(source)
    mnt_idx = metrics.mi_compute(hal_vol, cyc_cmp, lloc, per_com)

    return ast_depth, n_assert, n_mods, hal_vol, cyc_cmp, lloc, mnt_idx


def get_cumulative(proc):
    io = proc.io_counters()
    ctx = proc.num_ctx_switches()
    return [time.time(), io.read_count, io.write_count, ctx.voluntary]


def get_noncumulative(proc):
    return [proc.num_threads(), proc.memory_full_info().uss]


class TestInspect:
    def __init__(self, base_file):
        cov_file = f"{base_file}.sqlite3"
        self.rusage_file = f"{base_file}.tsv"
        self.static_file = f"{base_file}.pkl"

        self.coverage = Coverage(
            cover_pylib=False,
            config_file=False,
            data_file=cov_file,
            source=[os.getcwd()]
        )
 
        for file_name in (cov_file, self.rusage_file, self.static_file):
            if os.path.exists(file_name):
                os.remove(file_name)

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, session, config, items):
        static_data = {}, {}, set(), get_churn()
        test_fn_ids, test_fn_data, test_files, _ = static_data

        for it in items:
            test_fn = getattr(it, "obj", None)

            if test_fn is None:
                continue

            fid = id(test_fn)

            if fid not in test_fn_data:
                test_fn_data[fid] = get_test_fn_data(test_fn)

            if test_fn_data[fid] is None:
                continue

            test_fn_ids[it.nodeid] = fid
            test_files.add(it.location[0])

        with open(self.static_file, "wb") as fd:
            pickle.dump(static_data, fd)

    def pytest_runtestloop(self, session):
        options = session.config.option

        if session.testsfailed and not options.continue_on_collection_errors:
            raise session.Interrupted(
                "%d error%s during collection" % (
                    session.testsfailed, 
                    "s" if session.testsfailed != 1 else ""
                )
            )

        if options.collectonly:
            return True

        gc.disable()
        parent, child = Pipe()
        noncumul_start, noncumul_stop = Event(), Event()

        for item in session.items:
            pid = os.fork()

            if pid == 0:
                self.coverage.load()
                self.coverage.start()
                self.coverage.switch_context(item.nodeid)

                proc = Process()
                cumul_pre = get_cumulative(proc)
                noncumul_base = get_noncumulative(proc)

                noncumul_start.set()

                try:
                    item.ihook.pytest_runtest_protocol(
                        item=item, nextitem=None
                    )
                finally:
                    noncumul_stop.set()

                    cumul_post = get_cumulative(proc)
                    cumul = [y - x for x, y in zip(cumul_pre, cumul_post)]
                    child.send((cumul, noncumul_base))

                    self.coverage.stop()
                    self.coverage.save()
                    os._exit(0)

            noncumul_start.wait()

            proc = Process(pid)
            noncumul_max = get_noncumulative(proc)

            while not noncumul_stop.wait(0.025):
                noncumul_max = [
                    max(x, y) for x, y in zip(
                        noncumul_max, get_noncumulative(proc)
                    )
                ]

            cumul, noncumul_base = parent.recv()
            noncumul = [y - x for x, y in zip(noncumul_base, noncumul_max)]
            rusage_data = "\t".join([str(x) for x in cumul + noncumul])

            with open(self.rusage_file, "a") as fd:
                fd.write(f"{rusage_data}\t{item.nodeid}\n")

            noncumul_start.clear()
            noncumul_stop.clear()
            os.waitpid(pid, 0)

        return True


def pytest_addoption(parser):
    group = parser.getgroup("TestInspect")
    
    group.addoption(
        "--testinspect", action="store", dest="testinspect", type=str
    )


def pytest_configure(config):
    base_file = config.getoption("testinspect")

    if base_file:
        config.pluginmanager.register(TestInspect(base_file))
