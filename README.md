# ESP32-Robot

CAD-to-simulation pipeline for a 4-wheel rover designed in [Onshape](https://cad.onshape.com).
The CAD model is exported to URDF, then packaged as a Webots PROTO project with its
meshes and the `rover_drive` controller.

```
Onshape CAD ──(generate.py)──▶ robot.urdf + generated/<name>/
                                             ├── protos/<name>.proto + assets/
                                             └── controllers/rover_drive/
```

## Repository layout

| Path | Purpose |
|---|---|
| `config.json` | `onshape-to-robot` configuration (Onshape document URL, export options) |
| `.env` | Onshape API credentials (gitignored — never commit it) |
| `.env.example` | Template for the credentials file |
| `robot.urdf` | URDF description generated from the Onshape assembly |
| `generated/<name>/` | Shareable Webots project folder for the named robot |
| `generated/<name>/protos/` | Named PROTO and matching `assets/` meshes |
| `generated/<name>/controllers/rover_drive/` | Python drive controller and runtime settings |
| `.venv/` | Python virtual environment |

The PROTO references meshes with relative `assets/...` paths. Keep the PROTO
inside `protos/` beside its `assets/` directory when sharing or moving the package.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # then fill in your Onshape keys
```

Credentials come from [dev-portal.onshape.com/keys](https://dev-portal.onshape.com/keys).
The key's account must have access to the document referenced in `config.json`.
`onshape-to-robot` loads `.env` automatically (python-dotenv), so running from the
repo root is enough — no manual `source .env` needed.

## Automated generation

`generate.py` runs the Onshape export and Webots conversion, then creates a
shareable Webots project folder. Run it from the repository root after
activating the environment and creating `.env`:

```bash
python generate.py --name Kristel
```

This writes `robot.urdf` at the repository root and creates
`generated/Kristel/` with this layout:

```
generated/Kristel/
├── protos/
│   ├── Kristel.proto
│   └── assets/                 # meshes referenced by the PROTO
└── controllers/
    └── rover_drive/
        ├── rover_drive.py
        └── runtime.ini
```

The generated PROTO selects `rover_drive` by default. The package does not include
a world; add the robot to a world of your choice. To use the package on another
device, share the whole named folder, register it as a Webots project directory,
and open or create a world in Webots. Webots must be installed on that device,
along with Python 3 available as `python` on `PATH`. The generated PROTO targets
Webots R2025a by default; use R2025a or a newer compatible release.

The package contains no Onshape credentials. `.env` and `config.json` are only
needed by the person regenerating the model; each user regenerating it must have
their own Onshape credentials and access to the referenced document.

The PROTO name is required and must be a simple Webots identifier. Optional
`--config PATH` selects another Onshape configuration. `--output-dir PATH`
selects the parent directory for the named package (default: `generated/`). For
example:

```bash
python generate.py --name Kristel
python generate.py --name Rover --output-dir ./simulation
```

If `<output-dir>/<name>/` already exists, generation stops instead of replacing
it. Pass `--force` to replace that package folder:

```bash
python generate.py --name Kristel --force
```

Dependencies are listed in `requirements.txt`; install them in the active
virtual environment with `pip install -r requirements.txt`. The script does not
install packages.

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
python generate.py --name Rover
```

The share package keeps the generated PROTO next to its matching `assets/` folder
under `protos/`. Use `--force` to replace an existing package after a CAD change.

### Useful urdf2webots options

| Flag | Effect |
|---|---|
| `--robot-name=NAME` | Emit a Robot node string with this name instead of a PROTO; omit it for PROTO conversion (the output filename sets the PROTO name) |
| `--target=R2025a` | Webots version to target (default `R2025a`; use your installed version) |
| `--box-collision` | Replace mesh collision shapes with bounding boxes (faster, more stable physics) |
| `--normal` | Export per-vertex normals for smoother shading |
| `--link-to-def` / `--joint-to-def` | Add DEF nodes so links/joints are reachable via `getFromProtoDef()` |
| `--init-pos="[0.1,0.1,...]"` | Initial joint positions |
| `--relative-path-prefix=DIR` | Remap relative mesh paths when the PROTO lives elsewhere |

## Using the share package in Webots

Register the generated folder as a Webots project directory (Preferences → Webots
projects). Then open or create a world and add the robot's PROTO. The generated
PROTO defaults to `rover_drive`, which moves the rover forward:

```
Kristel {
  translation 0 0 0.05
}
```

The included Python controller drives the wheels forward. Motor names follow
`<front|back>_<left|right>_wheel`; sensors use the corresponding `_sensor` suffix.

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
| Webots shows the robot but meshes are missing/red | The PROTO's `assets/...` paths don't resolve. Keep it beside `assets/` under the package's `protos/` directory and register the package as a Webots project. |
| `Syntax error` when loading the PROTO | `--target` version is newer than the installed Webots. Regenerate with `--target` set to your Webots version. |
| Robot parts are flat-colored | Expected: URDF exports carry no textures, so shapes get solid `PBRAppearance` colors. Add textures in Onshape or edit the PROTO appearance by hand. |
| `Rover_textures/` folder is empty | Normal — there are no texture files to export. |
| Physics explodes / robot sinks through the floor | Mesh collisions are expensive and leaky. Try `--box-collision`, or add `processor_simplify_stls` / `processor_convex_decomposition` to `config.json` and re-export. |
| Joints exist but can't be driven | Confirm each `HingeJoint.device` block contains a `RotationalMotor` and that the controller fetches the exact motor `name`. |
| STL files are huge / Webots lags | Reduce mesh resolution in Onshape, or use the `processor_simplify_stls` processor before re-exporting. |

### Quick visual checks

- URDF only: `onshape-to-robot-bullet robot.urdf`
- Full simulation: open or create a `.wbt` world in Webots, add the generated PROTO, and step the simulation to verify the meshes, joints, and controller.
