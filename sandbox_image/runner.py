#!/usr/bin/env python3
import argparse
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
from pathlib import Path


WORKSPACE = Path("/workspace")


def timestamp_name(suffix: str) -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}{suffix}"


def list_files(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(item.resolve()) for item in path.rglob("*") if item.is_file()}


def print_result(stdout: str, stderr: str, files: list[str], exit_code: int) -> int:
    payload = {
        "stdout": stdout,
        "stderr": stderr,
        "files": files,
        "exit_code": exit_code,
    }
    print("\n__SANDBOX_RESULT__" + json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


def run_python(output_dir: Path) -> int:
    os.environ["MPLBACKEND"] = "Agg"
    output_dir.mkdir(parents=True, exist_ok=True)
    before = list_files(output_dir)

    stdout_path = WORKSPACE / "stdout.txt"
    stderr_path = WORKSPACE / "stderr.txt"
    exit_code = 0

    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout_file, stderr_file
        try:
            import matplotlib

            matplotlib.use("Agg", force=True)
            runpy.run_path(str(WORKSPACE / "main.py"), run_name="__main__")
            try:
                import matplotlib.pyplot as plt

                for figure_number in plt.get_fignums():
                    figure = plt.figure(figure_number)
                    target = output_dir / timestamp_name(f"-figure-{figure_number}.png")
                    figure.savefig(target, bbox_inches="tight")
                plt.close("all")
            except Exception as exc:  # noqa: BLE001
                print(f"failed to save matplotlib figures: {exc}", file=sys.stderr)
                exit_code = 1
        except SystemExit as exc:
            code = exc.code
            exit_code = code if isinstance(code, int) else 1
        except Exception:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            exit_code = 1
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout, sys.stderr = old_stdout, old_stderr

    after = list_files(output_dir)
    files = sorted(after - before)
    return print_result(
        stdout_path.read_text(encoding="utf-8", errors="replace"),
        stderr_path.read_text(encoding="utf-8", errors="replace"),
        files,
        exit_code,
    )


def run_compiled(language: str, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    source = WORKSPACE / ("main.c" if language == "c" else "main.cpp")
    binary = WORKSPACE / "program"
    compiler = "gcc" if language == "c" else "g++"
    standard = "-std=c11" if language == "c" else "-std=c++17"

    compile_cmd = [compiler, standard, "-O2", "-pipe", str(source), "-lm", "-o", str(binary)]
    if language == "cpp":
        compile_cmd = [compiler, standard, "-O2", "-pipe", str(source), "-o", str(binary)]

    compile_proc = subprocess.run(compile_cmd, capture_output=True, text=True, cwd=WORKSPACE)
    if compile_proc.returncode != 0:
        return print_result(compile_proc.stdout, compile_proc.stderr, [], compile_proc.returncode)

    before = list_files(output_dir)
    run_proc = subprocess.run([str(binary)], capture_output=True, text=True, cwd=WORKSPACE)
    after = list_files(output_dir)
    return print_result(run_proc.stdout, run_proc.stderr, sorted(after - before), run_proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=["python", "c", "cpp"], required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if args.language == "python":
        return run_python(output_dir)
    return run_compiled(args.language, output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
