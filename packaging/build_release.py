"""Build and verify a Windows x64 onedir release in an isolated environment."""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import venv
import zipfile


PACKAGING_DIR = Path(__file__).resolve().parent
ROOT = PACKAGING_DIR.parent


def read_version(source):
    # Read constants without importing Qt or starting the application.
    constants = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("VERSION_MAJOR", "VERSION_MINOR"):
                    value = ast.literal_eval(node.value)
                    if type(value) is not int or value < 0:
                        raise ValueError("Version constants must be nonnegative integers")
                    constants[target.id] = value
    return f"{constants['VERSION_MAJOR']}.{constants['VERSION_MINOR']}"


def run(command, **kwargs):
    print("+", subprocess.list2cmdline([str(part) for part in command]), flush=True)
    return subprocess.run(command, check=True, **kwargs)


def check_dependencies():
    from importlib.metadata import version
    for path in (ROOT / "requirements.txt", PACKAGING_DIR / "requirements-build.txt"):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-r")):
                continue
            name, expected = line.split("==")
            if version(name) != expected:
                raise RuntimeError(f"{name} must be {expected}; rerun without --skip-install")


def git_info():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        return {"commit": commit, "dirty": bool(status), "status": status}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def build(console):
    check_dependencies()
    version = read_version((ROOT / "SerialChart.py").read_text(encoding="utf-8-sig"))
    mode = "console" if console else "windowed"
    work = ROOT / "build" / mode
    dist = ROOT / "dist" / "console" if console else ROOT / "dist"
    # PyInstaller replaces its own onedir output. Reject paths redirected outside this checkout.
    for path in (work, dist, dist / "SerialChart", ROOT / "build" / "pyinstaller-cache"):
        if not path.resolve().is_relative_to(ROOT):
            raise RuntimeError(f"Build output escapes project directory: {path}")
    work.mkdir(parents=True, exist_ok=True)
    dist.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYQTGRAPH_QT_LIB"] = "PyQt5"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SERIALCHART_BUILD_CONSOLE"] = "1" if console else "0"
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build" / "pyinstaller-cache")
    run([sys.executable, "-m", "pip", "check"], cwd=ROOT, env=env)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, env=env)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--workpath", str(work), "--distpath", str(dist), str(PACKAGING_DIR / "SerialChart.spec")], cwd=ROOT, env=env)

    bundle = dist / "SerialChart"
    # Launch from a different working directory to catch resource paths tied to cwd.
    with tempfile.TemporaryDirectory(prefix="serialchart-smoke-") as directory:
        report_path = Path(directory) / "smoke.json"
        result = subprocess.run([str(bundle / "SerialChart.exe"), "--smoke-test", str(report_path)],
                                cwd=directory, env=env, timeout=90)
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        if result.returncode or not report.get("ok") or report.get("version") != version:
            raise RuntimeError(f"Frozen executable smoke test failed: {report}")

    packages = json.loads(subprocess.check_output([sys.executable, "-m", "pip", "list", "--format=json"], text=True))
    manifest = {"version": version, "mode": mode, "built_at_utc": datetime.now(timezone.utc).isoformat(),
                "python": platform.python_version(), "platform": platform.platform(),
                "git": git_info(), "packages": packages, "smoke_test": report}
    (bundle / "BUILD_INFO.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Convenient top-level notices; About uses the same files inside _internal.
    for name in ("LICENSE.txt", "COPYRIGHT.txt", "THIRD_PARTY_NOTICES.md", "SOURCE.md"):
        shutil.copy2(ROOT / name, bundle / name)
    filename = f"SerialChart-v{version}-windows-x64{'-console' if console else ''}.zip"
    archive = dist / filename
    temporary = archive.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as output:
            for file in sorted(bundle.rglob("*")):
                if file.is_file():
                    output.write(file, file.relative_to(dist))
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {filename}\n", encoding="ascii")
    print(f"\nVerified build: {archive}\nSHA256: {digest}", flush=True)
    print("Before publishing: clean-Windows COM testing and version-matched source/license checklist in SOURCE.md.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console", action="store_true", help="Build a separate diagnostic version with a console")
    parser.add_argument("--skip-install", action="store_true", help="Reuse the exact installed dependencies without network access")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 11) or struct.calcsize("P") != 8 or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("Use Windows x64 with 64-bit Python 3.11")
    environment = ROOT / ".venv-build"
    if not environment.resolve().is_relative_to(ROOT):
        raise RuntimeError("Build environment escapes project directory")
    python = environment / "Scripts" / "python.exe"
    if Path(sys.prefix).resolve() != environment.resolve():
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(environment)
        command = [str(python), str(Path(__file__).resolve())]
        if args.console:
            command.append("--console")
        if args.skip_install:
            command.append("--skip-install")
        run(command, cwd=ROOT)
        return
    if not args.skip_install:
        run([sys.executable, "-m", "pip", "install", "-r", str(PACKAGING_DIR / "requirements-build.txt")], cwd=ROOT)
    build(args.console)


if __name__ == "__main__":
    main()
