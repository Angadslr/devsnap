from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Set

IGNORE_DIRS = {
    ".git",
    ".devsnap",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".expo",
    ".turbo",
}

JS_TS_ENV_REGEX = re.compile(
    r"""process\.env\.(?P<key1>[A-Za-z0-9_]+)|process\.env\[['"](?P<key2>[A-Za-z0-9_]+)['"]\]"""
)


class PythonEnvVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.env_keys: Set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        # Handles os.getenv('KEY'), os.environ.get('KEY'), environ.get('KEY')
        func = node.func
        if isinstance(func, ast.Attribute):
            attr_name = func.attr
            if attr_name == "getenv" and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    self.env_keys.add(arg0.value)
            elif attr_name == "get" and node.args:
                val = func.value
                if isinstance(val, ast.Attribute) and val.attr == "environ":
                    arg0 = node.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                        self.env_keys.add(arg0.value)
                elif isinstance(val, ast.Name) and val.id == "environ":
                    arg0 = node.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                        self.env_keys.add(arg0.value)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        # Handles os.environ['KEY'], environ['KEY']
        val = node.value
        slice_node = node.slice
        is_environ = False
        if isinstance(val, ast.Attribute) and val.attr == "environ":
            is_environ = True
        elif isinstance(val, ast.Name) and val.id == "environ":
            is_environ = True

        if is_environ:
            if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                self.env_keys.add(slice_node.value)
        self.generic_visit(node)


def scan_python_code(code_str: str) -> Set[str]:
    try:
        tree = ast.parse(code_str)
        visitor = PythonEnvVisitor()
        visitor.visit(tree)
        return visitor.env_keys
    except SyntaxError:
        return set()


def scan_js_ts_code(code_str: str) -> Set[str]:
    keys: Set[str] = set()
    for match in JS_TS_ENV_REGEX.finditer(code_str):
        k = match.group("key1") or match.group("key2")
        if k:
            keys.add(k)
    return keys


def scan_repository_env_vars(repo_root: Path) -> Set[str]:
    all_keys: Set[str] = set()

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        suffix = path.suffix.lower()
        if suffix == ".py":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                all_keys.update(scan_python_code(content))
            except Exception:
                pass
        elif suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                all_keys.update(scan_js_ts_code(content))
            except Exception:
                pass

    return all_keys
