import os
import ast
import pytest
import subprocess as sp

from testinspect import get_churn, fix_indent, get_ast_depth


def git_repo_commit():
    sp.run(["git", "add", "-A"], check=True, stdout=sp.DEVNULL)
    sp.run(["git", "commit", "-m", "foo"], check=True, stdout=sp.DEVNULL)


@pytest.fixture
def git_repo(tmpdir):
    cwd = os.getcwd()
    os.chdir(tmpdir.strpath)
    sp.run(["git", "init"], check=True, stdout=sp.DEVNULL)

    yield

    os.chdir(cwd)


def test_get_churn(git_repo):
    with open("foo.py", "w") as fd_foo, \
         open("bar.py", "w") as fd_bar, \
         open("baz.py", "w") as fd_baz:
        fd_foo.write("foo\nbar\nbaz\n")
        fd_bar.write("foo\nbar\nbaz\n")
        fd_baz.write("foo\nbar\nbaz\n")

    git_repo_commit()

    with open("foo.py", "w") as fd:
        fd.write("foo\nbarr\nbaz\n")

    git_repo_commit()

    with open("bar.py", "w") as fd:
        fd.write("fooo\nbar\nbazz\n")

    git_repo_commit()

    with open("foo.py", "w") as fd:
        fd.write("foo\nbarrr\nbaz\n")

    git_repo_commit()

    assert get_churn(commit_window=3) == {
        "foo.py": {2: 2}, "bar.py": {1: 1, 3: 1}
    }


def test_fix_indent():
    lines1 = [
        "    foo\n", 
        "        bar\n", 
        "    baz\n", 
        "    qux\n"
    ]

    lines2 = [
        "    foo\n", 
        "        bar\n", 
        "baz\n", 
        "    qux\n"
    ]

    assert fix_indent(lines1) == fix_indent(lines2) == (
        "foo\n"
        "    bar\n"
        "baz\n"
        "qux\n"
    )


@pytest.mark.parametrize(
    "source,expected", 
    [
        (
            "a = foo()\n",
            1
        ),
        (
            "if bar():\n"
            "    a = foo()\n",
            2
        ),
        (
            "for x in bar():\n"
            "    if bar():\n"
            "        a = foo()\n",
            3
        ),
        (
            "for x in bar():\n"
            "    if bar():\n"
            "        a = foo()\n"
            "if bar():\n"
            "    a = foo()\n",
            3
        ),        
        (
            "while baz():\n"
            "    for x in bar():\n"
            "        if bar():\n"
            "            a = foo()\n"
            "if bar():\n"
            "    a = foo()\n",
            4
        )
    ]
)
def test_get_ast_depth(source, expected):
    assert max(get_ast_depth(n) for n in ast.parse(source).body) == expected