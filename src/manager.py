from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Callable

from src.hyprland import load_monitors, load_windows, select_monitor, visible_windows


def preferences_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "neuro-hypr-pet" / "preferences.json"


def available_image_sets(collection: Path) -> tuple[str, ...]:
    if not (collection / "img").is_dir():
        raise ValueError("未找到素材，请先运行 python3 tools/import_neurolings.py \"/path/to/Neurolings v1.zip\"，或用 --collection 指定已导入目录。")
    return tuple(sorted(path.name for path in (collection / "img").iterdir() if (path / "conf" / "actions.xml").is_file()))


def load_selection(path: Path, available: tuple[str, ...]) -> tuple[str, ...]:
    if not path.exists():
        return next(((name,) for name in ("Neuroling", "Neuron") if name in available), available[:1])
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(name for name in data["image_sets"] if name in available)


def save_selection(path: Path, names: tuple[str, ...], *, window_speed: float | None = None, allow_split: bool | None = None, split_probability: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["image_sets"] = names
    if allow_split is not None:
        data["allow_split"] = allow_split
        data["split_probability"] = split_probability
    if window_speed is not None:
        data["window_speed"] = window_speed
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class PetManager:
    def __init__(self, application, collection: Path, factory: Callable, *, monitor: str = "auto", selection_path: Path | None = None) -> None:
        self.application = application
        self.collection = collection
        self.factory = factory
        self.monitor = monitor
        self.selection_path = selection_path or preferences_path()
        self.available = available_image_sets(collection)
        self.selected = load_selection(self.selection_path, self.available)
        self.window_speed = float(json.loads(self.selection_path.read_text()).get("window_speed", 1.5)) if self.selection_path.exists() else 1.5
        self.allow_split = json.loads(self.selection_path.read_text()).get("allow_split", True) if self.selection_path.exists() else True
        self.split_probability = json.loads(self.selection_path.read_text()).get("split_probability") if self.selection_path.exists() else None
        self.paused = False
        self.following = False
        self.listeners: list[Callable] = []
        self.message = ""
        self.minimizations: dict[str, Callable] = {}
        application._neuro_hypr_shimeji_windows = []
        application._neuro_hypr_window_originals = {}
        application._neuro_hypr_manager = self

    @property
    def pets(self) -> list:
        return self.application._neuro_hypr_shimeji_windows

    def changed(self) -> None:
        for listener in list(self.listeners):
            listener()

    def set_selection(self, names) -> None:
        self.selected = tuple(dict.fromkeys(names))
        save_selection(self.selection_path, self.selected)
        self.changed()

    def spawn(self, name: str, monitor=None):
        if name not in self.available:
            raise ValueError(f"找不到素材 {name}，请检查 {self.collection / 'img'}")
        if monitor is None:
            monitor = select_monitor(None if self.monitor in {"auto", "all"} else self.monitor)
        pet = self.factory(name, monitor)
        self.register(pet)
        pet.start()
        return pet

    def register(self, pet, *, parent=None) -> None:
        pet.runtime.allow_split = parent.runtime.allow_split if parent else self.allow_split
        pet.runtime.split_probability = parent.runtime.split_probability if parent else self.split_probability
        pet.paused = self.paused
        pet.following_cursor = self.following and not pet.transient
        self.pets.append(pet)
        self.changed()

    def spawn_selected(self) -> None:
        if not self.selected:
            return
        monitors = load_monitors() if self.monitor == "all" else [select_monitor(None if self.monitor == "auto" else self.monitor)]
        self.set_paused(False)
        for name in self.selected:
            for monitor in monitors:
                self.spawn(name, monitor)
            self.set_selection(item for item in self.selected if item != name)

    def resummon(self, pet):
        return self.spawn(pet.catalog.image_set_dir.name, pet.monitor)

    def set_window_speed(self, speed: float) -> None:
        self.window_speed = max(0.5, min(3.0, speed))
        save_selection(self.selection_path, self.selected, window_speed=self.window_speed)
        self.changed()

    def set_split_defaults(self, enabled: bool, probability: float | None) -> None:
        self.allow_split = enabled
        self.split_probability = probability
        save_selection(self.selection_path, self.selected, allow_split=enabled, split_probability=probability)
        self.changed()

    def set_pet_split(self, pet, enabled: bool, probability: float | None) -> None:
        pet.runtime.allow_split = enabled
        pet.runtime.split_probability = probability
        self.changed()

    def apply_split_to_all(self, enabled: bool, probability: float | None) -> None:
        for pet in self.pets:
            pet.runtime.allow_split = enabled
            pet.runtime.split_probability = probability
        self.changed()

    def remove_all(self) -> None:
        for pet in list(self.pets):
            pet.close()

    def keep_one(self, pet=None) -> None:
        if not self.pets:
            return
        keep = pet or next((item for item in self.pets if not item.transient), self.pets[0])
        for item in list(self.pets):
            if item is not keep:
                item.close()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        for pet in self.pets:
            if paused and pet.runtime.pointer_active:
                pet.runtime.pointer_up(pet.runtime.cursor_x, pet.runtime.cursor_y)
            pet.paused = paused
        self.changed()

    def set_following(self, following: bool) -> None:
        self.following = following
        for pet in self.pets:
            pet.following_cursor = following and not pet.transient
            if not pet.transient and not pet.runtime.pointer_active and not pet.runtime.window_action_active:
                pet.runtime.start_action("Stand")
                if following:
                    pet.runtime.follow_cursor()
        self.changed()

    def interactive_windows(self):
        app_id = self.application.get_application_id()
        return [window for window in visible_windows(load_monitors(), load_windows()) if window.class_name != app_id]

    def interact(self, *, address: str | None = None, throw: bool = True, minimize: bool = False, pet=None) -> bool:
        windows = self.interactive_windows()
        if address is None:
            target = random.choice(windows) if windows else None
        else:
            target = next((window for window in windows if window.address == address), None)
        if target is None:
            raise ValueError("没有可用窗口，请刷新窗口列表")
        if target.address in self.minimizations:
            self.minimizations.pop(target.address)()
        if pet is None:
            pet = next((item for item in self.pets if not item.transient), None)
        if pet is None:
            pet = self.spawn(self.selected[0] if self.selected else self.available[0])
        self.set_paused(False)
        for other in self.pets:
            motion = other.window_motion
            if motion.target is not None and motion.target.address == target.address:
                other.runtime.start_action("Stand")
                other.runtime.desired_active_window_rect = None
                motion.release()
        if pet.runtime.pointer_active:
            pet.runtime.pointer_up(pet.runtime.cursor_x, pet.runtime.cursor_y)
        if not pet.request_window_interaction(target, throw=throw, minimize=minimize):
            raise ValueError(f"{pet.catalog.image_set_dir.name} 没有窗口搬运动作，请选择其他桌宠")
        self.message = "已开始抛出并最小化窗口" if minimize else "已开始抛出窗口" if throw else "已开始搬运窗口"
        self.changed()
        return True

    def restore_windows(self) -> None:
        self.cancel_minimizations()
        for pet in list(self.pets):
            if pet.transient:
                pet.close()
            else:
                pet.minimize_after_throw = False
                pet.runtime.start_action("Stand")
                pet.runtime.desired_active_window_rect = None
                pet.window_motion.release()
        from src.hyprland import WindowMotion
        WindowMotion(self.application._neuro_hypr_window_originals).restore(load_windows(), load_monitors())
        self.message = "已还原窗口"
        self.changed()

    def cancel_minimizations(self) -> None:
        for cancel in self.minimizations.values():
            cancel()
        self.minimizations.clear()

    def shutdown(self) -> None:
        from src.hyprland import WindowMotion
        placements = {address: self.application._neuro_hypr_window_originals[address] for address in self.minimizations}
        self.cancel_minimizations()
        if placements:
            WindowMotion(placements).restore(load_windows(), load_monitors())
        for pet in self.pets:
            pet.window_motion.release()
