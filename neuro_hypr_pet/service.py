from __future__ import annotations

import shlex
from pathlib import Path


def render_shimeji_user_service(
    *,
    repo_root: Path,
    collection: Path,
    image_set: str | None,
    monitor: str,
    fps: int,
    python: Path,
    move_active_window: bool = False,
) -> str:
    repo_root = repo_root.resolve()
    collection = collection.resolve()
    python = python.absolute()
    script = repo_root / "tools" / "neuro_hypr_shimeji.py"
    required_path = collection / "img" / image_set / "conf" / "actions.xml" if image_set else collection / "img"
    command = [
        str(python),
        str(script),
        "--collection",
        str(collection),
        "--monitor",
        monitor,
        "--fps",
        str(fps),
    ]
    if image_set:
        command.extend(["--image-set", image_set])
    if move_active_window:
        command.append("--move-active-window")
    return "\n".join(
        [
            "[Unit]",
            "Description=Neuro Hypr Pet sprite-bounded Shimeji runtime",
            "PartOf=graphical-session.target",
            "After=graphical-session.target",
            "ConditionEnvironment=WAYLAND_DISPLAY",
            f"ConditionPathExists={required_path}",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={repo_root}",
            "Environment=GDK_BACKEND=wayland",
            "Environment=GSK_RENDERER=cairo",
            f"ExecStart={' '.join(shlex.quote(part) for part in command)}",
            "Restart=on-failure",
            "RestartSec=2",
            "",
            "[Install]",
            "WantedBy=graphical-session.target",
            "",
        ]
    )


def write_shimeji_user_service(
    service: Path,
    *,
    repo_root: Path,
    collection: Path,
    image_set: str | None,
    monitor: str,
    fps: int,
    python: Path,
    move_active_window: bool = False,
) -> None:
    service.parent.mkdir(parents=True, exist_ok=True)
    service.write_text(
        render_shimeji_user_service(
            repo_root=repo_root,
            collection=collection,
            image_set=image_set,
            monitor=monitor,
            fps=fps,
            python=python,
            move_active_window=move_active_window,
        ),
        encoding="utf-8",
    )


def write_manager_desktop_entry(path: Path, *, repo_root: Path, collection: Path, python: Path) -> None:
    command = [str(python.absolute()), str(repo_root.resolve() / "tools" / "neuro_hypr_shimeji.py"),
               "--collection", str(collection.resolve()), "--manage"]
    # Desktop Entry Exec uses double quotes rather than shell quoting.
    quoted = ['"' + part.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$") + '"' for part in command]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Neuroling", "Comment=Manage Neuroling desktop pets",
        f"Exec={' '.join(quoted)}", "Icon=face-smile", "Terminal=false", "Categories=Utility;", "",
    ]), encoding="utf-8")
