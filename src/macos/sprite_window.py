from __future__ import annotations

import AppKit as AK

from src.macos.desktop import coordinates, cursor_pos


def load_sprite(path):
    image = AK.NSImage.alloc().initWithContentsOfFile_(str(path))
    if image is None:
        raise ValueError(f'Cannot load pet image: {path}')
    representation = next((rep for rep in image.representations() if hasattr(rep, 'pixelsWide')), None)
    if representation is None:
        raise ValueError(f'Pet image has no bitmap representation: {path}')
    # XML anchors and velocity are pixels; PNG DPI must not change their logical point scale.
    image.setSize_((representation.pixelsWide(), representation.pixelsHigh()))
    return image


class PetPanel(AK.NSPanel):
    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


class SpriteView(AK.NSView):
    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def drawRect_(self, rect):
        AK.NSColor.clearColor().set()
        AK.NSRectFillUsingOperation(self.bounds(), AK.NSCompositingOperationCopy)
        view = self.owner
        if view.image is None:
            return
        if view.mirror:
            AK.NSGraphicsContext.saveGraphicsState()
            transform = AK.NSAffineTransform.transform()
            transform.translateXBy_yBy_(self.bounds().size.width, 0)
            transform.scaleXBy_yBy_(-1, 1)
            transform.concat()
        view.image.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
            self.bounds(), AK.NSZeroRect, AK.NSCompositingOperationSourceOver, 1, True, None)
        if view.mirror:
            AK.NSGraphicsContext.restoreGraphicsState()

    def mouseDown_(self, event):
        owner = self.owner
        pet = owner.pet
        if pet.paused:
            return
        cursor = cursor_pos()
        pet.runtime.pointer_down(cursor.x, cursor.y, image_width=owner.width, image_height=owner.height)
        owner.render()

    def mouseDragged_(self, event):
        pet = self.owner.pet
        cursor = cursor_pos()
        if pet.runtime.pointer_active:
            pet.runtime.pointer_motion(cursor.x, cursor.y)
            self.owner.render()

    def mouseUp_(self, event):
        pet = self.owner.pet
        cursor = cursor_pos()
        if pet.runtime.pointer_active:
            pet.runtime.pointer_up(cursor.x, cursor.y)
            pet.reset_display()
            self.owner.render()

    def rightMouseDown_(self, event):
        if not self.owner.pet.runtime.dragging:
            self.owner.pet.application.ui.pet_menu(self.owner.pet, event, self)


class SpriteWindow:
    def __init__(self, pet):
        self.pet = pet
        self.images = pet.application.image_cache
        self.image = None
        self.width = self.height = 1
        self.mirror = False
        self.visual = None
        self.rect = None
        self.panel = PetPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (1, 1)), AK.NSWindowStyleMaskBorderless | AK.NSWindowStyleMaskNonactivatingPanel,
            AK.NSBackingStoreBuffered, False)
        self.panel.setTitle_(f'Neuro Pet — {pet.catalog.image_set_dir.name}')
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(AK.NSColor.clearColor())
        self.panel.setHasShadow_(False)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setLevel_(AK.NSFloatingWindowLevel)
        self.panel.setCollectionBehavior_(AK.NSWindowCollectionBehaviorCanJoinAllSpaces |
                                          AK.NSWindowCollectionBehaviorCanJoinAllApplications)
        self.panel.setReleasedWhenClosed_(False)
        self.area = SpriteView.alloc().initWithFrame_(((0, 0), (1, 1)))
        self.area.owner = self
        self.panel.setContentView_(self.area)

    def clear_images(self):
        self.visual = None

    def render(self):
        frame, runtime = self.pet.runtime.frame, self.pet.runtime
        name = frame.image_for_direction(look_right=runtime.look_right)
        key = (self.pet.catalog.image_set_dir, name)
        if key not in self.images:
            image = load_sprite(self.pet.catalog.image_set_dir / name) if name else AK.NSImage.alloc().initWithSize_((1, 1))
            self.images[key] = image
        image = self.images[key]
        size = image.size()
        width, height = round(size.width), round(size.height)
        mirror = frame.needs_horizontal_flip(look_right=runtime.look_right)
        rect = runtime.sprite_rect(width, height)
        if not runtime.pointer_active and not self.pet.paused:
            from src.runtime import Rect
            x, y = self.pet.display_anchor
            rect = Rect(round(rect.x + x - runtime.anchor_x), round(rect.y + y - runtime.anchor_y), rect.width, rect.height)
        visual = (name, mirror)
        self.image, self.width, self.height, self.mirror = image, width, height, mirror
        if rect != self.rect:
            self.rect = rect
            self.panel.setFrame_display_(coordinates().rect_to_appkit(rect), False)
        if visual != self.visual:
            self.visual = visual
            self.area.setNeedsDisplay_(True)

    def show(self):
        self.render()
        self.panel.orderFrontRegardless()

    def close(self):
        self.panel.close()
        self.area.owner = None
