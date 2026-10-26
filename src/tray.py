from __future__ import annotations

import sys
from gi.repository import Gio, GLib


ITEM_PATH = "/StatusNotifierItem"
ITEM_INTERFACE = "org.kde.StatusNotifierItem"
WATCHER = "org.kde.StatusNotifierWatcher"

ITEM_XML = """<node><interface name="org.kde.StatusNotifierItem">
  <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="WindowId" type="u" access="read"/>
  <property name="IconThemePath" type="s" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="IconPixmap" type="a(iiay)" access="read"/>
  <property name="OverlayIconName" type="s" access="read"/>
  <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionIconName" type="s" access="read"/>
  <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionMovieName" type="s" access="read"/>
  <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <signal name="NewTitle"/>
  <signal name="NewIcon"/>
  <signal name="NewIconThemePath"/>
  <signal name="NewStatus"><arg type="s" name="status"/></signal>
  <signal name="NewToolTip"/>
</interface></node>"""


class PetTray:
    def __init__(self, manager, show_manager) -> None:
        self.manager = manager
        self.show_manager = show_manager
        self._cached_pixmap = None
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        interface = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        self.registration = self.connection.register_object(ITEM_PATH, interface, self._method, self._property, None)
        self.watch = Gio.bus_watch_name_on_connection(self.connection, WATCHER, Gio.BusNameWatcherFlags.NONE, self._appeared, self._vanished)
        manager.listeners.append(self.changed)

    def _get_pixmap(self):
        if self._cached_pixmap is not None:
            return self._cached_pixmap
        try:
            from gi.repository import GdkPixbuf
            icon_path = self.manager.collection / "img" / "Neuron" / "shime1.png"
            if not icon_path.is_file():
                return []
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_path), 22, 22, True)
            w, h, rowstride = pixbuf.get_width(), pixbuf.get_height(), pixbuf.get_rowstride()
            n_channels = pixbuf.get_n_channels()
            pixels = pixbuf.get_pixels()

            # Network byte order ARGB32 (A, R, G, B)
            byte_list = bytearray(w * h * 4)
            idx = 0
            for y in range(h):
                row_start = y * rowstride
                for x in range(w):
                    p = row_start + x * n_channels
                    r, g, b = pixels[p], pixels[p + 1], pixels[p + 2]
                    a = pixels[p + 3] if n_channels == 4 else 255
                    byte_list[idx] = a
                    byte_list[idx + 1] = r
                    byte_list[idx + 2] = g
                    byte_list[idx + 3] = b
                    idx += 4
            self._cached_pixmap = [(w, h, byte_list)]
            return self._cached_pixmap
        except Exception:
            return []

    def _property(self, _connection, _sender, _path, _interface, name):
        count = len(self.manager.pets)
        state = "已暂停" if self.manager.paused else "运行中"
        if name == "ToolTip":
            status_line = f"{count} 只桌宠 · {state}" if count > 0 else "桌面暂无桌宠"
            return GLib.Variant("(sa(iiay)ss)", ("", [], "Neuroling 桌面宠物", status_line))
        if name == "IconPixmap":
            return GLib.Variant("a(iiay)", self._get_pixmap())
        if name.endswith("Pixmap"):
            return GLib.Variant("a(iiay)", [])
        if name == "WindowId":
            return GLib.Variant("u", 0)
        if name == "ItemIsMenu":
            return GLib.Variant("b", False)
        if name == "Status":
            return GLib.Variant("s", "Active")
        icon = self.manager.collection / "img" / "Neuron" / "shime1.png"
        if name == "IconThemePath":
            return GLib.Variant("s", str(icon.parent) if icon.parent.is_dir() else "")
        values = {
            "Category": "ApplicationStatus", "Id": "neuro-hypr-pet", "Title": "Neuroling",
            "IconName": str(icon) if icon.is_file() else "face-smile",
        }
        return GLib.Variant("s", values.get(name, ""))

    def _method(self, _connection, _sender, _path, _interface, method, _parameters, invocation):
        if method != "Scroll":
            self.show_manager()
        invocation.return_value(None)

    def _appeared(self, connection, name, _owner) -> None:
        connection.call(name, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
                        GLib.Variant("(s)", (ITEM_PATH,)), None, Gio.DBusCallFlags.NONE, -1, None, self._registered)

    def _registered(self, connection, result) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as error:
            print(f"Tray registration failed: {error}", file=sys.stderr)
            self.show_manager()

    def _vanished(self, _connection, _name) -> None:
        self.show_manager()

    def changed(self) -> None:
        try:
            self.connection.emit_signal(None, ITEM_PATH, ITEM_INTERFACE, "NewToolTip", None)
            self.connection.emit_signal(None, ITEM_PATH, ITEM_INTERFACE, "NewStatus", GLib.Variant("(s)", ("Active",)))
            self.connection.emit_signal(None, ITEM_PATH, ITEM_INTERFACE, "NewIcon", None)
        except Exception:
            pass

    def close(self) -> None:
        Gio.bus_unwatch_name(self.watch)
        self.connection.unregister_object(self.registration)
