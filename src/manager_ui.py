from __future__ import annotations

import random
import subprocess
from pathlib import Path

import gi
if hasattr(gi, "require_version"):
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, Gtk, Gtk4LayerShell, Pango

from src.assets import DOWNLOAD_PAGE, import_collection
from src.hyprland import cursor_pos, load_monitors, monitor_for_point
from src.manager import available_image_sets


class SplitControls(Gtk.Box):
    def __init__(self, manager, read, write) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.manager, self.read, self.write = manager, read, write
        self.syncing = False
        row = Gtk.Box(spacing=8)
        self.enabled = Gtk.CheckButton(label="允许分裂")
        self.original = Gtk.CheckButton(label="使用素材概率")
        row.append(self.enabled)
        row.append(self.original)
        self.append(row)
        chance = Gtk.Box(spacing=8)
        chance.append(Gtk.Label(label="自动分裂概率", xalign=0))
        self.probability = Gtk.SpinButton.new_with_range(0, 100, 1)
        self.probability.set_digits(0)
        self.probability.set_tooltip_text("每次自主选择动作时的分裂概率；仍遵守素材条件。手动分裂不受概率限制。")
        chance.append(self.probability)
        chance.append(Gtk.Label(label="%"))
        self.append(chance)
        self.sync()
        self.enabled.connect("toggled", self._changed)
        self.original.connect("toggled", self._changed)
        self.probability.connect("value-changed", self._changed)
        self.connect("map", self._subscribe)
        self.connect("unmap", self._unsubscribe)

    def _subscribe(self, _widget):
        if self.sync not in self.manager.listeners:
            self.manager.listeners.append(self.sync)
        self.sync()

    def _unsubscribe(self, _widget):
        if self.sync in self.manager.listeners:
            self.manager.listeners.remove(self.sync)

    def sync(self):
        enabled, probability = self.read()
        self.syncing = True
        self.enabled.set_active(enabled)
        self.original.set_active(probability is None)
        self.probability.set_value(0 if probability is None else probability)
        self.original.set_sensitive(enabled)
        self.probability.set_sensitive(enabled and probability is not None)
        self.syncing = False

    def _changed(self, _widget):
        if not self.syncing:
            self.write(self.enabled.get_active(), None if self.original.get_active() else self.probability.get_value())
            self.sync()


class ManagerPopup(Gtk.ApplicationWindow):
    SPEEDS = [0.25, 0.5, 0.7, 1.0, 1.5]
    SPEED_LABELS = ["0.25× (轻浮)", "0.5× (轻缓)", "0.7× (默认)", "1.0× (自然)", "1.5× (快速)"]

    def __init__(self, manager) -> None:
        super().__init__(application=manager.application)
        self.manager = manager
        self.set_title("Neuroling 管理")
        self.set_default_size(520, 640)
        self.set_decorated(False)
        self.add_css_class("neuro-manager-popup")

        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_namespace(self, "neuro-hypr-manager")
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_exclusive_zone(self, 0)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)

        self.connect("close-request", self._hide)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key_pressed)
        self.add_controller(keys)

        self.material_rows = {}
        self._current_available = ()
        self._refreshing_selection = False

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(root, f"set_margin_{side}")(14)
        self.set_child(root)

        # 1. Top Header Bar
        heading = Gtk.Box(spacing=8)
        title = Gtk.Label(label="Neuroling", xalign=0)
        title.add_css_class("neuro-header-title")
        heading.append(title)

        self.status_badge = Gtk.Label(label="○ 桌面暂无桌宠", xalign=0)
        self.status_badge.add_css_class("neuro-badge")
        self.status_badge.add_css_class("neuro-badge-inactive")
        heading.append(self.status_badge)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        heading.append(spacer)

        btn_random = self._button("🎲 随机", self.spawn_random)
        btn_random.set_tooltip_text("随机召唤一个角色")
        heading.append(btn_random)

        btn_clean = self._button("清屏", self.remove_all)
        btn_clean.set_tooltip_text("移除当前桌面所有桌宠")
        btn_clean.add_css_class("destructive-action")
        heading.append(btn_clean)

        dismiss = Gtk.Button(label="×", tooltip_text="收起")
        dismiss.add_css_class("flat")
        dismiss.connect("clicked", self._hide)
        heading.append(dismiss)
        root.append(heading)

        # 2. Global Quick Controls Bar
        controls = Gtk.Box(spacing=8)
        controls.add_css_class("neuro-quick-bar")
        self.pause = self._button("暂停", lambda: manager.set_paused(not manager.paused))
        controls.append(self.pause)

        self.follow = Gtk.ToggleButton(label="全部跟随鼠标")
        self.follow.set_tooltip_text("沿屏幕底部或窗口顶边追随鼠标，靠近后停下；再次点击恢复自主漫步")
        self.follow.connect("toggled", self._follow)
        controls.append(self.follow)

        controls.append(self._button("只留一只", manager.keep_one))
        root.append(controls)

        # 3. Main Stack / Tabs
        tabs = Gtk.Stack()
        tabs.set_vexpand(True)
        switcher = Gtk.StackSwitcher(stack=tabs, halign=Gtk.Align.FILL)
        switcher.set_hexpand(True)
        root.append(switcher)
        root.append(tabs)

        tabs.add_titled(self._materials(), "materials", "角色素材")
        self.pet_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.listed_pets = None
        tabs.add_titled(self._pets(), "pets", "活动桌宠")
        tabs.add_titled(self._window_actions(), "windows", "窗口互动")

        # 4. Status Feedback Banner
        message_card = Gtk.Box()
        message_card.add_css_class("neuro-card")
        self.message = Gtk.Label(xalign=0, wrap=True)
        self.message.add_css_class("neuro-status-text")
        message_card.append(self.message)
        root.append(message_card)

        # 5. Bottom Toolbar
        bottom = Gtk.Box(spacing=8)
        bottom_spacer = Gtk.Box()
        bottom_spacer.set_hexpand(True)
        bottom.append(bottom_spacer)
        quit_button = self._button("退出程序", manager.application.quit)
        quit_button.add_css_class("destructive-action")
        bottom.append(quit_button)
        root.append(bottom)

        manager.listeners.append(self.refresh)
        self.refresh()

    def _hide(self, _window) -> bool:
        self.set_visible(False)
        return True

    def _key_pressed(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self._hide(self)
            return True
        return False

    def _run(self, action) -> None:
        try:
            action()
        except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
            self.set_status(str(error), is_error=True)

    def _button(self, text, action):
        button = Gtk.Button(label=text)
        button.connect("clicked", lambda _button: self._run(action))
        return button

    @staticmethod
    def _scroll(child):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(child)
        scroll.set_vexpand(True)
        return scroll

    @staticmethod
    def _make_avatar(path: Path) -> Gtk.Widget:
        if path.is_file():
            try:
                picture = Gtk.Picture.new_for_filename(str(path))
                picture.set_can_shrink(True)
                picture.set_size_request(36, 36)
                picture.add_css_class("neuro-avatar")
                return picture
            except Exception:
                pass
        fallback = Gtk.Image.new_from_icon_name("face-smile")
        fallback.set_pixel_size(32)
        fallback.add_css_class("neuro-avatar")
        return fallback

    def set_status(self, text: str, is_error: bool = False) -> None:
        if not text:
            self.message.set_label("💡 提示：右键点击桌面的桌宠可唤出快捷动作；点击角色旁“+ 召唤”可直接生成")
            self.message.remove_css_class("error-text")
            return
        if is_error:
            self.message.set_label(f"⚠️ {text}")
            self.message.add_css_class("error-text")
        else:
            self.message.set_label(f"ℹ️ {text}")
            self.message.remove_css_class("error-text")

    def _materials(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # Top selection bar
        selection = Gtk.Box(spacing=8)
        self.lib_count = Gtk.Label(label="(共 0 种)", xalign=0)
        self.lib_count.add_css_class("neuro-subtext")
        selection.append(self.lib_count)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        selection.append(spacer)

        selection.append(self._button("全选", lambda: self.manager.set_selection(self.manager.available)))
        selection.append(self._button("全不选", lambda: self.manager.set_selection(())))
        panel.append(selection)

        # Scrollable Character Library
        self.material_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        panel.append(self._scroll(self.material_box))

        # Bottom Actions Bar
        actions_bar = Gtk.Box(spacing=8)
        self.summon = self._button("➕ 召唤所选", self.spawn_selected)
        self.summon.add_css_class("suggested-action")
        self.summon.set_hexpand(True)
        actions_bar.append(self.summon)

        actions_bar.append(self._button("📂 导入 ZIP…", self.import_zip))
        actions_bar.append(self._button("🌐 获取素材", self.download_materials))
        panel.append(actions_bar)

        self._rebuild_material_list()
        return panel

    def _rebuild_material_list(self) -> None:
        names = self.manager.available
        self._current_available = tuple(names)
        self.material_rows = {}
        self.lib_count.set_label(f"(共 {len(names)} 种)")

        while (child := self.material_box.get_first_child()) is not None:
            self.material_box.remove(child)

        if not names:
            empty = Gtk.Label(label="暂无可用的素材角色，请先导入 ZIP 或下载素材。")
            empty.add_css_class("neuro-empty-hint")
            self.material_box.append(empty)
            return

        for name in names:
            row = Gtk.Box(spacing=8)
            row.add_css_class("neuro-material-row")

            check = Gtk.CheckButton()
            check.set_active(name in self.manager.selected)
            check.connect("toggled", lambda _check, name=name: self._toggle_selection(name))
            row.append(check)

            avatar = self._make_avatar(self.manager.collection / "img" / name / "shime1.png")
            row.append(avatar)

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            info.set_hexpand(True)
            name_label = Gtk.Label(label=name, xalign=0)
            name_label.add_css_class("bold")
            badge = Gtk.Label(label="未召唤", xalign=0)
            badge.add_css_class("neuro-badge-sm")
            badge.add_css_class("neuro-badge-inactive-text")
            info.append(name_label)
            info.append(badge)
            row.append(info)

            spawn_btn = Gtk.Button(label="+ 召唤")
            spawn_btn.connect("clicked", lambda _btn, name=name: self.spawn_one(name))
            row.append(spawn_btn)

            self.material_box.append(row)
            self.material_rows[name] = {
                "row": row,
                "check": check,
                "badge": badge,
                "spawn_button": spawn_btn,
            }

    def _toggle_selection(self, name: str) -> None:
        if self._refreshing_selection:
            return
        selected = list(self.manager.selected)
        if name in selected:
            selected.remove(name)
        else:
            selected.append(name)
        self.manager.set_selection(selected)

    def spawn_one(self, name: str) -> None:
        try:
            self.manager.spawn(name)
            self.set_status(f"已召唤 {name}")
        except Exception as error:
            self.set_status(str(error), is_error=True)

    def spawn_random(self) -> None:
        if not self.manager.available:
            self.set_status("没有可用的素材，请先导入素材", is_error=True)
            return
        name = random.choice(self.manager.available)
        try:
            self.manager.spawn(name)
            self.set_status(f"🎲 已随机召唤：{name}")
        except Exception as error:
            self.set_status(str(error), is_error=True)

    def spawn_selected(self) -> None:
        if not self.manager.selected:
            self.set_status("请先勾选需要召唤的角色素材", is_error=True)
            return
        count = len(self.manager.selected)
        self.manager.spawn_selected()
        self.set_status(f"已召唤所选角色（共 {count} 种）")

    def remove_all(self) -> None:
        if not self.manager.pets:
            self.set_status("当前桌面没有活跃的桌宠")
            return
        count = len(self.manager.pets)
        self.manager.remove_all()
        self.set_status(f"已移除全部桌面桌宠（共 {count} 只）")

    def import_zip(self) -> None:
        chooser = Gtk.FileChooserNative.new(
            "导入素材 ZIP 包",
            self,
            Gtk.FileChooserAction.OPEN,
            "导入",
            "取消",
        )
        filter_zip = Gtk.FileFilter()
        filter_zip.set_name("ZIP 压缩包 (*.zip)")
        filter_zip.add_pattern("*.zip")
        chooser.add_filter(filter_zip)

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file:
                    path = Path(file.get_path())
                    try:
                        names = import_collection(path, self.manager.collection)
                        self.manager.available = available_image_sets(self.manager.collection)
                        self.manager.changed()
                        self.set_status(f"已成功导入角色素材：{'、'.join(names)}")
                    except Exception as error:
                        self.set_status(f"导入失败：{error}", is_error=True)
            dialog.destroy()

        chooser.connect("response", on_response)
        chooser.show()

    def download_materials(self) -> None:
        try:
            subprocess.Popen(["xdg-open", DOWNLOAD_PAGE])
            self.set_status("正在打开素材下载页面…")
        except Exception as error:
            self.set_status(f"无法打开浏览器: {error}", is_error=True)

    def _pets(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.append(self._scroll(self.pet_list))

        # Behavior & Physics Card
        physics_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        physics_card.add_css_class("neuro-card")

        card_title = Gtk.Label(label="全局行为偏好与物理设置", xalign=0)
        card_title.add_css_class("bold")
        card_title.add_css_class("neuro-subtext")
        physics_card.append(card_title)

        # Fall Speed Setting
        speed_row = Gtk.Box(spacing=8)
        speed_row.append(Gtk.Label(label="⚡ 下落重力速度:", xalign=0, hexpand=True))
        self.fall_speed_dropdown = Gtk.DropDown.new_from_strings(self.SPEED_LABELS)
        self.fall_speed_dropdown.connect("notify::selected", self._fall_speed_selected)
        speed_row.append(self.fall_speed_dropdown)
        physics_card.append(speed_row)

        # Global Split Defaults
        split_row = Gtk.Box(spacing=8)
        split_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        split_box.set_hexpand(True)
        split_box.append(SplitControls(self.manager,
            lambda: (self.manager.allow_split, self.manager.split_probability), self.manager.set_split_defaults))
        split_row.append(split_box)

        apply_all_btn = self._button("应用到全部", lambda: (
            self.manager.apply_split_to_all(self.manager.allow_split, self.manager.split_probability),
            self.set_status("已将分裂设置应用至当前所有桌宠")
        ))
        apply_all_btn.set_valign(Gtk.Align.CENTER)
        split_row.append(apply_all_btn)
        physics_card.append(split_row)

        panel.append(physics_card)
        return panel

    def _fall_speed_selected(self, dropdown, _param) -> None:
        idx = dropdown.get_selected()
        if 0 <= idx < len(self.SPEEDS):
            target = self.SPEEDS[idx]
            if abs(self.manager.fall_speed - target) > 0.01:
                self.manager.set_fall_speed(target)
                self.set_status(f"已设置下落速度为 {target}×")

    def _follow(self, button) -> None:
        if button.get_active() != self.manager.following:
            self._run(lambda: self.manager.set_following(button.get_active()))

    def _window_actions(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # Actor pet card
        actor_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        actor_card.add_css_class("neuro-card")
        actor_card.append(Gtk.Label(label="执行桌宠", xalign=0, css_classes=["bold", "neuro-subtext"]))
        self.actor = self._dropdown()
        self.actor_pets = []
        actor_card.append(self.actor)
        panel.append(actor_card)

        # Target window card
        target_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        target_card.add_css_class("neuro-card")
        target_header = Gtk.Box(spacing=8)
        target_header.append(Gtk.Label(label="目标窗口", xalign=0, hexpand=True, css_classes=["bold", "neuro-subtext"]))
        target_header.append(self._button("刷新", self.refresh_windows))
        target_card.append(target_header)
        self.target = self._dropdown()
        self.target_windows = []
        target_card.append(self.target)
        panel.append(target_card)

        # Interaction settings and actions card
        action_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        action_card.add_css_class("neuro-card")

        speed_row = Gtk.Box(spacing=8)
        speed_row.append(Gtk.Label(label="搬运 / 抛出速度（倍）", xalign=0, hexpand=True))
        self.window_speed_spin = Gtk.SpinButton.new_with_range(0.5, 3.0, 0.25)
        self.window_speed_spin.set_digits(2)
        self.window_speed_spin.set_value(self.manager.window_speed)
        self.window_speed_spin.connect("value-changed", self._window_speed_changed)
        speed_row.append(self.window_speed_spin)
        action_card.append(speed_row)

        buttons = Gtk.Box(spacing=8)
        self.carry = self._button("搬运所选窗口", lambda: self._interact(False))
        self.throw = self._button("抛出所选窗口", lambda: self._interact(True))
        buttons.append(self.carry)
        buttons.append(self.throw)
        buttons.append(self._button("随机抛出", lambda: self._interact(True, random_target=True)))
        action_card.append(buttons)

        finish = Gtk.Box(spacing=8)
        self.minimize = self._button("抛出并最小化", lambda: self._interact(True, minimize=True))
        finish.append(self.minimize)
        finish.append(self._button("↩️ 还原搬动的窗口", self.manager.restore_windows))
        action_card.append(finish)
        panel.append(action_card)

        self.refresh_windows()
        return panel

    @staticmethod
    def _dropdown():
        dropdown = Gtk.DropDown()
        dropdown.set_enable_search(True)
        factory = Gtk.SignalListItemFactory()
        def setup(_factory, item):
            label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=36)
            item.set_child(label)
        def bind(_factory, item):
            text = item.get_item().get_string()
            item.get_child().set_label(text)
            item.get_child().set_tooltip_text(text)
        factory.connect("setup", setup)
        factory.connect("bind", bind)
        dropdown.set_factory(factory)
        dropdown.set_list_factory(factory)
        return dropdown

    def refresh_windows(self) -> None:
        selected = self.target.get_selected()
        old = self.target_windows[selected].address if selected < len(self.target_windows) else None
        self.target_windows = self.manager.interactive_windows()
        labels = [f"{window.class_name} — {window.title}" for window in self.target_windows]
        self.target.set_model(Gtk.StringList.new(labels))
        for index, window in enumerate(self.target_windows):
            if window.address == old:
                self.target.set_selected(index)
        self.carry.set_sensitive(bool(labels))
        self.throw.set_sensitive(bool(labels))
        self.minimize.set_sensitive(bool(labels))

    def _window_speed_changed(self, spin) -> None:
        if spin.get_value() != self.manager.window_speed:
            self._run(lambda: self.manager.set_window_speed(spin.get_value()))

    def _interact(self, throw: bool, *, random_target: bool = False, minimize: bool = False) -> None:
        index = self.actor.get_selected()
        pet = self.actor_pets[index - 1] if 0 < index <= len(self.actor_pets) else None
        selected = self.target.get_selected()
        address = None if random_target else self.target_windows[selected].address
        self.manager.interact(address=address, throw=throw, minimize=minimize, pet=pet)

    def refresh(self) -> None:
        manager = self.manager
        active_count = len(manager.pets)
        paused = manager.paused

        # Update Top Header badge
        self.status_badge.remove_css_class("neuro-badge-active")
        self.status_badge.remove_css_class("neuro-badge-paused")
        self.status_badge.remove_css_class("neuro-badge-inactive")
        if active_count == 0:
            self.status_badge.set_label("○ 桌面暂无桌宠")
            self.status_badge.add_css_class("neuro-badge-inactive")
        elif paused:
            self.status_badge.set_label(f"⏸️ 已暂停：{active_count} 只桌宠")
            self.status_badge.add_css_class("neuro-badge-paused")
        else:
            self.status_badge.set_label(f"● 桌面活动：{active_count} 只桌宠")
            self.status_badge.add_css_class("neuro-badge-active")

        self.pause.set_label("继续" if paused else "暂停")
        self.follow.set_active(manager.following)
        self.window_speed_spin.set_value(manager.window_speed)

        # Count active pets by character
        counts = {}
        for pet in manager.pets:
            pname = pet.catalog.image_set_dir.name
            counts[pname] = counts.get(pname, 0) + 1

        # Check if materials list changed
        if tuple(manager.available) != self._current_available:
            self._rebuild_material_list()

        # Update material rows
        self._refreshing_selection = True
        for name, widgets in self.material_rows.items():
            is_sel = name in manager.selected
            widgets["check"].set_active(is_sel)
            cnt = counts.get(name, 0)
            if cnt > 0:
                widgets["badge"].set_label(f"● {cnt} 只在桌面活动")
                widgets["badge"].remove_css_class("neuro-badge-inactive-text")
                widgets["badge"].add_css_class("neuro-badge-active-text")
            else:
                widgets["badge"].set_label("未召唤")
                widgets["badge"].remove_css_class("neuro-badge-active-text")
                widgets["badge"].add_css_class("neuro-badge-inactive-text")
        self._refreshing_selection = False

        sel_count = len(manager.selected)
        self.summon.set_label(f"➕ 召唤所选 ({sel_count})" if sel_count > 0 else "➕ 召唤所选")
        self.summon.set_sensitive(sel_count > 0)

        # Update fall speed dropdown
        current_speed = manager.fall_speed
        best_idx = min(range(len(self.SPEEDS)), key=lambda i: abs(self.SPEEDS[i] - current_speed))
        if self.fall_speed_dropdown.get_selected() != best_idx:
            self.fall_speed_dropdown.set_selected(best_idx)

        # Update message
        msg = manager.message
        self.set_status(msg)

        # Update actor dropdown for windows tab
        old_actor = self.actor_pets[self.actor.get_selected() - 1] if 0 < self.actor.get_selected() <= len(self.actor_pets) else None
        self.actor_pets = [pet for pet in manager.pets if not pet.transient]
        self.actor.set_model(Gtk.StringList.new(["自动选择"] + [f"{pet.catalog.image_set_dir.name} · {pet.monitor.name}" for pet in self.actor_pets]))
        if old_actor in self.actor_pets:
            self.actor.set_selected(self.actor_pets.index(old_actor) + 1)

        # Update active pets list
        pet_keys = [(pet, pet.catalog.image_set_dir.name, pet.monitor.name) for pet in manager.pets]
        if self.listed_pets == pet_keys:
            return
        self.listed_pets = pet_keys
        while (child := self.pet_list.get_first_child()) is not None:
            self.pet_list.remove(child)

        if not manager.pets:
            empty = Gtk.Label(label="当前桌面暂无桌宠，点击角色素材页“+ 召唤”添加", xalign=0.5)
            empty.add_css_class("neuro-empty-hint")
            self.pet_list.append(empty)
        else:
            for number, pet in enumerate(manager.pets, 1):
                item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                item.add_css_class("neuro-card")
                top_row = Gtk.Box(spacing=8)
                avatar = self._make_avatar(pet.catalog.image_set_dir / "shime1.png")
                top_row.append(avatar)
                name = f"{number}. {pet.catalog.image_set_dir.name} · {pet.monitor.name}"
                top_row.append(Gtk.Label(label=name, xalign=0, hexpand=True))
                top_row.append(self._button("再召唤", lambda pet=pet: manager.resummon(pet)))
                remove_btn = self._button("移除", pet.close)
                remove_btn.add_css_class("destructive-action")
                top_row.append(remove_btn)
                item.append(top_row)
                item.append(SplitControls(manager,
                    lambda pet=pet: (pet.runtime.allow_split, pet.runtime.split_probability),
                    lambda enabled, probability, pet=pet: manager.set_pet_split(pet, enabled, probability)))
                self.pet_list.append(item)

    def show_manager(self) -> None:
        self._run(self.refresh_windows)
        self.refresh()
        point = cursor_pos()
        monitor = monitor_for_point(load_monitors(), point.x, point.y)
        outputs = Gdk.Display.get_default().get_monitors()
        for index in range(outputs.get_n_items()):
            output = outputs.get_item(index)
            if output.get_connector() == monitor.name:
                Gtk4LayerShell.set_monitor(self, output)
                break
        area = monitor.work_area
        width, height = max(520, self.get_width()), max(640, self.get_height())
        x = max(area.left, min(area.right - width, point.x - monitor.x - width + 20))
        y = max(area.top, min(area.bottom - height, point.y - monitor.y + 10))
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, x)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, y)
        self.present()
