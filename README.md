# ESP32-Robot

CAD-to-simulation pipeline for a 4-wheel rover designed in [Onshape](https://cad.onshape.com).
The CAD model is exported to URDF, then converted to a Webots PROTO for simulation.

```
Onshape CAD ──(onshape-to-robot)──▶ robot.urdf + assets/*.stl ──(urdf2webots)──▶ Rover.proto
```

## Repository layout

| Path | Purpose |
|---|---|
| `config.json` | `onshape-to-robot` configuration (Onshape document URL, export options) |
| `.env` | Onshape API credentials (gitignored — never commit it) |
| `.env.example` | Template for the credentials file |
| `robot.urdf` | URDF description generated from the Onshape assembly |
| `assets/` | STL meshes (+ `.part` metadata) referenced by the URDF |
| `Rover.proto` | Webots PROTO of the rover (root copy, sits next to `assets/`) |
| `protos/` | Second conversion output (`Rover.proto` + its own `assets/` copy) |
| `.venv/` | Python virtual environment |

> The PROTO references its meshes with **relative** paths (`assets/...`), so a
> `.proto` file only works when it sits next to an `assets/` folder containing
> those meshes. That is why `protos/` carries its own copy.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install onshape-to-robot urdf2webots

cp .env.example .env    # then fill in your Onshape keys
```

Credentials come from [dev-portal.onshape.com/keys](https://dev-portal.onshape.com/keys).
The key's account must have access to the document referenced in `config.json`.
`onshape-to-robot` loads `.env` automatically (python-dotenv), so running from the
repo root is enough — no manual `source .env` needed.

## Step 1 — Onshape → URDF

Run from the repo root (where `config.json` lives):

```bash
onshape-to-robot
```

This downloads the assembly, resolves joints, and writes:

- `robot.urdf` — the robot description
- `assets/*.stl` — one mesh per part (+ `.part` metadata files)

### config.json reference

| Key | Meaning |
|---|---|
| `url` | Onshape document URL — must point at the **assembly** tab (`/w/.../e/...`) |
| `outputFormat` | Export format (`urdf`, `mujoco`, `sdf`, `bullet`) |
| `drawCollisions` | `true` to use visual meshes as collision geometry instead of simplified shapes |
| `jointMaxEffort` | Max effort written into every URDF joint |
| `jointMaxVelocity` | Max velocity written into every URDF joint |

Other useful keys: `robot_name`, `output_filename`, `assets_directory`, and
[processors](https://onshape-to-robot.readthedocs.io/) such as
`processor_simplify_stls` or `processor_convex_decomposition` for heavy meshes.

### Regenerating after a CAD change

Results are cached per document version. If the output looks stale after editing
the Onshape document:

```bash
onshape-to-robot-clear-cache
onshape-to-robot
```

## Step 2 — URDF → Webots PROTO

Run **from the repo root** so the relative `assets/...` mesh paths resolve:

```bash
python -m urdf2webots.importer \
    --input=robot.urdf \
    --output=Rover.proto \
    --robot-name=Rover
```

Outputs:

- `Rover.proto` — the robot PROTO (header states the source URDF and target Webots version)
- `Rover_textures/` — texture folder; **it being empty is normal** (the URDF has
  no texture materials, colors are exported as flat `PBRAppearance` values)
- Mesh URLs stay as `assets/...`, matching the existing folder — no copy step needed

### Useful urdf2webots options

| Flag | Effect |
|---|---|
| `--robot-name=NAME` | PROTO name (must be a valid Webots identifier) |
| `--target=R2025a` | Webots version to target (default `R2025a`; use your installed version) |
| `--box-collision` | Replace mesh collision shapes with bounding boxes (faster, more stable physics) |
| `--normal` | Export per-vertex normals for smoother shading |
| `--link-to-def` / `--joint-to-def` | Add DEF nodes so links/joints are reachable via `getFromProtoDef()` |
| `--init-pos="[0.1,0.1,...]"` | Initial joint positions |
| `--relative-path-prefix=DIR` | Remap relative mesh paths when the PROTO lives elsewhere |

## Using the PROTO in Webots

Add the robot to a world file (`.wbt`) and make sure the repo is on Webots'
project path (Preferences → Webots projects), so `Rover.proto` and `assets/` resolve:

```
Rover {
  translation 0 0 0.05
  controller "rover_controller"
}
```

Each wheel is a `HingeJoint` with a `RotationalMotor` and `PositionSensor`:

```c
// rover_controller (C)
#include <webots/robot.h>
#include <webots/motor.h>

#define WHEELS 4
static const char *wheel_names[WHEELS] = {
  "back_left_wheel", "front_left_wheel", "back_right_wheel", "front_right_wheel"
};

int main() {
  wb_robot_init();
  WbDeviceTag wheels[WHEELS];
  for (int i = 0; i < WHEELS; i++)
    wheels[i] = wb_robot_get_device(wheel_names[i]);
  for (int i = 0; i < WHEELS; i++)
    wb_motor_set_velocity(wheels[i], 5.0);  // rad/s, capped at maxVelocity
  while (wb_robot_step(TIME_STEP) != -1) {}
  wb_robot_cleanup();
  return 0;
}
```

Motor name pattern: `<corner>_<left|right>_wheel`, sensors are `<name>_sensor`.

## Debugging

### Onshape export (`onshape-to-robot`)

| Symptom | Cause / fix |
|---|---|
| `ERROR: No Onshape API access key are set` | `.env` not found. Run from the repo root, check `echo $ONSHAPE_ACCESS_KEY`, and confirm `.env` contains `ONSHAPE_API`, `ONSHAPE_ACCESS_KEY`, `ONSHAPE_SECRET_KEY`. |
| `WARNING: Storing Onshape credentials in config.json is deprecated` | Credentials were found in `config.json`; move them to `.env` and delete them from the config. |
| `Invalid URL: ...` | The `url` in `config.json` must match `https://<host>/documents/<docId>/(w\|v)/<id>/e/<elementId>` and point at the assembly element. |
| Stale geometry after CAD edits | Cached response. Run `onshape-to-robot-clear-cache`, then re-export. |
| Parts or sub-assemblies missing | The `/e/` element in the URL selects one assembly tab; make sure all parts are in that tab and the key's account has view permission. |
| Joints too weak / fast in simulation | Tune `jointMaxEffort` / `jointMaxVelocity` in `config.json` (these become the URDF limits). |
| Want to sanity-check the URDF before converting | Preview it in PyBullet: `onshape-to-robot-bullet robot.urdf` (installed in `.venv`). |

### URDF → PROTO conversion (`urdf2webots`)

| Symptom | Cause / fix |
|---|---|
| Webots shows the robot but meshes are missing/red | The PROTO's `assets/...` paths don't resolve. Keep the `.proto` next to `assets/`, re-run the conversion from the repo root, or copy `assets/` beside the PROTO (as done under `protos/`). |
| `Syntax error` when loading the PROTO | `--target` version is newer than the installed Webots. Regenerate with `--target` set to your Webots version. |
| Robot parts are flat-colored | Expected: URDF exports carry no textures, so shapes get solid `PBRAppearance` colors. Add textures in Onshape or edit the PROTO appearance by hand. |
| `Rover_textures/` folder is empty | Normal — there are no texture files to export. |
| Physics explodes / robot sinks through the floor | Mesh collisions are expensive and leaky. Try `--box-collision`, or add `processor_simplify_stls` / `processor_convex_decomposition` to `config.json` and re-export. |
| Joints exist but can't be driven | Confirm each `HingeJoint.device` block contains a `RotationalMotor` and that the controller fetches the exact motor `name`. |
| STL files are huge / Webots lags | Reduce mesh resolution in Onshape, or use the `processor_simplify_stls` processor before re-exporting. |

### Quick visual checks

- URDF only: `onshape-to-robot-bullet robot.urdf`
- Full simulation: open any `.wbt` world in Webots with `Rover` inserted, step the simulation, and drag the robot to verify joints and collisions.
