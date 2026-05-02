from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
IMAGE_NAME = os.getenv("SANDBOX_IMAGE", "freebbs-sandbox-runner:latest")
MAX_TIMEOUT_SECONDS = int(os.getenv("SANDBOX_MAX_TIMEOUT", "30"))
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("SANDBOX_DEFAULT_TIMEOUT", "10"))
DOCKER_RUN_TIMEOUT_GRACE_SECONDS = 3
MAX_CODE_BYTES = int(os.getenv("SANDBOX_MAX_CODE_BYTES", str(256 * 1024)))
UID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class RunRequest(BaseModel):
    language: Literal["python", "c", "cpp", "c++"]
    code: str = Field(min_length=1)
    uid: str = Field(min_length=1, max_length=80)
    timeout: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1, le=MAX_TIMEOUT_SECONDS)

    @field_validator("uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        if not UID_RE.fullmatch(value):
            raise ValueError("uid may only contain letters, numbers, dot, underscore, and dash")
        return value

    @field_validator("code")
    @classmethod
    def validate_code_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_CODE_BYTES:
            raise ValueError(f"code exceeds {MAX_CODE_BYTES} bytes")
        return value

    def normalized_language(self) -> Literal["python", "c", "cpp"]:
        return "cpp" if self.language == "c++" else self.language


class RunResponse(BaseModel):
    stdout: str
    stderr: str
    files: list[str]
    exit_code: int
    timed_out: bool = False


app = FastAPI(title="freeBBS sandbox", version="0.1.0")


@app.middleware("http")
async def localhost_only(request: Request, call_next):
    client = request.client
    if client is None or client.host != "127.0.0.1":
        return JSONResponse(status_code=403, content={"detail": "only 127.0.0.1 clients are allowed"})
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse)
def run_code(payload: RunRequest) -> RunResponse:
    if shutil.which("docker") is None:
        raise HTTPException(status_code=503, detail="docker executable was not found")

    language = payload.normalized_language()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_dir = (OUTPUTS_DIR / payload.uid).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o777)

    job_id = f"sandbox-{int(time.time())}-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="freebbs-sandbox-") as tmpdir:
        workspace = Path(tmpdir).resolve()
        source_name = {"python": "main.py", "c": "main.c", "cpp": "main.cpp"}[language]
        (workspace / source_name).write_text(payload.code, encoding="utf-8")
        workspace.chmod(0o777)
        (workspace / source_name).chmod(0o666)

        command = docker_command(
            container_name=job_id,
            language=language,
            workspace=workspace,
            output_dir=output_dir,
        )

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=payload.timeout + DOCKER_RUN_TIMEOUT_GRACE_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            subprocess.run(["docker", "rm", "-f", job_id], capture_output=True, text=True)
            return RunResponse(
                stdout=coerce_text(exc.stdout),
                stderr=coerce_text(exc.stderr) + f"\nExecution timed out after {payload.timeout} seconds.",
                files=[],
                exit_code=124,
                timed_out=True,
            )

    return parse_runner_result(completed.stdout, completed.stderr, completed.returncode, output_dir)


def docker_command(container_name: str, language: str, workspace: Path, output_dir: Path) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--pids-limit",
        "128",
        "--memory",
        os.getenv("SANDBOX_MEMORY", "2g"),
        "--cpus",
        os.getenv("SANDBOX_CPUS", "2"),
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "-e",
        "MPLBACKEND=Agg",
        "-e",
        "HOME=/tmp",
        "-e",
        "MPLCONFIGDIR=/tmp/matplotlib",
        "-v",
        f"{workspace}:/workspace:rw",
        "-v",
        f"{output_dir}:/outputs:rw",
        IMAGE_NAME,
        "--language",
        language,
        "--output-dir",
        "/outputs",
    ]


def parse_runner_result(stdout: str, stderr: str, returncode: int, output_dir: Path) -> RunResponse:
    marker = "__SANDBOX_RESULT__"
    result_line = None
    visible_stdout_lines: list[str] = []
    for line in stdout.splitlines():
        if line.startswith(marker):
            result_line = line[len(marker) :]
        else:
            visible_stdout_lines.append(line)

    if result_line is None:
        return RunResponse(
            stdout="\n".join(visible_stdout_lines),
            stderr=stderr or "sandbox runner did not return a result payload",
            files=[],
            exit_code=returncode,
        )

    try:
        result = json.loads(result_line)
    except json.JSONDecodeError:
        return RunResponse(
            stdout="\n".join(visible_stdout_lines),
            stderr=stderr or "sandbox runner returned invalid result JSON",
            files=[],
            exit_code=returncode,
        )

    files = []
    for file_path in result.get("files", []):
        path = Path(file_path)
        if path.is_absolute():
            try:
                relative = path.relative_to("/outputs")
                files.append(str(output_dir / relative))
            except ValueError:
                files.append(str(path))
        else:
            files.append(str(output_dir / path))

    runner_stderr = result.get("stderr", "")
    if stderr:
        runner_stderr = f"{runner_stderr}\n{stderr}" if runner_stderr else stderr

    return RunResponse(
        stdout=result.get("stdout", ""),
        stderr=runner_stderr,
        files=files,
        exit_code=int(result.get("exit_code", returncode)),
    )


def coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
