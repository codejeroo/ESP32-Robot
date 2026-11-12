#!/usr/bin/env python3
"""Export an Onshape assembly to URDF and a Webots PROTO."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Webots PROTO and robot name")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json", help="Onshape export config")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "protos", help="Directory for PROTO and assets")
    args = parser.parse_args()
    if not NAME_RE.fullmatch(args.name):
        parser.error("--name must be a simple Webots identifier (letters, digits, underscores; not starting with a digit)")
    return args


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
    output_dir = args.output_dir.expanduser().resolve()
    env_file = ROOT / ".env"
    if not config.is_file():
        raise RuntimeError(f"Config file not found: {config}")
    if not env_file.is_file():
        raise RuntimeError(f"Credentials file not found: {env_file}. Copy .env.example to .env and add your Onshape credentials.")

    with config.open(encoding="utf-8") as stream:
        json.load(stream)
    export_cmd = executable("onshape-to-robot")

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="onshape-webots-") as temp:
        workspace = Path(temp) / "source"
        workspace.mkdir()
        shutil.copy2(config, workspace / "config.json")
        shutil.copy2(env_file, workspace / ".env")
        staging = Path(temp) / "result"
        staging.mkdir()

        subprocess.run([export_cmd, str(workspace)], check=True, cwd=workspace)
        urdf = workspace / "robot.urdf"
        meshes = workspace / "assets"
        if not urdf.is_file() or not meshes.is_dir():
            raise RuntimeError("Onshape export completed without producing robot.urdf and assets/.")
        shutil.copy2(urdf, staging / "robot.urdf")
        shutil.copytree(meshes, staging / "assets")

        subprocess.run(
            [sys.executable, "-m", "urdf2webots.importer", f"--input={staging / 'robot.urdf'}",
             f"--output={staging / (args.name + '.proto')}", f"--robot-name={args.name}"],
            check=True,
            cwd=staging,
        )
        proto = staging / f"{args.name}.proto"
        if not proto.is_file():
            raise RuntimeError("URDF conversion completed without producing the requested PROTO file.")

        # Replace the generated model and mesh set only after both stages succeed.
        target_proto = output_dir / proto.name
        backup = Path(temp) / "old-output"
        backup.mkdir()
        old_assets = output_dir / "assets"
        merged_assets = Path(temp) / "assets"
        merged_assets.mkdir()
        if old_assets.is_dir():
            for item in old_assets.iterdir():
                if item.suffix.lower() not in {".stl", ".part"}:
                    destination = merged_assets / item.name
                    shutil.copytree(item, destination) if item.is_dir() else shutil.copy2(item, destination)
        for item in (staging / "assets").iterdir():
            destination = merged_assets / item.name
            shutil.copytree(item, destination) if item.is_dir() else shutil.copy2(item, destination)
        if target_proto.exists():
            shutil.move(str(target_proto), str(backup / target_proto.name))
        if old_assets.exists():
            shutil.move(str(old_assets), str(backup / "assets"))
        try:
            shutil.copy2(proto, target_proto)
            shutil.move(str(merged_assets), str(old_assets))
        except Exception:
            target_proto.unlink(missing_ok=True)
            shutil.rmtree(old_assets, ignore_errors=True)
            if (backup / target_proto.name).exists():
                shutil.move(str(backup / target_proto.name), str(target_proto))
            if (backup / "assets").exists():
                shutil.move(str(backup / "assets"), str(old_assets))
            raise

        shutil.copy2(staging / "robot.urdf", ROOT / "robot.urdf")
        print(f"Generated {target_proto} and {old_assets}")
        print(f"Generated {ROOT / 'robot.urdf'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"generate.py: error: {error}", file=sys.stderr)
        raise SystemExit(1)
