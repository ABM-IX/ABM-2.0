"""
abm/sandbox/execution_loop.py
=============================
Compiler/test check loop injection.
Uses the DockerSandbox to validate generated code against tests or compilers.
"""

from typing import Callable

from abm.sandbox.container import DockerSandbox
from abm.sandbox.models import ExecutionResult


class SandboxCheckLoop:
    """
    Injects code files into an ephemeral sandbox, executes a build/test
    command, and returns the result.
    """

    def __init__(self, sandbox_factory: Callable[[], DockerSandbox]) -> None:
        self.sandbox_factory = sandbox_factory

    def evaluate_code(
        self, code_files: dict[str, str], test_command: str | list[str]
    ) -> ExecutionResult:
        """
        Runs the test_command in a sandbox populated with code_files.

        :param code_files: Dictionary mapping container path -> file content.
                           e.g., {"/app/main.py": "print('hello')"}
        :param test_command: Command to execute, e.g., "python /app/main.py"
        """
        with self.sandbox_factory() as sandbox:
            # Inject all files
            for path, content in code_files.items():
                sandbox.write_file(path, content)

            # Execute the validation loop
            result = sandbox.execute_command(test_command)
            return result
