from __future__ import annotations

import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from src.shimeji_model import load_action_catalog, load_behavior_catalog


DOWNLOAD_PAGE = "https://neurofumo.itch.io/neurolings"


def default_collection() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "neuro-hypr-pet/collection"


def import_collection(archive: Path, destination: Path | None = None) -> tuple[str, ...]:
    destination = destination or default_collection()
    if destination.exists():
        raise ValueError(f"素材目录已存在：{destination}。请用 --destination 选择新目录。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as source, tempfile.TemporaryDirectory(prefix=".neurolings-import-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "collection"
        stage.mkdir()
        members = {}
        for info in source.infolist():
            path = PurePosixPath(info.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"ZIP 路径无效：{info.filename}")
            if not info.is_dir():
                members[path] = info
        roots = {PurePosixPath(*path.parts[:i]) for path in members for i, part in enumerate(path.parts)
                 if part == "img" and len(path.parts) > i + 2 and path.suffix.lower() == ".png"}
        if len(roots) != 1:
            raise ValueError("ZIP 中未找到唯一的 Shimeji 素材目录；请从发布页面下载 Neurolings v1.zip。")
        root = roots.pop()
        for path, info in members.items():
            if not path.is_relative_to(root):
                continue
            relative = path.relative_to(root)
            if not relative.parts:
                continue
            allowed = (relative.parts[0] in {"img", "conf", "sound"} and relative.suffix.lower() in {".png", ".xml", ".wav", ".ogg"})
            allowed = allowed or (len(relative.parts) == 1 and relative.name.lower() in {"licence.txt", "license.txt", "originallicence.txt", "readme.txt", "readme2.txt"})
            if allowed:
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info) as reader, target.open("wb") as writer:
                    shutil.copyfileobj(reader, writer)
        names = []
        for image_set in sorted((stage / "img").iterdir()):
            if not image_set.is_dir() or not (image_set / "shime1.png").is_file():
                continue
            conf = image_set / "conf"
            conf.mkdir(exist_ok=True)
            for filename in ("actions.xml", "behaviors.xml"):
                if not (conf / filename).exists() and (stage / "conf" / filename).is_file():
                    shutil.copyfile(stage / "conf" / filename, conf / filename)
            try:
                catalog = load_action_catalog(conf / "actions.xml")
                load_behavior_catalog(conf / "behaviors.xml")
            except (OSError, ET.ParseError, ValueError) as error:
                raise ValueError(f"素材 {image_set.name} 的 XML 无效：{error}") from error
            if not catalog.actions or not any(action.frames for action in catalog.actions.values()):
                raise ValueError(f"素材 {image_set.name} 没有可播放的动作。")
            for action in catalog.actions.values():
                for frame in action.frames:
                    for image in (frame.image, frame.image_right):
                        if not image:
                            continue
                        relative = PurePosixPath(image)
                        if relative.is_absolute() or ".." in relative.parts or not (image_set / image).is_file():
                            raise ValueError(f"素材 {image_set.name} 缺少或引用了无效图片：{image}")
            names.append(image_set.name)
        if not names:
            raise ValueError("ZIP 中没有包含 shime1.png 和动作 XML 的可用角色。")
        stage.rename(destination)
    return tuple(names)
