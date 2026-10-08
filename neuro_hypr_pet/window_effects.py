from gi.repository import GLib

from neuro_hypr_pet.hyprland import (Rect, load_monitors, load_windows, minimize_window, monitor_for_point,
                                     move_window_to_rect, resize_window, set_window_animation_disabled,
                                     window_move_animation_ms)


def animate_minimize(window, manager, animation_disabled: str) -> None:
    placement = manager.application._neuro_hypr_window_originals[window.address]
    monitor = monitor_for_point(load_monitors(), window.x + window.width // 2, window.y + window.height // 2)
    area = monitor.global_work_area
    duration = window_move_animation_ms()
    set_window_animation_disabled(window, "false")
    resize_window(window, 100, 80)
    move_window_to_rect(window, Rect(area.x + area.width // 2 - 50, area.bottom - 80, 100, 80))

    def target():
        return next((item for item in load_windows() if item.address == window.address), None)

    def finish():
        manager.minimizations.pop(window.address, None)
        current = target()
        if current is not None:
            try:
                minimize_window(current, placement)
            finally:
                set_window_animation_disabled(current, animation_disabled)
            manager.message = "已最小化窗口"
            manager.changed()
        return False

    source = GLib.timeout_add(duration + 60, finish)

    def cancel():
        GLib.source_remove(source)
        current = target()
        if current is not None:
            set_window_animation_disabled(current, animation_disabled)

    manager.minimizations[window.address] = cancel
