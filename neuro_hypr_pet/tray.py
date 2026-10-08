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
  <property name="IconName" type="s" access="read"/>
  <property name="IconPixmap" type="a(iiay)" access="read"/>
  <property name="OverlayIconName" type="s" access="read"/>
  <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionIconName" type="s" access="read"/>
  <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionMovieName" type="s" access="read"/>
  <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <signal name="NewToolTip"/>
</interface></node>"""


class PetTray:
    def __init__(self, manager, show_manager) -> None:
        self.manager = manager
        self.show_manager = show_manager
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        interface = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        self.registration = self.connection.register_object(ITEM_PATH, interface, self._method, self._property, None)
        self.watch = Gio.bus_watch_name_on_connection(self.connection, WATCHER, Gio.BusNameWatcherFlags.NONE, self._appeared, self._vanished)
        manager.listeners.append(self.changed)

    def _property(self, _connection, _sender, _path, _interface, name):
        if name == "ToolTip":
            state = "已暂停" if self.manager.paused else "运行中"
            return GLib.Variant("(sa(iiay)ss)", ("", [], "Neuroling", f"{len(self.manager.pets)} 只桌宠 · {state}"))
        if name.endswith("Pixmap"):
            return GLib.Variant("a(iiay)", [])
        if name == "WindowId":
            return GLib.Variant("u", 0)
        if name == "ItemIsMenu":
            return GLib.Variant("b", False)
        icon = self.manager.collection / "img" / "Neuron" / "shime1.png"
        values = {
            "Category": "ApplicationStatus", "Id": "neuro-hypr-pet", "Title": "Neuroling",
            "Status": "Active", "IconName": str(icon) if icon.is_file() else "face-smile",
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
        self.connection.emit_signal(None, ITEM_PATH, ITEM_INTERFACE, "NewToolTip", None)

    def close(self) -> None:
        Gio.bus_unwatch_name(self.watch)
        self.connection.unregister_object(self.registration)
