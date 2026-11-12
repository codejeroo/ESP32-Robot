#!/usr/bin/env python3
"""Export an Onshape assembly and package a Webots PROTO with its assets/controller."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTROLLER_NAME = "rover_drive"
CONTROLLER_SOURCE = ROOT / "controllers" / CONTROLLER_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Webots PROTO and robot name")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json", help="Onshape export config")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "generated",
        help="Parent directory for the named Webots project folder (default: generated/)",
    )
    parser.add_argument("--force", action="store_true", help="Replace the named output folder if it already exists")
    args = parser.parse_args()
    if not NAME_RE.fullmatch(args.name):
        parser.error("--name must be a simple Webots identifier (letters, digits, underscores; not starting with a digit)")
    return args


def set_default_controller(proto: Path) -> None:
    source = proto.read_text(encoding="utf-8")
    source = re.sub(
        r"(?m)^# Extracted from: .+$",
        "# Extracted from: Onshape URDF export",
        source,
        count=1,
    )
    updated, count = re.subn(
        r'(?m)^(\s*field\s+SFString\s+controller\s+)"[^"]*"',
        rf'\1"{CONTROLLER_NAME}"',
        source,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Could not set the default controller in generated PROTO: {proto}")
    proto.write_text(updated, encoding="utf-8")


def replace_package(staged_package: Path, target_package: Path, force: bool, backup_dir: Path) -> None:
    backup_package = backup_dir / "previous-package"
    had_previous = target_package.exists()
    if had_previous and not force:
        raise RuntimeError(f"Output folder already exists: {target_package}. Use --force to replace it.")
    if had_previous:
        target_package.replace(backup_package)
    try:
        staged_package.replace(target_package)
    except Exception:
        if had_previous and backup_package.exists():
            backup_package.replace(target_package)
        raise


def executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        candidate = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin") / name
        if candidate.is_file():
            found = str(candidate)
    if not found:
        raise RuntimeError(f"Required command '{name}' was not found. Install project dependencies; see README.md.")
    return found


def main() -> int:
    args = parse_args()
    config = args.config.expanduser().resolve()
    output_parent = args.output_dir.expanduser().resolve()
    package_dir = output_parent / args.name
    env_file = ROOT / ".env"
    if not config.is_file():
        raise RuntimeError(f"Config file not found: {config}")
    if not env_file.is_file():
        raise RuntimeError(f"Credentials file not found: {env_file}. Copy .env.example to .env and add your Onshape credentials.")
    if not CONTROLLER_SOURCE.is_dir():
        raise RuntimeError(f"Controller source not found: {CONTROLLER_SOURCE}")
    if package_dir.exists() and not args.force:
        raise RuntimeError(f"Output folder already exists: {package_dir}. Use --force to replace it.")

    with config.open(encoding="utf-8") as stream:
        json.load(stream)
    export_cmd = executable("onshape-to-robot")

    output_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="onshape-webots-") as temp, tempfile.TemporaryDirectory(
        prefix=f".{args.name}-staging-", dir=output_parent
    ) as build_temp:
        temp_root = Path(temp)
        workspace = temp_root / "source"
        workspace.mkdir()
        shutil.copy2(config, workspace / "config.json")
        shutil.copy2(env_file, workspace / ".env")
        staging = Path(build_temp)
        package_stage = staging / "package"
        proto_dir = package_stage / "protos"
        proto_dir.mkdir(parents=True)
        controller_dir = package_stage / "controllers" / CONTROLLER_NAME
        shutil.copytree(CONTROLLER_SOURCE, controller_dir)

        subprocess.run([export_cmd, str(workspace)], check=True, cwd=workspace)
        urdf = workspace / "robot.urdf"
        meshes = workspace / "assets"
        if not urdf.is_file() or not meshes.is_dir():
            raise RuntimeError("Onshape export completed without producing robot.urdf and assets/.")
        shutil.copy2(urdf, staging / "robot.urdf")
        shutil.copytree(meshes, proto_dir / "assets")

        # Onshape emits package://assets/... URIs. Make an importer-only copy
        # beside the PROTO assets so urdf2webots writes portable relative URLs.
        proto_urdf = proto_dir / "robot.urdf"
        urdf_source = (staging / "robot.urdf").read_text(encoding="utf-8")
        urdf_source = urdf_source.replace('filename="package://assets/', 'filename="assets/')
        if "package://" in urdf_source:
            raise RuntimeError("URDF contains unsupported package:// mesh paths; expected package://assets/...")
        proto_urdf.write_text(urdf_source, encoding="utf-8")

        subprocess.run(
            [sys.executable, "-m", "urdf2webots.importer", f"--input={proto_urdf}",
             f"--output={proto_dir / (args.name + '.proto')}"],
            check=True,
            cwd=staging,
        )
        proto_urdf.unlink()
        proto = proto_dir / f"{args.name}.proto"
        if not proto.is_file():
            raise RuntimeError("URDF conversion completed without producing the requested PROTO file.")
        set_default_controller(proto)

        # Stage the root URDF beside its destination so replacement stays on one filesystem.
        root_urdf_fd, root_urdf_name = tempfile.mkstemp(prefix=".robot.urdf-", dir=ROOT)
        os.close(root_urdf_fd)
        root_urdf_stage = Path(root_urdf_name)
        shutil.copy2(staging / "robot.urdf", root_urdf_stage)
        backup_dir = Path(tempfile.mkdtemp(prefix=f".{args.name}-backup-", dir=output_parent))
        package_installed = False
        completed = False
        try:
            replace_package(package_stage, package_dir, args.force, backup_dir)
            package_installed = True
            root_urdf_stage.replace(ROOT / "robot.urdf")
            completed = True
        except Exception:
            backup_package = backup_dir / "previous-package"
            if backup_package.exists():
                shutil.rmtree(package_dir, ignore_errors=True)
                backup_package.replace(package_dir)
            elif package_installed:
                shutil.rmtree(package_dir, ignore_errors=True)
            raise
        finally:
            root_urdf_stage.unlink(missing_ok=True)
            if completed or not (backup_dir / "previous-package").exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

        print(f"Generated Webots project {package_dir}")
        print(f"  PROTO: {package_dir / 'protos' / proto.name}")
        print(f"  Assets: {package_dir / 'protos' / 'assets'}")
        print(f"  Controller: {package_dir / 'controllers' / CONTROLLER_NAME}")
        print(f"Generated {ROOT / 'robot.urdf'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"generate.py: error: {error}", file=sys.stderr)
        raise SystemExit(1)
