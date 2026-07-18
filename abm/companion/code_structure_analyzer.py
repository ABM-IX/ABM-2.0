"""
abm/companion/code_structure_analyzer.py
=========================================
General-purpose code structure analyzer for Phase v0.2.

This module builds on the v0.1 Stream A chunking contract without modifying
the v0.1 chunker. It parses code into structural nodes and derives formatting
and architecture signals that the style fingerprint engine can consume.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from abm.memory.chunking import chunk_stream_a_code_topologies


SUPPORTED_STRUCTURE_LANGUAGES: frozenset[str] = frozenset({"dart", "kotlin", "python"})


@dataclass
class CodeStructureNode:
    """A structural unit found in source code."""

    kind: str
    name: str
    start_line: int
    end_line: int
    text: str
    identifiers: list[str] = field(default_factory=list)


@dataclass
class CodeStructureAnalysis:
    """Complete structural analysis for one code block."""

    language: str
    chunks: list[str]
    nodes: list[CodeStructureNode]
    identifiers: list[str]
    imports: list[str]
    formatting_patterns: dict[str, Any]
    architectural_preferences: dict[str, Any]


class CodeStructureAnalyzer:
    """
    Parse code into reusable structure, formatting, and architecture signals.

    The analyzer supports the same Stream A language names used throughout the
    repo: ``"dart"``, ``"kotlin"``, and ``"python"``.
    """

    def analyze(self, code: str, language: str) -> CodeStructureAnalysis:
        """
        Analyse source code and return a ``CodeStructureAnalysis``.
        """
        if language not in SUPPORTED_STRUCTURE_LANGUAGES:
            raise ValueError("language must be one of: dart, kotlin, python")
        if not code or not code.strip():
            raise ValueError("code must be non-empty")

        chunks = chunk_stream_a_code_topologies(code, language)
        if language == "python":
            nodes, identifiers, imports = self._analyze_python(code)
        else:
            nodes, identifiers, imports = self._analyze_brace_language(code)

        formatting_patterns = self._formatting_patterns(code)
        architectural_preferences = self._architectural_preferences(
            code=code,
            language=language,
            identifiers=identifiers,
            imports=imports,
            nodes=nodes,
        )

        return CodeStructureAnalysis(
            language=language,
            chunks=chunks,
            nodes=nodes,
            identifiers=identifiers,
            imports=imports,
            formatting_patterns=formatting_patterns,
            architectural_preferences=architectural_preferences,
        )

    def _analyze_python(
        self,
        code: str,
    ) -> tuple[list[CodeStructureNode], list[str], list[str]]:
        lines = code.splitlines()
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return self._analyze_brace_language(code)

        nodes: list[CodeStructureNode] = []
        identifiers: list[str] = []
        imports: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.extend(self._python_import_names(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
                identifiers.append(name)
                node_identifiers = self._python_node_identifiers(node)
                identifiers.extend(node_identifiers)
                start = self._node_start_lineno(node)
                end = getattr(node, "end_lineno", None) or start
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                nodes.append(
                    CodeStructureNode(
                        kind=kind,
                        name=name,
                        start_line=start,
                        end_line=end,
                        text="\n".join(lines[start - 1 : end]),
                        identifiers=sorted(set(node_identifiers)),
                    )
                )
            elif isinstance(node, ast.Name):
                identifiers.append(node.id)
            elif isinstance(node, ast.arg):
                identifiers.append(node.arg)

        return nodes, identifiers, sorted(set(imports))

    def _analyze_brace_language(
        self,
        code: str,
    ) -> tuple[list[CodeStructureNode], list[str], list[str]]:
        lines = code.splitlines()
        identifiers = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", code)
        imports = self._brace_imports(code)
        nodes: list[CodeStructureNode] = []

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            class_match = re.search(
                r"\b(class|interface|enum|mixin)\s+([A-Za-z_][A-Za-z0-9_]*)",
                stripped,
            )
            function_match = re.search(
                r"\b(?:fun|void|Future<[^>]+>|[A-Za-z_][A-Za-z0-9_<>, ?]*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
                stripped,
            )
            if class_match:
                kind = class_match.group(1)
                name = class_match.group(2)
            elif function_match and not stripped.startswith(("if", "for", "while", "switch")):
                kind = "function"
                name = function_match.group(1)
            else:
                continue
            end = self._brace_node_end_line(lines, index)
            text = "\n".join(lines[index - 1 : end])
            nodes.append(
                CodeStructureNode(
                    kind=kind,
                    name=name,
                    start_line=index,
                    end_line=end,
                    text=text,
                    identifiers=sorted(set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", text))),
                )
            )

        return nodes, identifiers, imports

    @staticmethod
    def _python_import_names(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Import):
            return [alias.name for alias in node.names]
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            return [module] if module else []
        return []

    @staticmethod
    def _python_node_identifiers(node: ast.AST) -> list[str]:
        identifiers: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                identifiers.append(child.id)
            elif isinstance(child, ast.arg):
                identifiers.append(child.arg)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                identifiers.append(child.name)
        return identifiers

    @staticmethod
    def _node_start_lineno(node: ast.AST) -> int:
        decorator_lines = [
            decorator.lineno
            for decorator in getattr(node, "decorator_list", [])
            if hasattr(decorator, "lineno")
        ]
        node_lineno = getattr(node, "lineno", 1)
        return min([node_lineno, *decorator_lines])

    @staticmethod
    def _brace_imports(code: str) -> list[str]:
        imports: list[str] = []
        for match in re.finditer(r"^\s*import\s+['\"]?([^'\";]+)['\"]?;?", code, re.MULTILINE):
            imports.append(match.group(1).strip())
        return sorted(set(imports))

    @staticmethod
    def _brace_node_end_line(lines: list[str], start_line: int) -> int:
        brace_depth = 0
        saw_open = False
        for index in range(start_line - 1, len(lines)):
            line = lines[index]
            brace_depth += line.count("{") - line.count("}")
            saw_open = saw_open or "{" in line
            if saw_open and brace_depth <= 0:
                return index + 1
        return start_line

    @staticmethod
    def _formatting_patterns(code: str) -> dict[str, Any]:
        lines = code.splitlines()
        non_empty = [line for line in lines if line.strip()]
        indent_widths = [
            len(match.group(1).replace("\t", "    "))
            for line in non_empty
            if (match := re.match(r"^(\s+)\S", line))
        ]
        positive = [width for width in indent_widths if width > 0]
        indent_unit = Counter(positive).most_common(1)[0][0] if positive else 0
        return {
            "indent_style": "tabs" if any(line.startswith("\t") for line in non_empty) else "spaces",
            "indent_unit": indent_unit,
            "trailing_commas": code.count(",\n") + code.count(",\r\n"),
            "semicolon_count": code.count(";"),
            "average_line_length": round(sum(len(line) for line in non_empty) / len(non_empty), 2)
            if non_empty
            else 0.0,
            "max_line_length": max((len(line) for line in non_empty), default=0),
            "blank_line_ratio": round((len(lines) - len(non_empty)) / len(lines), 3)
            if lines
            else 0.0,
        }

    @staticmethod
    def _architectural_preferences(
        *,
        code: str,
        language: str,
        identifiers: list[str],
        imports: list[str],
        nodes: list[CodeStructureNode],
    ) -> dict[str, Any]:
        lower_code = code.lower()
        lower_imports = " ".join(imports).lower()
        identifier_text = " ".join(identifiers).lower()
        class_names = [node.name for node in nodes if node.kind in {"class", "interface", "mixin"}]
        return {
            "uses_flutter": "flutter" in lower_code or "flutter" in lower_imports,
            "uses_bloc": "bloc" in lower_code or "cubit" in lower_code,
            "bloc_class_count": sum(1 for name in class_names if name.endswith(("Bloc", "Cubit"))),
            "state_class_count": sum(1 for name in class_names if name.endswith("State")),
            "event_class_count": sum(1 for name in class_names if name.endswith("Event")),
            "repository_pattern": "repository" in identifier_text,
            "service_pattern": "service" in identifier_text,
            "async_preference": any(token in lower_code for token in ("async", "await", "future<", "suspend ")),
            "language": language,
        }


def analyze_code_structure(code: str, language: str) -> CodeStructureAnalysis:
    """Convenience wrapper around ``CodeStructureAnalyzer().analyze(...)``."""
    return CodeStructureAnalyzer().analyze(code, language)


__all__ = [
    "SUPPORTED_STRUCTURE_LANGUAGES",
    "CodeStructureNode",
    "CodeStructureAnalysis",
    "CodeStructureAnalyzer",
    "analyze_code_structure",
]
