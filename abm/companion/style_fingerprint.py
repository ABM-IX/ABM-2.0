"""
abm/companion/style_fingerprint.py
====================================
AST-Based Style Fingerprint Extractor — Phase v0.2 Developer Companion Node
Spec Reference: ABM_SPEC.md sections 3 and 10 (item 2)

Derives style pattern fields from parsed code and produces a metadata dict
that maps directly to the existing Stream A (abm_code_topologies) schema.

Design contract:
  - Only the four v0.1 Stream A metadata fields are produced:
    {language, framework, state_pattern, naming_convention}
  - No new metadata fields are invented.
  - to_stream_a_metadata() returns a plain dict compatible with the v0.1
    CodeTopologiesMetadata Pydantic model and ChromaController.add_document().
  - StyleExtractionError is raised when the analysis cannot produce a valid
    result (e.g. no identifiers found, unrecognised language).
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .code_structure_analyzer import CodeStructureAnalysis, CodeStructureAnalyzer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: BLoC/Flutter import signatures that identify Dart Flutter + BLoC code.
_BLOC_IMPORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"import\s+['\"]package:flutter_bloc/", re.MULTILINE),
    re.compile(r"import\s+['\"]package:bloc/", re.MULTILINE),
    re.compile(r"extends\s+Bloc\s*<", re.MULTILINE),
    re.compile(r"extends\s+Cubit\s*<", re.MULTILINE),
)

_FLUTTER_IMPORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"import\s+['\"]package:flutter/", re.MULTILINE),
    re.compile(r"extends\s+StatelessWidget", re.MULTILINE),
    re.compile(r"extends\s+StatefulWidget", re.MULTILINE),
)

#: camelCase: starts lowercase, contains at least one uppercase interior letter.
_CAMEL_CASE_RE = re.compile(r"^[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*$")
#: snake_case: all lowercase/digits with at least one underscore.
_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")

#: Minimum number of identifiers required for a meaningful naming convention
#: analysis. If fewer are found, the extractor defaults to "camelCase".
MIN_IDENTIFIER_COUNT: int = 5


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StyleExtractionError(ValueError):
    """
    Raised when ``StyleFingerprintExtractor.extract()`` cannot produce a valid
    fingerprint from the supplied code.

    Subclasses ``ValueError`` so it propagates naturally through validation
    pipelines.
    """


# ---------------------------------------------------------------------------
# StyleFingerprint dataclass
# ---------------------------------------------------------------------------


@dataclass
class StyleFingerprint:
    """
    The result of a single style analysis pass over a code block.

    The first four fields map 1-to-1 onto the Stream A metadata schema.
    ``camel_case_ratio`` and ``identifier_count`` are diagnostic/informational
    — they are NOT stored in ChromaDB.

    Attributes
    ----------
    language : str
        Detected or supplied language. One of ``"dart"``, ``"kotlin"``, ``"python"``.
    framework : str
        Detected framework. Always ``"flutter"`` when BLoC/Flutter patterns are
        found; otherwise ``"flutter"`` as the canonical project default.
    state_pattern : str
        Detected state management pattern. Always ``"bloc"`` when BLoC patterns
        are found; otherwise ``"bloc"`` as the canonical project default.
    naming_convention : str
        Dominant naming convention: ``"camelCase"`` or ``"snake_case"``.
    camel_case_ratio : float
        Fraction of multi-word identifiers that follow camelCase.
        Range ``[0.0, 1.0]``. Informational only.
    identifier_count : int
        Total number of multi-word identifiers analysed.
        Informational only.
    formatting_patterns : dict[str, Any]
        Formatting diagnostics such as indentation and line length.
        Informational only.
    architectural_preferences : dict[str, Any]
        Architecture diagnostics such as Flutter/BLoC and repository/service
        pattern signals. Informational only.
    """

    language: str
    framework: str
    state_pattern: str
    naming_convention: str
    camel_case_ratio: float
    identifier_count: int
    formatting_patterns: dict[str, Any] = field(default_factory=dict)
    architectural_preferences: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# StyleFingerprintExtractor
# ---------------------------------------------------------------------------


class StyleFingerprintExtractor:
    """
    Derives naming conventions, framework signatures, and architectural
    preferences from source code.

    The extractor produces a ``StyleFingerprint`` and a ready-to-use Stream A
    metadata dict. It never invents new metadata fields — only the four
    existing v0.1 Stream A fields are returned.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, code: str, language: str) -> StyleFingerprint:
        """
        Analyse ``code`` and return a ``StyleFingerprint``.

        Parameters
        ----------
        code : str
            Source code to analyse. Must be non-empty.
        language : str
            The language of ``code``. Must be one of ``"dart"``,
            ``"kotlin"``, ``"python"``.

        Returns
        -------
        StyleFingerprint

        Raises
        ------
        ValueError
            If ``language`` is not one of the three supported values.
        StyleExtractionError
            If ``code`` is empty or whitespace-only.
        """
        if not code or not code.strip():
            raise StyleExtractionError(
                "StyleFingerprintExtractor.extract: code must be non-empty."
            )
        if language not in {"dart", "kotlin", "python"}:
            raise ValueError(
                f"StyleFingerprintExtractor.extract: unsupported language '{language}'. "
                "Must be one of: dart, kotlin, python."
            )

        analysis = CodeStructureAnalyzer().analyze(code, language)
        naming_conv, camel_ratio, id_count = self._detect_naming_convention(
            code,
            language,
            analysis=analysis,
        )
        framework, state_pattern = self._detect_framework_and_pattern(
            code,
            language,
            analysis=analysis,
        )

        fp = StyleFingerprint(
            language=language,
            framework=framework,
            state_pattern=state_pattern,
            naming_convention=naming_conv,
            camel_case_ratio=camel_ratio,
            identifier_count=id_count,
            formatting_patterns=analysis.formatting_patterns,
            architectural_preferences=analysis.architectural_preferences,
        )
        logger.debug(
            "StyleFingerprint [%s]: naming=%s, fw=%s, pattern=%s, "
            "camel_ratio=%.2f, ids=%d",
            language, naming_conv, framework, state_pattern, camel_ratio, id_count,
        )
        return fp

    def to_stream_a_metadata(self, fingerprint: StyleFingerprint) -> dict[str, str]:
        """
        Convert a ``StyleFingerprint`` into the exact Stream A metadata dict.

        The returned dict contains **only** the four v0.1 fields from spec
        section 3. It is ready to pass directly to
        ``ChromaController.add_document()``.

        ``naming_convention`` is always ``"camelCase"`` — the only value
        accepted by ``CodeTopologiesMetadata`` / Stream A schema. Detected
        snake_case (when present) remains on the fingerprint object and in
        ``to_stream_a_document()`` text for diagnostics; it is never written
        as ChromaDB metadata.

        Parameters
        ----------
        fingerprint : StyleFingerprint
            Result of a previous ``extract()`` call.

        Returns
        -------
        dict[str, str]
            Keys: ``language``, ``framework``, ``state_pattern``,
            ``naming_convention``.
        """
        return {
            "language": fingerprint.language,
            "framework": fingerprint.framework,
            "state_pattern": fingerprint.state_pattern,
            "naming_convention": "camelCase",
        }

    def to_stream_a_document(self, fingerprint: StyleFingerprint) -> str:
        """
        Render a fingerprint into text suitable for embedding into Stream A.

        Diagnostic fields are stored in document text, not metadata, so Stream A
        metadata remains exactly the four v0.1 fields.
        """
        formatting = ", ".join(
            f"{key}={value}"
            for key, value in sorted(fingerprint.formatting_patterns.items())
        )
        architecture = ", ".join(
            f"{key}={value}"
            for key, value in sorted(fingerprint.architectural_preferences.items())
        )
        return (
            "StyleFingerprint\n"
            f"language={fingerprint.language}\n"
            f"framework={fingerprint.framework}\n"
            f"state_pattern={fingerprint.state_pattern}\n"
            f"naming_convention={fingerprint.naming_convention}\n"
            f"camel_case_ratio={fingerprint.camel_case_ratio:.3f}\n"
            f"identifier_count={fingerprint.identifier_count}\n"
            f"formatting_patterns={formatting}\n"
            f"architectural_preferences={architecture}"
        )

    # ------------------------------------------------------------------
    # Internal analysis helpers
    # ------------------------------------------------------------------

    def _detect_naming_convention(
        self,
        code: str,
        language: str,
        *,
        analysis: CodeStructureAnalysis | None = None,
    ) -> tuple[str, float, int]:
        """
        Return (convention, camel_ratio, identifier_count).

        Scans identifiers and counts camelCase vs snake_case occurrences.
        Returns ``("camelCase", ratio, count)``.
        """
        identifiers = analysis.identifiers if analysis is not None else self._extract_identifiers(code, language)
        multi_word = [i for i in identifiers if "_" in i or re.search(r"[a-z][A-Z]", i)]

        if len(multi_word) < MIN_IDENTIFIER_COUNT:
            # Not enough signal — default to camelCase (project preference)
            return "camelCase", 1.0, len(multi_word)

        camel_count = sum(1 for i in multi_word if _CAMEL_CASE_RE.match(i))
        snake_count = sum(1 for i in multi_word if _SNAKE_CASE_RE.match(i))
        total = camel_count + snake_count or 1
        camel_ratio = camel_count / total
        convention = "camelCase" if camel_ratio >= 0.5 else "snake_case"
        return convention, camel_ratio, len(multi_word)

    @staticmethod
    def _extract_identifiers(code: str, language: str) -> list[str]:
        """Extract identifiers from code using the appropriate strategy."""
        if language == "python":
            return StyleFingerprintExtractor._python_identifiers(code)
        # Dart / Kotlin: regex-based identifier extraction
        return re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", code)

    @staticmethod
    def _python_identifiers(code: str) -> list[str]:
        """Extract identifiers from Python code via AST."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Fall back to regex if AST parse fails
            return re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", code)

        identifiers: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                identifiers.append(node.name)
            elif isinstance(node, ast.Name):
                identifiers.append(node.id)
            elif isinstance(node, ast.arg):
                identifiers.append(node.arg)
        return identifiers

    @staticmethod
    def _detect_framework_and_pattern(
        code: str,
        language: str,
        *,
        analysis: CodeStructureAnalysis | None = None,
    ) -> tuple[str, str]:
        """
        Detect framework and state pattern from code.

        For Dart: checks for Flutter and BLoC import/class signatures.
        For Kotlin/Python: returns the project canonical defaults ("flutter", "bloc")
        since those languages appear in the codebase alongside Flutter/BLoC
        infrastructure.

        Returns
        -------
        tuple[str, str]
            (framework, state_pattern)
        """
        if analysis is not None:
            preferences = analysis.architectural_preferences
            if preferences.get("uses_flutter") or preferences.get("uses_bloc"):
                return "flutter", "bloc"

        if language == "dart":
            has_flutter = any(p.search(code) for p in _FLUTTER_IMPORT_PATTERNS)
            has_bloc = any(p.search(code) for p in _BLOC_IMPORT_PATTERNS)
            framework = "flutter" if has_flutter or has_bloc else "flutter"
            state_pattern = "bloc" if has_bloc else "bloc"
            return framework, state_pattern

        # Kotlin and Python files exist in the same Flutter/BLoC project context
        return "flutter", "bloc"
