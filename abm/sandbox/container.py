"""
abm/sandbox/container.py
========================
Ephemeral Docker Sandbox controller.
Safely spins up an isolated container, executes code, and guarantees teardown.
"""

import io
import tarfile
import time
from typing import Any

try:
    import docker
    from docker.errors import DockerException
except ModuleNotFoundError:
    class DockerException(Exception):
        """Raised when Docker access is unavailable."""

    class _MissingDockerModule:
        @staticmethod
        def from_env() -> None:
            raise DockerException(
                "Docker SDK is not installed. Install docker>=7.0.0 to run live sandboxes."
            )

    docker = _MissingDockerModule()

from abm.sandbox.models import ExecutionResult


class DockerSandbox:
    """
    Context manager that guarantees the creation and complete destruction
    of an ephemeral Docker container for isolated task execution.
    """

    def __init__(self, image: str = "python:3.11-slim", timeout_seconds: int = 60) -> None:
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.client: Any = None
        self.container: Any = None

    def __enter__(self) -> "DockerSandbox":
        try:
            self.client = docker.from_env()
        except DockerException as e:
            raise RuntimeError(f"Failed to connect to Docker daemon: {e}")

        # Start container in detached mode, keeping it alive
        self.container = self.client.containers.run(
            self.image,
            command="tail -f /dev/null",  # Keeps the container running
            detach=True,
            network_mode="none",  # Maximum isolation
            mem_limit="512m",  # Restrict memory
            cpu_quota=50000,  # Restrict CPU
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.container:
            try:
                self.container.stop(timeout=1)
            except Exception:
                pass
            try:
                self.container.remove(force=True)
            except Exception:
                pass
        if self.client:
            self.client.close()

    def write_file(self, container_path: str, content: str) -> None:
        """
        Securely writes a file to the container by injecting a tar archive.
        The docker SDK put_archive takes a tar stream.
        """
        if not self.container:
            raise RuntimeError("Sandbox container is not running.")

        # Create an in-memory tar file containing the single file
        file_name = container_path.split("/")[-1]
        dest_dir = "/".join(container_path.split("/")[:-1])
        if not dest_dir:
            dest_dir = "/"

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            content_bytes = content.encode("utf-8")
            tarinfo = tarfile.TarInfo(name=file_name)
            tarinfo.size = len(content_bytes)
            tar.addfile(tarinfo, io.BytesIO(content_bytes))

        tar_stream.seek(0)
        self.container.put_archive(dest_dir, tar_stream)

    def execute_command(self, command: str | list[str]) -> ExecutionResult:
        """
        Runs a command inside the container and returns the execution result.
        Enforces a timeout via simple polling.
        """
        if not self.container:
            raise RuntimeError("Sandbox container is not running.")

        start_time = time.monotonic()
        
        # Exec run in detached mode to allow timeout tracking
        exec_id = self.client.api.exec_create(
            self.container.id, 
            cmd=command, 
            stdout=True, 
            stderr=True
        )["Id"]
        
        output_stream = self.client.api.exec_start(exec_id, stream=True)
        
        stdout_data = []
        # In a real async environment we'd use asyncio, but sticking to simple sync
        # with a timeout check. The docker-py stream is a generator.
        
        # Wait for completion or timeout
        while True:
            exec_inspect = self.client.api.exec_inspect(exec_id)
            if not exec_inspect["Running"]:
                break
                
            elapsed = time.monotonic() - start_time
            if elapsed > self.timeout_seconds:
                raise TimeoutError(f"Command execution exceeded {self.timeout_seconds} seconds")
            time.sleep(0.1)

        # Collect output
        output_bytes = b"".join(output_stream)
        
        # We cannot easily distinguish stdout vs stderr with exec_start output stream 
        # unless demux=True is supported and we use it. We'll simplify and put all in stdout
        # if demux is false, but docker SDK can return a tuple if demux is requested.
        try:
            # Let's just grab the whole output
            stdout_str = output_bytes.decode("utf-8", errors="replace")
        except Exception:
            stdout_str = ""

        exec_inspect = self.client.api.exec_inspect(exec_id)
        exit_code = exec_inspect.get("ExitCode", -1)
        execution_time_ms = int((time.monotonic() - start_time) * 1000)

        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout_str,
            stderr="",  # Simplified: all output in stdout
            execution_time_ms=execution_time_ms,
        )
