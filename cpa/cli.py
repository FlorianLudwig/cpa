"""Console script for create python app."""
from __future__ import annotations

import sys
import os
import subprocess
import typing
import shutil
import dataclasses

import pkg_resources
import click
import tomlkit


def find_project_root(path: str = ".") -> str:
    path = os.path.abspath(path)
    files_in_folder = os.listdir(path)
    if ".git" in files_in_folder or "pyproject.toml" in files_in_folder:
        return path

    parent = os.path.join(path, os.path.pardir)
    parent = os.path.abspath(parent)
    if parent == path:
        raise AttributeError("project root not found")

    return find_project_root(parent)


@dataclasses.dataclass
class Config:
    name: str
    public: bool


class Project:
    pyproject: Optional[tomlkit.document]

    def __init__(self, path: str):
        self.path = path
        pyproject_path = os.path.join(path, "pyproject.toml")

        if os.path.exists(pyproject_path):
            tomlkit.document()
            with open(pyproject_path) as config_fo:
                config_data = config_fo.read()
            self.pyproject = tomlkit.loads(config_data)

    @classmethod
    def find(cls) -> Project:
        path = find_project_root()
        return cls(path)

    def metadata(self) -> Config:
        name = None
        public = False

        if self.pyproject:
            tool = self.pyproject.get("tool", {})
            name = tool.get("poetry", {}).get("name", None)
            name = tool.get("cpa", {}).get("name", name)
            public = tool.get("cpa", {}).get("public", public)

        if name is None:
            raise AttributeError("Could not determine package name")
        
        metadata = Config(name, public)
        return metadata

    @property
    def pylintrc(self):
        project_sepecific_pylintrc = os.path.join(self.path, ".pylintrc")
        if os.path.exists(project_sepecific_pylintrc):
            return project_sepecific_pylintrc

        return pkg_resources.resource_filename("cpa", "pylintrc")


def run_tests(project: Project) -> int:
    conf = project.metadata()
    module = conf["name"]

    # allow syntax new in python 3.6
    cmd = ["black", "--check", "--target-version", "py36", "."]
    style_res = run(cmd)

    cmd = ["pylint", f"--rcfile={project.pylintrc}", module]
    pylint_res = run(cmd)

    cmd = [
        "mypy",
        "--no-incremental",
        "--ignore-missing-imports",
        "--warn-unreachable",
        "--check-untyped-defs",
        module,
    ]
    mypy_res = run(cmd)

    ret_code = 0
    if style_res.returncode != 0:
        click.echo(f"== style check failed with code {style_res.returncode} ==")
        click.echo(style_res.output)
        ret_code = ret_code | 1

    if pylint_res.returncode != 0:
        click.echo(f"== pylint failed with code {pylint_res.returncode} ==")
        click.echo(pylint_res.output)
        ret_code = ret_code | 2

    if mypy_res.returncode != 0:
        click.echo(f"== mypy failed with code {mypy_res.returncode} ==")
        click.echo(mypy_res.output)
        ret_code = ret_code | 4

    return ret_code


@click.group()
def main(args=None):
    """Console script for cpa."""

    return 0


class CommandResult(typing.NamedTuple):
    output: str
    returncode: int


def run(cmd, capture=True) -> CommandResult:
    cmd = ["pipenv", "run"] + cmd

    if capture:
        proc = subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        assert proc.stdout is not None  # makes mypy happy
        return CommandResult(proc.stdout.read().decode("utf-8"), proc.wait())
    else:
        proc = subprocess.Popen(cmd)
        return CommandResult("", proc.wait())


@main.command()
def new():
    """create new project"""
    raise NotImplementedError()


@main.command()
def update():
    """update current project"""
    raise NotImplementedError()


@main.command()
def dist():
    """create distributables"""
    project = Project.find()

    # TODO ensure project is CLEAN
    _dist(project)


def _dist(project):
    test_result_code = run_tests(project)
    if test_result_code != 0:
        click.secho("Not creating dist due to failing tests", fg="red")
        sys.exit(test_result_code)

    os.chdir(project.path)
    if os.path.exists("dist"):
        shutil.rmtree("dist")

    click.echo(run(["python", "setup.py", "sdist"]).output)
    click.echo(run(["python", "setup.py", "bdist_wheel"]).output)


@main.command()
def publish():
    """publish to pypi"""
    project = Project.find()

    if not project.metadata().get("public", False):
        click.secho("Project not public.  Not uploading to pypi", fg="red")
        sys.exit(1)

    click.secho("Creating distribution")
    _dist(project)
    click.secho("Uploading")
    cmd = ["twine", "upload"] + ["dist/" + name for name in os.listdir("dist")]
    run(cmd, capture=False)


@main.command()
def test() -> None:
    """run tests"""
    project = Project.find()
    ret_code = run_tests(project)
    sys.exit(ret_code)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
