from __future__ import annotations

import subprocess
from gi.repository import Gdk, Gtk, Gtk4LayerShell, Pango

from neuro_hypr_pet.hyprland import cursor_pos, load_monitors, monitor_for_point


class ManagerPopup(Gtk.ApplicationWindow):
    def __init__(self, manager) -> None:
        super().__init__(application=manager.application)
        self.manager = manager
        self.set_title("Neuroling 管理")
        self.set_default_size(480, 560)
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
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(root, f"set_margin_{side}")(14)
        self.set_child(root)
        heading = Gtk.Box(spacing=8)
        title = Gtk.Label(label="Neuroling", xalign=0, hexpand=True)
        title.add_css_class("title-3")
        heading.append(title)
        dismiss = Gtk.Button(label="×", tooltip_text="收起")
        dismiss.add_css_class("flat")
        dismiss.connect("clicked", self._hide)
        heading.append(dismiss)
        root.append(heading)
        self.summary = Gtk.Label(xalign=0)
        root.append(self.summary)
        controls = Gtk.Box(spacing=8)
        root.append(controls)
        self.pause = self._button("暂停", lambda: manager.set_paused(not manager.paused))
        controls.append(self.pause)
        self.follow = Gtk.ToggleButton(label="全部跟随鼠标")
        self.follow.set_tooltip_text("沿屏幕底部或窗口顶边追随鼠标，靠近后停下；再次点击恢复自主活动")
        self.follow.connect("toggled", self._follow)
        controls.append(self.follow)
        controls.append(self._button("只留一只", manager.keep_one))
        controls.append(self._button("移除全部", manager.remove_all))
        self.split = Gtk.CheckButton(label="允许分裂成两只")
        self.split.connect("toggled", self._split_changed)
        root.append(self.split)
        tabs = Gtk.Stack()
        tabs.set_vexpand(True)
        switcher = Gtk.StackSwitcher(stack=tabs, halign=Gtk.Align.FILL)
        switcher.set_hexpand(True)
        root.append(switcher)
        root.append(tabs)
        tabs.add_titled(self._materials(), "materials", "素材")
        self.pet_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tabs.add_titled(self._scroll(self.pet_list), "pets", "桌宠")
        tabs.add_titled(self._window_actions(), "windows", "窗口互动")
        self.message = Gtk.Label(xalign=0, wrap=True)
        root.append(self.message)
        quit_button = self._button("退出程序", manager.application.quit)
        quit_button.set_halign(Gtk.Align.END)
        root.append(quit_button)
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
            self.manager.message = str(error)
            self.manager.changed()

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

    def _materials(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        selection = Gtk.Box(spacing=8)
        selection.append(self._button("全选", lambda: self.manager.set_selection(self.manager.available)))
        selection.append(self._button("全不选", lambda: self.manager.set_selection(())))
        panel.append(selection)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.material_checks = {}
        self._refreshing_selection = False
        for name in self.manager.available:
            check = Gtk.CheckButton(label=name)
            check.set_active(name in self.manager.selected)
            self.material_checks[name] = check
            check.connect("toggled", self._selection_changed)
            rows.append(check)
        panel.append(self._scroll(rows))
        self.summon = self._button("召唤所选", self.manager.spawn_selected)
        self.summon.add_css_class("suggested-action")
        panel.append(self.summon)
        return panel

    def _selection_changed(self, _check) -> None:
        if not self._refreshing_selection:
            self._run(lambda: self.manager.set_selection(name for name, check in self.material_checks.items() if check.get_active()))

    def _split_changed(self, button) -> None:
        if button.get_active() != self.manager.allow_split:
            self._run(lambda: self.manager.set_allow_split(button.get_active()))

    def _follow(self, button) -> None:
        if button.get_active() != self.manager.following:
            self._run(lambda: self.manager.set_following(button.get_active()))

    def _window_actions(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.append(Gtk.Label(label="执行桌宠", xalign=0))
        self.actor = self._dropdown()
        self.actor_pets = []
        panel.append(self.actor)
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(label="目标窗口", xalign=0, hexpand=True))
        row.append(self._button("刷新", self.refresh_windows))
        panel.append(row)
        self.target = self._dropdown()
        self.target_windows = []
        panel.append(self.target)
        speed_row = Gtk.Box(spacing=8)
        speed_row.append(Gtk.Label(label="搬运 / 抛出速度（倍）", xalign=0, hexpand=True))
        self.speed = Gtk.SpinButton.new_with_range(0.5, 3.0, 0.25)
        self.speed.set_digits(2)
        self.speed.set_value(self.manager.window_speed)
        self.speed.connect("value-changed", self._speed_changed)
        speed_row.append(self.speed)
        panel.append(speed_row)
        buttons = Gtk.Box(spacing=8)
        self.carry = self._button("搬运所选窗口", lambda: self._interact(False))
        self.throw = self._button("抛出所选窗口", lambda: self._interact(True))
        buttons.append(self.carry)
        buttons.append(self.throw)
        buttons.append(self._button("随机抛出", lambda: self._interact(True, random_target=True)))
        panel.append(buttons)
        finish = Gtk.Box(spacing=8)
        self.minimize = self._button("抛出并最小化", lambda: self._interact(True, minimize=True))
        finish.append(self.minimize)
        finish.append(self._button("还原搬动的窗口", self.manager.restore_windows))
        panel.append(finish)
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

    def _speed_changed(self, spin) -> None:
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
        self.summary.set_label(f"{len(manager.pets)} 只桌宠 · {'已暂停' if manager.paused else '运行中'}")
        self.pause.set_label("继续" if manager.paused else "暂停")
        self.follow.set_active(manager.following)
        self.split.set_active(manager.allow_split)
        self.speed.set_value(manager.window_speed)
        self._refreshing_selection = True
        for name, check in self.material_checks.items():
            check.set_active(name in manager.selected)
        self._refreshing_selection = False
        self.summon.set_sensitive(bool(manager.selected))
        self.message.set_label(manager.message)
        index = self.actor.get_selected()
        old = self.actor_pets[index - 1] if 0 < index <= len(self.actor_pets) else None
        self.actor_pets = [pet for pet in manager.pets if not pet.transient]
        self.actor.set_model(Gtk.StringList.new(["自动选择"] + [f"{pet.catalog.image_set_dir.name} · {pet.monitor.name}" for pet in self.actor_pets]))
        if old in self.actor_pets:
            self.actor.set_selected(self.actor_pets.index(old) + 1)
        while (child := self.pet_list.get_first_child()) is not None:
            self.pet_list.remove(child)
        if not manager.pets:
            self.pet_list.append(Gtk.Label(label="暂无桌宠"))
        for pet in manager.pets:
            row = Gtk.Box(spacing=8)
            name = f"{pet.catalog.image_set_dir.name} · {pet.monitor.name}"
            row.append(Gtk.Label(label=name, xalign=0, hexpand=True))
            row.append(self._button("再召唤", lambda pet=pet: manager.resummon(pet)))
            row.append(self._button("移除", pet.close))
            self.pet_list.append(row)

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
        width, height = max(480, self.get_width()), max(560, self.get_height())
        x = max(area.left, min(area.right - width, point.x - monitor.x - width + 20))
        y = max(area.top, min(area.bottom - height, point.y - monitor.y + 10))
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, x)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, y)
        self.present()
