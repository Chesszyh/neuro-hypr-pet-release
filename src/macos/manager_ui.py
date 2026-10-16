from __future__ import annotations

import random
from pathlib import Path

import AppKit as AK
import Foundation as F
import objc

from src.assets import DOWNLOAD_PAGE, import_collection
from src.controller import COMPANION_CHOICES, manual_behavior_label
from src.macos import login


class FlippedView(AK.NSView):
    def isFlipped(self):
        return True


class ManagerUI(F.NSObject):
    @objc.python_method
    def configure(self, application):
        self.application = application
        self.callbacks = {}
        self.buttons = {}
        self.material_rows = {}
        self._current_available = ()
        self._built = False
        self._cached_images = {}

        # Status Bar Item (Menu Extra)
        self.status = AK.NSStatusBar.systemStatusBar().statusItemWithLength_(AK.NSVariableStatusItemLength)
        self._tray_icon = None
        self._update_tray_icon(0, False)
        self._build_tray_menu()

        # Main Panel Window
        self.panel = AK.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((200, 150), (540, 660)),
            AK.NSWindowStyleMaskTitled | AK.NSWindowStyleMaskClosable | AK.NSWindowStyleMaskMiniaturizable,
            AK.NSBackingStoreBuffered,
            False,
        )
        self.panel.setTitle_('Neuro Pet')
        self.panel.setReleasedWhenClosed_(False)
        self.panel.setFloatingPanel_(True)

        return self

    @objc.python_method
    def _build_tray_menu(self):
        menu = AK.NSMenu.alloc().initWithTitle_('Neuro Pet')

        header = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Neuro Pet 桌面宠物', None, '')
        header.setEnabled_(False)
        menu.addItem_(header)

        self.tray_status_item = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('○ 暂无活跃桌宠', None, '')
        self.tray_status_item.setEnabled_(False)
        menu.addItem_(self.tray_status_item)
        menu.addItem_(AK.NSMenuItem.separatorItem())

        self.add_menu_item(menu, '⚙️ 管理面板…', self.show)
        self.add_menu_item(menu, '🎲 召唤随机桌宠', self.spawn_random)
        menu.addItem_(AK.NSMenuItem.separatorItem())

        self.tray_pause_item = self.add_menu_item(
            menu, '⏸️ 暂停全部',
            lambda: self.application.manager and self.application.manager.set_paused(not self.application.manager.paused)
        )
        self.tray_follow_item = self.add_menu_item(
            menu, '🎯 跟随鼠标',
            lambda: self.application.manager and self.application.manager.set_following(not self.application.manager.following)
        )
        self.add_menu_item(menu, '🗑️ 移除全部桌宠', self.remove_all)
        menu.addItem_(AK.NSMenuItem.separatorItem())

        self.add_menu_item(
            menu, '🪟 还原搬动的窗口',
            lambda: self.application.manager and self.application.manager.restore_windows()
        )
        self.add_menu_item(menu, '📂 导入素材 ZIP…', self.import_zip)
        self.add_menu_item(
            menu, '🌐 下载 Neurolings 素材',
            lambda: AK.NSWorkspace.sharedWorkspace().openURL_(F.NSURL.URLWithString_(DOWNLOAD_PAGE))
        )
        menu.addItem_(AK.NSMenuItem.separatorItem())
        self.add_menu_item(menu, '退出', self.application.quit)

        self.static_callbacks = dict(self.callbacks)
        self.status.setMenu_(menu)

    @objc.python_method
    def add_menu_item(self, menu, title, callback, checked=False):
        item = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, 'invoke:', '')
        item.setTarget_(self)
        item.setTag_(len(self.callbacks) + 1)
        self.callbacks[item.tag()] = callback
        item.setState_(AK.NSControlStateValueOn if checked else AK.NSControlStateValueOff)
        menu.addItem_(item)
        return item

    def invoke_(self, sender):
        try:
            self.application.message = ''
            tag = sender.tag()
            if tag in self.callbacks:
                self.callbacks[tag]()
        except Exception as error:
            self.set_status(str(error), is_error=True)
            self.application.report_error(error)

    @objc.python_method
    def register_action(self, control, callback):
        tag = len(self.callbacks) + 1
        self.callbacks[tag] = callback
        control.setTarget_(self)
        control.setAction_('invoke:')
        control.setTag_(tag)
        return control

    @objc.python_method
    def _make_card(self, parent, rect):
        box = AK.NSBox.alloc().initWithFrame_(rect)
        box.setBoxType_(AK.NSBoxCustom)
        box.setTitlePosition_(AK.NSNoTitle)
        box.setCornerRadius_(10.0)
        box.setBorderWidth_(1.0)
        box.setBorderColor_(AK.NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.12))
        box.setFillColor_(AK.NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.04))
        content = FlippedView.alloc().initWithFrame_(((0, 0), (rect[1][0], rect[1][1])))
        box.setContentView_(content)
        parent.addSubview_(box)
        return content

    @objc.python_method
    def _build_ui(self):
        self.content_view = FlippedView.alloc().initWithFrame_(((0, 0), (540, 660)))
        self.panel.setContentView_(self.content_view)

        # 1. Top Header Bar
        title_lbl = AK.NSTextField.labelWithString_('Neuro Pet')
        title_lbl.setFrame_(((20, 16), (110, 24)))
        title_lbl.setFont_(AK.NSFont.boldSystemFontOfSize_(18.0))
        self.content_view.addSubview_(title_lbl)

        self.status_badge = AK.NSTextField.labelWithString_('○ 桌面暂无桌宠')
        self.status_badge.setFrame_(((135, 20), (220, 20)))
        self.status_badge.setFont_(AK.NSFont.systemFontOfSize_weight_(12.0, AK.NSFontWeightMedium))
        self.status_badge.setTextColor_(AK.NSColor.secondaryLabelColor())
        self.content_view.addSubview_(self.status_badge)

        self.btn_random_top = AK.NSButton.alloc().initWithFrame_(((365, 15), (95, 26)))
        self.btn_random_top.setTitle_('🎲 随机召唤')
        self.btn_random_top.setBezelStyle_(AK.NSBezelStyleRounded)
        self.register_action(self.btn_random_top, self.spawn_random)
        self.content_view.addSubview_(self.btn_random_top)

        self.btn_clean_top = AK.NSButton.alloc().initWithFrame_(((465, 15), (55, 26)))
        self.btn_clean_top.setTitle_('清屏')
        self.btn_clean_top.setBezelStyle_(AK.NSBezelStyleRounded)
        self.register_action(self.btn_clean_top, self.remove_all)
        self.content_view.addSubview_(self.btn_clean_top)

        # 2. Section Header: Character Library
        lib_title = AK.NSTextField.labelWithString_('角色素材库')
        lib_title.setFrame_(((20, 52), (90, 20)))
        lib_title.setFont_(AK.NSFont.boldSystemFontOfSize_(13.0))
        self.content_view.addSubview_(lib_title)

        self.lib_count = AK.NSTextField.labelWithString_('(共 0 种)')
        self.lib_count.setFrame_(((95, 53), (80, 18)))
        self.lib_count.setFont_(AK.NSFont.systemFontOfSize_(11.0))
        self.lib_count.setTextColor_(AK.NSColor.secondaryLabelColor())
        self.content_view.addSubview_(self.lib_count)

        self.btn_select_all = AK.NSButton.alloc().initWithFrame_(((395, 50), (60, 22)))
        self.btn_select_all.setTitle_('全选')
        self.btn_select_all.setBezelStyle_(AK.NSBezelStyleInline)
        self.register_action(
            self.btn_select_all,
            lambda: self.application.manager and self.application.manager.set_selection(self.application.manager.available)
        )
        self.content_view.addSubview_(self.btn_select_all)

        self.btn_select_none = AK.NSButton.alloc().initWithFrame_(((460, 50), (60, 22)))
        self.btn_select_none.setTitle_('全不选')
        self.btn_select_none.setBezelStyle_(AK.NSBezelStyleInline)
        self.register_action(
            self.btn_select_none,
            lambda: self.application.manager and self.application.manager.set_selection(())
        )
        self.content_view.addSubview_(self.btn_select_none)

        # Character Scroll Card
        self.scroll_card = AK.NSBox.alloc().initWithFrame_(((20, 76), (500, 200)))
        self.scroll_card.setBoxType_(AK.NSBoxCustom)
        self.scroll_card.setTitlePosition_(AK.NSNoTitle)
        self.scroll_card.setCornerRadius_(8.0)
        self.scroll_card.setBorderWidth_(1.0)
        self.scroll_card.setBorderColor_(AK.NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.12))
        self.scroll_card.setFillColor_(AK.NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.25))
        self.content_view.addSubview_(self.scroll_card)

        self.scroll_view = AK.NSScrollView.alloc().initWithFrame_(((0, 0), (500, 200)))
        self.scroll_view.setHasVerticalScroller_(True)
        self.scroll_view.setDrawsBackground_(False)
        self.scroll_card.setContentView_(self.scroll_view)

        # Selection Toolbar under scroll area
        self.btn_spawn_sel = AK.NSButton.alloc().initWithFrame_(((20, 284), (150, 32)))
        self.btn_spawn_sel.setTitle_('➕ 召唤所选')
        self.btn_spawn_sel.setBezelStyle_(AK.NSBezelStyleRounded)
        self.btn_spawn_sel.setKeyEquivalent_('\r')
        self.register_action(self.btn_spawn_sel, self.spawn_selected)
        self.content_view.addSubview_(self.btn_spawn_sel)

        self.btn_import_zip = AK.NSButton.alloc().initWithFrame_(((178, 284), (140, 32)))
        self.btn_import_zip.setTitle_('📂 导入素材 ZIP…')
        self.btn_import_zip.setBezelStyle_(AK.NSBezelStyleRounded)
        self.register_action(self.btn_import_zip, self.import_zip)
        self.content_view.addSubview_(self.btn_import_zip)

        self.btn_download = AK.NSButton.alloc().initWithFrame_(((326, 284), (194, 32)))
        self.btn_download.setTitle_('🌐 下载更多素材…')
        self.btn_download.setBezelStyle_(AK.NSBezelStyleRounded)
        self.register_action(
            self.btn_download,
            lambda: AK.NSWorkspace.sharedWorkspace().openURL_(F.NSURL.URLWithString_(DOWNLOAD_PAGE))
        )
        self.content_view.addSubview_(self.btn_download)

        # 3. Section: Global Desktop Controls Card
        card_ctrl = self._make_card(self.content_view, ((20, 326), (500, 68)))
        lbl_ctrl = AK.NSTextField.labelWithString_('全局桌面控制')
        lbl_ctrl.setFrame_(((14, 8), (120, 18)))
        lbl_ctrl.setFont_(AK.NSFont.boldSystemFontOfSize_(12.0))
        lbl_ctrl.setTextColor_(AK.NSColor.secondaryLabelColor())
        card_ctrl.addSubview_(lbl_ctrl)

        self.cb_pause = AK.NSButton.alloc().initWithFrame_(((14, 34), (115, 22)))
        self.cb_pause.setButtonType_(AK.NSButtonTypeSwitch)
        self.cb_pause.setTitle_('⏸️ 暂停全部')
        self.register_action(
            self.cb_pause,
            lambda: self.application.manager and self.toggle_pause()
        )
        card_ctrl.addSubview_(self.cb_pause)

        self.cb_follow = AK.NSButton.alloc().initWithFrame_(((140, 34), (115, 22)))
        self.cb_follow.setButtonType_(AK.NSButtonTypeSwitch)
        self.cb_follow.setTitle_('🎯 跟随鼠标')
        self.register_action(
            self.cb_follow,
            lambda: self.application.manager and self.toggle_follow()
        )
        card_ctrl.addSubview_(self.cb_follow)

        self.btn_remove_all = AK.NSButton.alloc().initWithFrame_(((370, 30), (115, 28)))
        self.btn_remove_all.setTitle_('🗑️ 移除全部')
        self.btn_remove_all.setBezelStyle_(AK.NSBezelStyleRounded)
        self.register_action(self.btn_remove_all, self.remove_all)
        card_ctrl.addSubview_(self.btn_remove_all)

        # 4. Section: Behavior & Physics Card
        card_behav = self._make_card(self.content_view, ((20, 404), (500, 96)))
        lbl_behav = AK.NSTextField.labelWithString_('行为偏好与物理设置')
        lbl_behav.setFrame_(((14, 8), (150, 18)))
        lbl_behav.setFont_(AK.NSFont.boldSystemFontOfSize_(12.0))
        lbl_behav.setTextColor_(AK.NSColor.secondaryLabelColor())
        card_behav.addSubview_(lbl_behav)

        # Row 1: Split
        self.cb_split = AK.NSButton.alloc().initWithFrame_(((14, 32), (125, 22)))
        self.cb_split.setButtonType_(AK.NSButtonTypeSwitch)
        self.cb_split.setTitle_('🧬 允许自主分裂')
        self.register_action(
            self.cb_split,
            lambda: self.application.manager and self.application.manager.set_split_defaults(
                not self.application.manager.allow_split, self.application.manager.split_probability
            )
        )
        card_behav.addSubview_(self.cb_split)

        lbl_prob = AK.NSTextField.labelWithString_('概率:')
        lbl_prob.setFrame_(((145, 34), (40, 18)))
        lbl_prob.setFont_(AK.NSFont.systemFontOfSize_(12.0))
        card_behav.addSubview_(lbl_prob)

        self.pop_prob = AK.NSPopUpButton.alloc().initWithFrame_pullsDown_(((185, 30), (110, 26)), False)
        self.pop_prob.addItemsWithTitles_(['素材默认', '0%', '10%', '25%', '50%', '100%'])
        self.pop_prob.setTarget_(self)
        self.pop_prob.setAction_('probability:')
        card_behav.addSubview_(self.pop_prob)

        self.btn_apply_all = AK.NSButton.alloc().initWithFrame_(((370, 28), (115, 28)))
        self.btn_apply_all.setTitle_('应用到全部')
        self.btn_apply_all.setBezelStyle_(AK.NSBezelStyleRounded)
        self.register_action(
            self.btn_apply_all,
            lambda: self.application.manager and (
                self.application.manager.apply_split_to_all(
                    self.application.manager.allow_split, self.application.manager.split_probability
                ),
                self.set_status('已将分裂设置应用至当前所有桌宠')
            )
        )
        card_behav.addSubview_(self.btn_apply_all)

        # Row 2: Falling Speed
        lbl_speed = AK.NSTextField.labelWithString_('⚡ 下落重力速度:')
        lbl_speed.setFrame_(((14, 66), (110, 18)))
        lbl_speed.setFont_(AK.NSFont.systemFontOfSize_(12.0))
        card_behav.addSubview_(lbl_speed)

        self.pop_speed = AK.NSPopUpButton.alloc().initWithFrame_pullsDown_(((125, 62), (170, 26)), False)
        self.pop_speed.addItemsWithTitles_(['0.25× (轻浮)', '0.5× (轻缓)', '0.7× (默认)', '1.0× (自然)', '1.5× (快速)'])
        self.pop_speed.setTarget_(self)
        self.pop_speed.setAction_('fallSpeed:')
        card_behav.addSubview_(self.pop_speed)

        # 5. Section: Window Interaction & System Card
        card_win = self._make_card(self.content_view, ((20, 510), (500, 74)))
        lbl_win = AK.NSTextField.labelWithString_('窗口交互与系统')
        lbl_win.setFrame_(((14, 8), (120, 18)))
        lbl_win.setFont_(AK.NSFont.boldSystemFontOfSize_(12.0))
        lbl_win.setTextColor_(AK.NSColor.secondaryLabelColor())
        card_win.addSubview_(lbl_win)

        self.btn_win_menu = AK.NSButton.alloc().initWithFrame_(((14, 32), (135, 28)))
        self.btn_win_menu.setTitle_('🪟 窗口互动… ▾')
        self.btn_win_menu.setBezelStyle_(AK.NSBezelStyleRounded)
        self.register_action(self.btn_win_menu, self.window_menu)
        card_win.addSubview_(self.btn_win_menu)

        self.btn_restore_win = AK.NSButton.alloc().initWithFrame_(((155, 32), (150, 28)))
        self.btn_restore_win.setTitle_('↩️ 还原搬动的窗口')
        self.btn_restore_win.setBezelStyle_(AK.NSBezelStyleRounded)
        self.register_action(
            self.btn_restore_win,
            lambda: self.application.manager and self.restore_windows()
        )
        card_win.addSubview_(self.btn_restore_win)

        self.cb_login = AK.NSButton.alloc().initWithFrame_(((325, 35), (160, 22)))
        self.cb_login.setButtonType_(AK.NSButtonTypeSwitch)
        self.cb_login.setTitle_('🚀 登录时自动启动')
        self.register_action(self.cb_login, self.toggle_login)
        card_win.addSubview_(self.cb_login)

        # 6. Status & Notification Banner
        self.banner_box = AK.NSBox.alloc().initWithFrame_(((20, 594), (500, 48)))
        self.banner_box.setBoxType_(AK.NSBoxCustom)
        self.banner_box.setTitlePosition_(AK.NSNoTitle)
        self.banner_box.setCornerRadius_(8.0)
        self.banner_box.setBorderWidth_(1.0)
        self.banner_box.setBorderColor_(AK.NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.1))
        self.banner_box.setFillColor_(AK.NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.03))
        self.content_view.addSubview_(self.banner_box)

        banner_content = FlippedView.alloc().initWithFrame_(((0, 0), (500, 48)))
        self.banner_box.setContentView_(banner_content)

        self.message = AK.NSTextField.labelWithString_('')
        self.message.setFrame_(((12, 6), (476, 36)))
        self.message.setFont_(AK.NSFont.systemFontOfSize_(11.5))
        self.message.setTextColor_(AK.NSColor.secondaryLabelColor())
        self.message.setMaximumNumberOfLines_(2)
        self.message.setLineBreakMode_(AK.NSLineBreakByTruncatingTail)
        banner_content.addSubview_(self.message)

        self._built = True

    @objc.python_method
    def set_status(self, text, is_error=False):
        if not self._built:
            return
        if is_error:
            self.message.setStringValue_(f'⚠️ {text}')
            self.message.setTextColor_(AK.NSColor.systemRedColor())
        elif text:
            self.message.setStringValue_(f'ℹ️ {text}')
            self.message.setTextColor_(AK.NSColor.labelColor())
        else:
            self.message.setStringValue_('💡 提示：右键点击桌面的桌宠可唤出快捷动作菜单；点击角色旁“+ 召唤”可直接生成')
            self.message.setTextColor_(AK.NSColor.secondaryLabelColor())

    @objc.python_method
    def toggle_pause(self):
        manager = self.application.manager
        if not manager:
            return
        new_paused = not manager.paused
        manager.set_paused(new_paused)
        self.set_status('已暂停所有桌宠活动' if new_paused else '已恢复桌宠自主活动')

    @objc.python_method
    def toggle_follow(self):
        manager = self.application.manager
        if not manager:
            return
        new_follow = not manager.following
        manager.set_following(new_follow)
        self.set_status('已开启跟随鼠标（靠近停下）' if new_follow else '已恢复桌宠自主漫步')

    @objc.python_method
    def restore_windows(self):
        manager = self.application.manager
        if not manager:
            return
        manager.restore_windows()
        self.set_status(manager.message)

    @objc.python_method
    def toggle_login(self):
        try:
            target = not login.enabled()
            login.set_enabled(target)
            self.cb_login.setState_(AK.NSControlStateValueOn if target else AK.NSControlStateValueOff)
        except Exception as error:
            self.set_status(str(error), is_error=True)

    @objc.python_method
    def _get_tray_icon(self):
        if self._tray_icon is not None:
            return self._tray_icon
        collection = getattr(self.application, 'collection', None)
        paths_to_check = []
        if collection:
            paths_to_check.extend([
                collection / 'img' / 'icon.png',
                collection / 'img' / 'Neuron' / 'shime1.png',
                collection / 'img' / 'Neuroling' / 'shime1.png',
            ])
        repo_icon = Path(__file__).resolve().parents[2] / 'refs' / 'The-Neuroling-Collection' / 'img' / 'icon.png'
        paths_to_check.append(repo_icon)

        for p in paths_to_check:
            if p.exists():
                img = AK.NSImage.alloc().initWithContentsOfFile_(str(p))
                if img:
                    img.setSize_((18, 18))
                    self._tray_icon = img
                    return img
        return None

    @objc.python_method
    def _update_tray_icon(self, active_count, paused):
        tray_icon = self._get_tray_icon()
        btn = self.status.button()
        if not btn:
            return
        if tray_icon:
            btn.setImage_(tray_icon)
            btn.setImagePosition_(AK.NSImageLeft)
            if active_count > 0:
                suffix = ' ⏸️' if paused else f' {active_count}'
                btn.setTitle_(suffix)
            else:
                btn.setTitle_('')
        else:
            btn.setImage_(None)
            suffix = f' ({active_count})' if active_count > 0 else ''
            btn.setTitle_(f'Neuro{suffix}')

        if active_count > 0:
            state_text = f'已暂停 ({active_count} 只)' if paused else f'{active_count} 只活动中'
            btn.setToolTip_(f'Neuro Pet ({state_text})')
        else:
            btn.setToolTip_('Neuro Pet 桌面宠物')

    @objc.python_method
    def _load_character_image(self, name):
        if name in self._cached_images:
            return self._cached_images[name]
        collection = getattr(self.application, 'collection', None)
        if collection:
            img_path = collection / 'img' / name / 'shime1.png'
            if img_path.exists():
                img = AK.NSImage.alloc().initWithContentsOfFile_(str(img_path))
                if img:
                    self._cached_images[name] = img
                    return img
        return None

    @objc.python_method
    def _rebuild_material_list(self):
        manager = self.application.manager
        names = manager.available if manager else ()
        self._current_available = tuple(names)
        self.buttons = {}
        self.material_rows = {}

        row_height = 48
        total_height = max(200, row_height * len(names))
        document = FlippedView.alloc().initWithFrame_(((0, 0), (480, total_height)))
        self.scroll_view.setDocumentView_(document)

        if not names:
            empty_lbl = AK.NSTextField.labelWithString_('暂无可用的素材角色，请先导入 ZIP 或下载素材。')
            empty_lbl.setFrame_(((20, 85), (440, 24)))
            empty_lbl.setFont_(AK.NSFont.systemFontOfSize_(12.0))
            empty_lbl.setTextColor_(AK.NSColor.secondaryLabelColor())
            document.addSubview_(empty_lbl)
            return

        for index, name in enumerate(names):
            selected = name in manager.selected
            row_y = index * row_height
            row = FlippedView.alloc().initWithFrame_(((0, row_y), (480, row_height)))
            document.addSubview_(row)

            # Checkbox for batch selection
            cb = AK.NSButton.alloc().initWithFrame_(((10, 14), (20, 20)))
            cb.setButtonType_(AK.NSButtonTypeSwitch)
            cb.setTitle_('')
            cb.setState_(AK.NSControlStateValueOn if selected else AK.NSControlStateValueOff)
            self.register_action(cb, lambda name=name: self.toggle_selection(name))
            row.addSubview_(cb)
            self.buttons[name] = cb

            # Thumbnail avatar
            avatar = self._load_character_image(name)
            if avatar:
                iv = AK.NSImageView.alloc().initWithFrame_(((34, 6), (36, 36)))
                iv.setImage_(avatar)
                iv.setImageScaling_(AK.NSImageScaleProportionallyUpOrDown)
                row.addSubview_(iv)

            # Character name
            name_lbl = AK.NSTextField.labelWithString_(name)
            name_lbl.setFrame_(((78, 8), (220, 18)))
            name_lbl.setFont_(AK.NSFont.boldSystemFontOfSize_(13.0))
            row.addSubview_(name_lbl)

            # Active status badge
            badge = AK.NSTextField.labelWithString_('未召唤')
            badge.setFrame_(((78, 26), (220, 16)))
            badge.setFont_(AK.NSFont.systemFontOfSize_(11.0))
            badge.setTextColor_(AK.NSColor.tertiaryLabelColor())
            row.addSubview_(badge)

            # Quick spawn button
            btn_spawn = AK.NSButton.alloc().initWithFrame_(((405, 11), (65, 26)))
            btn_spawn.setTitle_('+ 召唤')
            btn_spawn.setBezelStyle_(AK.NSBezelStyleRounded)
            self.register_action(btn_spawn, lambda name=name: self.spawn_one(name))
            row.addSubview_(btn_spawn)

            # Row separator
            sep = AK.NSBox.alloc().initWithFrame_(((10, row_height - 1), (460, 1)))
            sep.setBoxType_(AK.NSBoxSeparator)
            row.addSubview_(sep)

            self.material_rows[name] = {
                'row': row,
                'checkbox': cb,
                'badge': badge,
                'spawn_button': btn_spawn,
            }

    @objc.python_method
    def refresh(self):
        if not self._built:
            self._build_ui()

        manager = self.application.manager
        if not manager:
            self.lib_count.setStringValue_('(共 0 种)')
            self._rebuild_material_list()
            self.set_status('请先导入下载好的 Neurolings ZIP 素材包。')
            return

        names = manager.available
        self.lib_count.setStringValue_(f'(共 {len(names)} 种)')

        # Check if materials list changed
        if tuple(names) != self._current_available:
            self._rebuild_material_list()

        # Count active pets by character
        pet_counts = {}
        for pet in manager.pets:
            pname = pet.catalog.image_set_dir.name
            pet_counts[pname] = pet_counts.get(pname, 0) + 1

        # Update material rows states
        for name, widgets in self.material_rows.items():
            is_selected = name in manager.selected
            widgets['checkbox'].setState_(AK.NSControlStateValueOn if is_selected else AK.NSControlStateValueOff)
            count = pet_counts.get(name, 0)
            if count > 0:
                widgets['badge'].setStringValue_(f'● {count} 只在桌面活动')
                widgets['badge'].setTextColor_(AK.NSColor.systemGreenColor())
            else:
                widgets['badge'].setStringValue_('未召唤')
                widgets['badge'].setTextColor_(AK.NSColor.tertiaryLabelColor())

        # Update batch spawn button title
        sel_count = len(manager.selected)
        self.btn_spawn_sel.setTitle_(f'➕ 召唤所选 ({sel_count})' if sel_count > 0 else '➕ 召唤所选')

        # Update Header & Tray status
        active_count = len(manager.pets)
        is_paused = manager.paused
        if active_count == 0:
            self.status_badge.setStringValue_('○ 桌面暂无桌宠')
            self.status_badge.setTextColor_(AK.NSColor.secondaryLabelColor())
            self.tray_status_item.setTitle_('○ 桌面暂无桌宠')
        elif is_paused:
            self.status_badge.setStringValue_(f'⏸️ 已暂停：{active_count} 只桌宠')
            self.status_badge.setTextColor_(AK.NSColor.systemOrangeColor())
            self.tray_status_item.setTitle_(f'⏸️ 已暂停：{active_count} 只桌宠')
        else:
            self.status_badge.setStringValue_(f'● 桌面活动：{active_count} 只桌宠')
            self.status_badge.setTextColor_(AK.NSColor.systemGreenColor())
            self.tray_status_item.setTitle_(f'● 正在运行：{active_count} 只桌宠')

        self._update_tray_icon(active_count, is_paused)

        # Update controls
        self.cb_pause.setState_(AK.NSControlStateValueOn if manager.paused else AK.NSControlStateValueOff)
        self.tray_pause_item.setState_(AK.NSControlStateValueOn if manager.paused else AK.NSControlStateValueOff)

        self.cb_follow.setState_(AK.NSControlStateValueOn if manager.following else AK.NSControlStateValueOff)
        self.tray_follow_item.setState_(AK.NSControlStateValueOn if manager.following else AK.NSControlStateValueOff)

        self.cb_split.setState_(AK.NSControlStateValueOn if manager.allow_split else AK.NSControlStateValueOff)

        values = [None, 0, 10, 25, 50, 100]
        prob_idx = values.index(manager.split_probability) if manager.split_probability in values else 0
        self.pop_prob.selectItemAtIndex_(prob_idx)

        speeds = [.25, .5, .7, 1.0, 1.5]
        speed_idx = min(range(len(speeds)), key=lambda idx: abs(speeds[idx] - manager.fall_speed))
        self.pop_speed.selectItemAtIndex_(speed_idx)

        self.cb_login.setState_(AK.NSControlStateValueOn if login.enabled() else AK.NSControlStateValueOff)

        msg = self.application.message or manager.message
        self.set_status(msg)

    def probability_(self, sender):
        manager = self.application.manager
        if manager:
            values = [None, 0, 10, 25, 50, 100]
            idx = sender.indexOfSelectedItem()
            manager.set_split_defaults(manager.allow_split, values[idx] if idx < len(values) else None)

    def fallSpeed_(self, sender):
        manager = self.application.manager
        if manager:
            speeds = [.25, .5, .7, 1.0, 1.5]
            idx = sender.indexOfSelectedItem()
            if idx < len(speeds):
                manager.set_fall_speed(speeds[idx])

    @objc.python_method
    def toggle_selection(self, name):
        manager = self.application.manager
        if not manager:
            return
        selected = list(manager.selected)
        if name in selected:
            selected.remove(name)
        else:
            selected.append(name)
        manager.set_selection(selected)

    @objc.python_method
    def spawn_one(self, name):
        manager = self.application.manager
        if not manager:
            return
        try:
            manager.spawn(name)
            self.set_status(f'已召唤 {name}')
        except Exception as error:
            self.set_status(str(error), is_error=True)

    @objc.python_method
    def spawn_selected(self):
        manager = self.application.manager
        if not manager:
            return
        if not manager.selected:
            self.set_status('请先勾选需要召唤的角色素材', is_error=True)
            return
        count = len(manager.selected)
        manager.spawn_selected()
        self.set_status(f'已召唤所选角色（共 {count} 种）')

    @objc.python_method
    def spawn_random(self):
        manager = self.application.manager
        if not manager or not manager.available:
            self.set_status('没有可用的素材，请先导入素材', is_error=True)
            return
        name = random.choice(manager.available)
        try:
            manager.spawn(name)
            self.set_status(f'🎲 已随机召唤：{name}')
        except Exception as error:
            self.set_status(str(error), is_error=True)

    @objc.python_method
    def remove_all(self):
        manager = self.application.manager
        if not manager or not manager.pets:
            self.set_status('当前桌面没有活跃的桌宠')
            return
        count = len(manager.pets)
        manager.remove_all()
        self.set_status(f'已移除全部桌面桌宠（共 {count} 只）')

    @objc.python_method
    def window_menu(self):
        from src.macos.accessibility import is_trusted
        if not is_trusted(prompt=True):
            self.set_status('请在“系统设置 -> 隐私与安全性 -> 辅助功能”中允许 Neuro Pet', is_error=True)
            return
        manager = self.application.manager
        if not manager:
            return
        windows = manager.interactive_windows()
        if not windows:
            self.set_status('当前没有可交互的普通应用窗口', is_error=True)
            return

        menu = AK.NSMenu.alloc().initWithTitle_('窗口互动')
        self.add_menu_item(menu, '🎲 随机搬运窗口', lambda: manager.interact(throw=False))
        self.add_menu_item(menu, '🚀 随机抛出窗口', lambda: manager.interact(throw=True))
        menu.addItem_(AK.NSMenuItem.separatorItem())

        for window in windows:
            submenu = AK.NSMenu.alloc().initWithTitle_(window.title)
            display_title = (window.class_name + ' — ' + window.title) if window.title else window.class_name
            if len(display_title) > 36:
                display_title = display_title[:35] + '…'
            item = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(display_title, None, '')
            item.setSubmenu_(submenu)
            menu.addItem_(item)
            for title, throw, minimize in [
                ('🖐️ 搬运窗口', False, False),
                ('🚀 抛出窗口', True, False),
                ('📦 抛出并最小化', True, True)
            ]:
                self.add_menu_item(
                    submenu, title,
                    lambda address=window.address, throw=throw, minimize=minimize:
                    manager.interact(address=address, throw=throw, minimize=minimize)
                )

        btn_frame = self.btn_win_menu.frame()
        menu.popUpMenuPositioningItem_atLocation_inView_(
            None,
            (btn_frame.origin.x, btn_frame.origin.y + btn_frame.size.height + 4),
            self.btn_win_menu.superview()
        )

    @objc.python_method
    def show(self):
        self.refresh()
        self.panel.center()
        self.panel.makeKeyAndOrderFront_(None)
        AK.NSApp.activateIgnoringOtherApps_(True)

    @objc.python_method
    def import_zip(self):
        chooser = AK.NSOpenPanel.openPanel()
        chooser.setCanChooseDirectories_(False)
        chooser.setAllowsMultipleSelection_(False)
        chooser.setAllowedFileTypes_(['zip'])
        if chooser.runModal() != AK.NSModalResponseOK:
            return
        try:
            names = import_collection(Path(chooser.URL().path()), self.application.collection)
            self.application.attach_manager()
            self._cached_images.clear()
            self.set_status('已成功导入角色素材：' + '、'.join(names))
            self.show()
        except Exception as error:
            self.set_status(f'导入失败：{error}', is_error=True)
            self.application.report_error(error)

    @objc.python_method
    def pet_menu(self, pet, event, view):
        manager = self.application.manager
        pet_name = pet.catalog.image_set_dir.name
        menu = AK.NSMenu.alloc().initWithTitle_(pet_name)
        menu.setMinimumWidth_(220)

        header = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f'🐾 {pet_name}', None, '')
        header.setEnabled_(False)
        menu.addItem_(header)
        menu.addItem_(AK.NSMenuItem.separatorItem())

        self.add_menu_item(menu, '➕ 再召唤一只', lambda: manager.resummon(pet))
        self.add_menu_item(menu, '🎯 只保留这只', lambda: manager.keep_one(pet))
        self.add_menu_item(menu, '❌ 移除这只', pet.close)

        companions_added = False
        for image_set, label, choices in COMPANION_CHOICES:
            name = next((name for name in choices if name in manager.available), None)
            if name:
                if not companions_added:
                    menu.addItem_(AK.NSMenuItem.separatorItem())
                    companions_added = True
                self.add_menu_item(menu, f'👯 {label}', lambda name=name: pet.summon_companion(name))

        menu.addItem_(AK.NSMenuItem.separatorItem())

        # Manual behaviors submenu
        behaviors = pet.runtime.available_manual_behaviors()
        if behaviors:
            actions_menu = AK.NSMenu.alloc().initWithTitle_('动作')
            actions_item = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('⚡ 触发动作', None, '')
            actions_item.setSubmenu_(actions_menu)
            menu.addItem_(actions_item)
            for name in behaviors:
                self.add_menu_item(
                    actions_menu, manual_behavior_label(name),
                    lambda name=name: pet.runtime.start_manual_behavior(name)
                )

        # Splitting submenu
        split_menu = AK.NSMenu.alloc().initWithTitle_('分裂设置')
        split_item = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('🧬 分裂设置', None, '')
        split_item.setSubmenu_(split_menu)
        menu.addItem_(split_item)

        self.add_menu_item(
            split_menu, '允许分裂',
            lambda: manager.set_pet_split(pet, not pet.runtime.allow_split, pet.runtime.split_probability),
            checked=pet.runtime.allow_split
        )
        split_menu.addItem_(AK.NSMenuItem.separatorItem())
        for title, probability in [
            ('素材默认', None), ('0%', 0), ('10%', 10), ('25%', 25), ('50%', 50), ('100%', 100)
        ]:
            self.add_menu_item(
                split_menu, title,
                lambda probability=probability: manager.set_pet_split(pet, pet.runtime.allow_split, probability),
                checked=pet.runtime.split_probability == probability
            )

        menu.addItem_(AK.NSMenuItem.separatorItem())
        self.add_menu_item(menu, '⚙️ 管理面板…', self.show)

        self.context = menu
        point = view.window().convertPointToScreen_(event.locationInWindow())
        menu.popUpMenuPositioningItem_atLocation_inView_(None, point, None)

    @objc.python_method
    def close(self):
        AK.NSStatusBar.systemStatusBar().removeStatusItem_(self.status)
        self.panel.close()
