"""Shared helper for the tests: find code that names the answer labels.

Detection and classifier modules must never read the answer labels. This looks
at a module's identifiers and string literals (not its docstrings or comments,
which may explain the rule) for any of the forbidden names.
"""

from __future__ import annotations

import ast

FORBIDDEN_NAMES = ("ground_truth", "gt_borrowers", "gt_messages", "gt_lenders", "profile_type")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                found.add(id(first.value))
    return found


def forbidden_mentions(source: str, names: tuple[str, ...] = FORBIDDEN_NAMES) -> list[str]:
    """Identifiers and string literals (not docstrings or comments) that name the answer labels."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    words: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            words.append(node.id)
        elif isinstance(node, ast.Attribute):
            words.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            words.append(node.name)
        elif isinstance(node, ast.arg):
            words.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            words.append(node.arg)
        elif isinstance(node, ast.alias):
            words.extend(part for part in (node.name, node.asname) if part)
        elif isinstance(node, ast.ImportFrom) and node.module:
            words.append(node.module)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            words.append(node.value)
    return [w for w in words if any(name in w.lower() for name in names)]


def string_literals(source: str) -> list[str]:
    """Every string literal in the code, except docstrings (comments are never part of the tree)."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


def names_used(source: str) -> set[str]:
    """Every plain name, attribute and imported name used in the code."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.asname or node.name)
    return found
