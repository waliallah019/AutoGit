"""AST-first change parsing for Python and JS/TS files."""

from __future__ import annotations

import ast
import hashlib
import os
import re
from dataclasses import dataclass, field


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass
class ParsedChange:
    file_path: str
    language: str
    modified_lines: list[int] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    summary_seed: str = ""


class _PyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: set[str] = set()
        self.functions: set[str] = set()
        self.classes: set[str] = set()
        self.calls: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for n in node.names:
            self.imports.add(n.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.add(node.module)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.functions.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.add(node.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name:
            self.calls.add(name)
        self.generic_visit(node)


class ASTChangeParser:
    """Extracts changed entities from git diff and file ASTs."""

    def __init__(self) -> None:
        self._tree_sitter_parser = None
        self._tree_sitter_language = None
        self._init_tree_sitter()

    def _init_tree_sitter(self) -> None:
        try:
            from tree_sitter import Parser
            from tree_sitter_languages import get_language

            self._tree_sitter_parser = Parser()
            # We use JavaScript grammar for JS/TS fallback; TS support depends on installed package.
            self._tree_sitter_language = get_language("javascript")
            self._tree_sitter_parser.set_language(self._tree_sitter_language)
        except Exception:
            self._tree_sitter_parser = None
            self._tree_sitter_language = None

    @staticmethod
    def _language_for(path: str) -> str:
        ext = os.path.splitext(path.lower())[1]
        if ext == ".py":
            return "python"
        if ext in {".js", ".jsx", ".ts", ".tsx"}:
            return "javascript"
        return "other"

    @staticmethod
    def _parse_modified_lines(file_patch: str) -> list[int]:
        modified: set[int] = set()
        current_line = 0
        for raw in file_patch.splitlines():
            hunk_match = _HUNK_RE.match(raw)
            if hunk_match:
                current_line = int(hunk_match.group(1))
                continue
            if raw.startswith("+") and not raw.startswith("+++"):
                modified.add(current_line)
                current_line += 1
            elif raw.startswith("-") and not raw.startswith("---"):
                # line removed from old file; current_line not incremented in new file view
                continue
            else:
                current_line += 1
        return sorted(modified)

    @staticmethod
    def split_diff_by_file(diff_text: str) -> dict[str, str]:
        files: dict[str, list[str]] = {}
        current: str | None = None
        for line in diff_text.splitlines():
            if line.startswith("diff --git "):
                m = re.search(r" b/(.+)$", line)
                current = m.group(1) if m else None
                if current:
                    files.setdefault(current, [])
                continue
            if current:
                files[current].append(line)
        return {k: "\n".join(v) for k, v in files.items()}

    def parse(self, repo_root: str, file_path: str, file_patch: str) -> ParsedChange:
        language = self._language_for(file_path)
        modified_lines = self._parse_modified_lines(file_patch)
        abs_path = os.path.join(repo_root, file_path)
        if not os.path.exists(abs_path):
            return ParsedChange(file_path=file_path, language=language, modified_lines=modified_lines)

        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()

        if language == "python":
            return self._parse_python(file_path, source, modified_lines)
        if language == "javascript":
            return self._parse_javascript(file_path, source, modified_lines)
        return ParsedChange(file_path=file_path, language=language, modified_lines=modified_lines)

    def _parse_python(self, file_path: str, source: str, modified_lines: list[int]) -> ParsedChange:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return ParsedChange(file_path=file_path, language="python", modified_lines=modified_lines)

        visitor = _PyVisitor()
        visitor.visit(tree)
        summary_seed = self._summary_seed(
            file_path=file_path,
            functions=sorted(visitor.functions),
            classes=sorted(visitor.classes),
            imports=sorted(visitor.imports),
        )
        return ParsedChange(
            file_path=file_path,
            language="python",
            modified_lines=modified_lines,
            imports=sorted(visitor.imports),
            functions=sorted(visitor.functions),
            classes=sorted(visitor.classes),
            calls=sorted(visitor.calls),
            dependencies=sorted(visitor.imports),
            summary_seed=summary_seed,
        )

    def _parse_javascript(self, file_path: str, source: str, modified_lines: list[int]) -> ParsedChange:
        if not self._tree_sitter_parser:
            return ParsedChange(file_path=file_path, language="javascript", modified_lines=modified_lines)

        tree = self._tree_sitter_parser.parse(source.encode("utf-8", errors="ignore"))
        root = tree.root_node

        imports: set[str] = set()
        functions: set[str] = set()
        classes: set[str] = set()
        calls: set[str] = set()

        stack = [root]
        while stack:
            node = stack.pop()
            node_type = node.type
            if node_type == "import_statement":
                text = source[node.start_byte : node.end_byte]
                imports.add(text.strip())
            elif node_type in {"function_declaration", "method_definition"}:
                name_node = node.child_by_field_name("name")
                if name_node:
                    functions.add(source[name_node.start_byte : name_node.end_byte])
            elif node_type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    classes.add(source[name_node.start_byte : name_node.end_byte])
            elif node_type == "call_expression":
                fn_node = node.child_by_field_name("function")
                if fn_node:
                    calls.add(source[fn_node.start_byte : fn_node.end_byte][:80])
            stack.extend(node.children)

        summary_seed = self._summary_seed(
            file_path=file_path,
            functions=sorted(functions),
            classes=sorted(classes),
            imports=sorted(imports),
        )
        return ParsedChange(
            file_path=file_path,
            language="javascript",
            modified_lines=modified_lines,
            imports=sorted(imports),
            functions=sorted(functions),
            classes=sorted(classes),
            calls=sorted(calls),
            dependencies=sorted(imports),
            summary_seed=summary_seed,
        )

    @staticmethod
    def _summary_seed(file_path: str, functions: list[str], classes: list[str], imports: list[str]) -> str:
        digest = hashlib.sha1(f"{file_path}|{functions}|{classes}|{imports}".encode("utf-8")).hexdigest()[:12]
        return f"{file_path}:{digest}"

