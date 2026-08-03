# Repository Guide

## Scope and Architecture

- `deepcool-lm` owns USB transport, production IPC, display state, and the CLI. `deepcool_lm_system.py` collects system data without USB; `deepcool_lm_display.py` renders PIL images and encodes RGB565 without collecting data.
- `monitor` owns the USB device and `/var/run/deepcool-lm.sock`; while that socket exists, `solid`, `brightness`, and `monitor` send JSON to the running process instead of opening USB directly. Custom image upload is intentionally unsupported.
- `deepcool-lm-preview` is a repository-only PySide6 tool. It must not import PyUSB, connect to the production socket, or be installed by packaging scripts; its control socket lives under `$XDG_RUNTIME_DIR`, while timestamped PNGs go to ignored `previews/`.
- Hardware assumptions are protocol-critical: VID:PID `3633:0026`, endpoint `0x01`, 320x240 output, a 13-byte frame header, and a 153,600-byte little-endian RGB565 framebuffer. Do not change these as ordinary UI constants.
- `pkg/`, `src/`, and `*.pkg.tar.*` are `makepkg` outputs. Edit root sources only.

## Installation Boundaries

- Arch packaging is defined by `PKGBUILD`: it installs the executable to `/usr/bin`, shared modules to `/usr/lib/deepcool-lm`, and the service to `/etc/systemd/system`. `deepcool-lm.install` contains package lifecycle hooks.
- `install.sh` is a separate, interactive root installer. It installs under `/usr/local`, downloads missing source files from the repository's `main` branch, rewrites the service executable path, and manages systemd itself.
- The service explicitly starts `/usr/bin/deepcool-lm`; account for that path when changing either installation flow.
- `PKGBUILD` is authoritative package metadata. After changing it, regenerate the tracked `.SRCINFO` with `makepkg --printsrcinfo > .SRCINFO`; do not hand-edit `.SRCINFO`.
- Do not run `install.sh`, `uninstall.sh`, package install hooks, `systemctl` mutations, or device commands during routine verification: they require root and alter the host or real LCD.

## Verification

- There is no automated test suite, linter, formatter, or CI. Run the focused checks that match the changed files:
- Rendering regression tests: `python -m unittest discover -s tests -v`.
- Python syntax and import-independent compilation: `python -m py_compile deepcool-lm deepcool_lm_display.py deepcool_lm_system.py deepcool-lm-preview`.
- CLI/parser smoke test (requires runtime Python dependencies): `./deepcool-lm --help`.
- Preview/parser smoke test (requires PySide6 only for `run`): `./deepcool-lm-preview --help`.
- Shell syntax: `bash -n install.sh uninstall.sh`.
- Systemd unit syntax: `systemd-analyze verify deepcool-lm.service`.
- Package metadata consistency: `diff -u .SRCINFO <(makepkg --printsrcinfo)`.
- Full non-installing package build: `makepkg -f`; this recreates ignored `pkg/`, `src/`, and the package archive.
- Real monitor/render/brightness testing requires the USB device and usually root access. Report it as untested when hardware is unavailable rather than treating `--help` as hardware coverage.

## Change Coupling

- Keep user-facing commands synchronized across `deepcool-lm`, `README.md`, `install.sh`, and messages in `deepcool-lm.install`.
- Keep service names, executable paths, dependencies, and socket cleanup synchronized across `PKGBUILD`, `deepcool-lm.service`, both shell scripts, and `deepcool-lm.install`.
- Rendering changes belong in `deepcool_lm_display.py`; production and preview must both call `render_monitor_framebuffer()`. The preview may only decode that final 153,600-byte RGB565 payload with `framebuffer_to_rgb_image()`, never maintain a second layout path.
