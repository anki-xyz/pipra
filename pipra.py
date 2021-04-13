from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, \
    QSlider, QLabel, QFileDialog, QColorDialog, QMessageBox, QInputDialog, QAction
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtCore import Qt, pyqtSignal
import pyqtgraph as pg
import numpy as np
import imageio as io
import flammkuchen as fl
import os
from skimage.draw import disk
from skimage.color import rgb2gray
import json
from glob import glob
from floodfill import floodfill


class customImageItem(pg.ImageItem):
    wheel_change = pyqtSignal(int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clicked = False
        self.mode = 'add'
        self.save_history = False
        self.spaceIsDown = False

    def wheelEvent(self, wh, ax=None):
        """Wheel event in image scene

        Args:
            wh (Wheel event): Contains information about the wheel
            ax (axis, optional): Wheel axis. Defaults to None.
        """
        modifiers = QApplication.keyboardModifiers()

        # Use Ctrl+Wheel to navigate through the stack
        if modifiers == Qt.ControlModifier:
            # Check for scrolling direction
            wheel_event_direction = int(np.sign(wh.delta()))
            self.wheel_change.emit(wheel_event_direction)

        # Use wheel for zooming
        else:
            super().wheelEvent(wh)

    def mouseDragEvent(self, e):
        modifiers = QApplication.keyboardModifiers()

        # When SHIFT is pressed,
        #  allow left mouse drag
        #  and right mouse zoom
        if modifiers == Qt.ShiftModifier or self.spaceIsDown:
            super().mouseDragEvent(e)

        # Otherwise, add pixels to mask
        #  with left mouse, remove with right mouse
        else:
            # Important to keep event alive
            e.accept()

            if e.isStart() and e.button() == Qt.LeftButton:
                self.clicked = True
                self.mode = 'add'

            if e.isStart() and e.button() == Qt.RightButton:
                self.clicked = True
                self.mode = 'remove'

            elif e.isFinish():
                self.clicked = False

            else:
                self.save_history = False


class Annotator(pg.ImageView):
    keyPressSignal = pyqtSignal(int)

    def __init__(self, im, mask=None, parent=None):
        # Set Widget as parent to show ImageView in Widget
        super().__init__(parent=parent)

        # Set 2D image
        self.setImage(im)
        self.shape = im.shape[:2]

        self.history = []
        self.saved = True
        self.tolerance = 5
        self.only_darker_px = True

        # Colors
        self.colorCursor = (255, 0, 100, 255)  # magenta
        self.colorMask   = (20, 240, 92, 255)
        self.colorOthers = (30, 30, 20, 255)
        self.colorBlack  = (0, 0, 0, 0)

        # Call mouse moved event slot
        self.proxy = pg.SignalProxy(self.scene.sigMouseMoved,
                                    rateLimit=60,
                                    slot=self.mouseMoveEvent)

        # XY coordinates of mouse
        self.xy = None

        # Current cursor map
        self.currentCursor = np.zeros(self.shape + (4,), dtype=np.uint8)
        self.currentCursorItem = pg.ImageItem(
            self.currentCursor,
            compositionMode=QPainter.CompositionMode_Plus,
        )

        # Current mask
        self.mask = np.zeros(self.shape + (4,), dtype=np.uint8)

        # If there's already a mask
        if mask is not None:
            self.mask[mask] = self.colorMask

        self.maskItem = customImageItem(
            self.mask,
            compositionMode=QPainter.CompositionMode_Plus,
        )

        # Radius of block or circle
        self.radius = 6
        self.mode = 'circle'
        self.showMask = 1

        # Add mask and cursor as overlay images,
        #  disable right click menu
        self.getView().addItem(self.currentCursorItem)
        self.getView().addItem(self.maskItem)
        self.getView().setMenuEnabled(False)

        # Interesting things to keep in mind:
        # self.getView().setMouseEnabled(False, False)
        # self.getView().setLeftButtonAction('rect') # Zoom via rectangle

    def keyPressEvent(self, ev):
        if ev.isAutoRepeat() and ev.key() == Qt.Key_Space:
            ev.ignore()
            return

        self.keyPressSignal.emit(ev.key())
        modifiers = QApplication.keyboardModifiers()

        # Increase radius
        if ev.key() == Qt.Key_8:
            if self.radius <= 14:
                self.radius += 2 if self.mode == 'block' else 1

        # Decrease radius
        elif ev.key() == Qt.Key_2:
            if self.radius >= 2:
                self.radius -= 2 if self.mode == 'block' else 1

            elif self.radius == 1:
                self.radius = 0

        # Toggle mask visibility
        elif ev.key() == Qt.Key_Q:
            if self.showMask:
                self.maskItem.setImage(np.zeros_like(self.mask))

            else:
                self.maskItem.setImage(self.mask)

            self.showMask = not self.showMask

        elif ev.key() == Qt.Key_M:
            self.mode = 'circle' if self.mode == 'block' else 'block'

        elif ev.key() == Qt.Key_Z and modifiers == Qt.ControlModifier:
            if len(self.history):
                old_mask = self.history.pop()
                self.mask[:, :] = old_mask
                self.maskItem.setImage(self.mask)

        elif ev.key() == Qt.Key_X:
            self.mask[:, :] = False

        elif ev.key() == Qt.Key_Space:
            self.maskItem.spaceIsDown = True

        self.paint()

    def keyReleaseEvent(self, ev):
        if ev.isAutoRepeat():
            ev.ignore()
            return

        if ev.key() == Qt.Key_Space and self.maskItem.spaceIsDown:
            self.maskItem.spaceIsDown = False

    def mousePressEvent(self, e):
        modifiers = QApplication.keyboardModifiers()

        if modifiers != Qt.ShiftModifier and not self.maskItem.spaceIsDown:
            if e.button() == Qt.LeftButton:
                self.maskItem.mode = 'add'
                self.maskItem.save_history = True
                self.paint(True)

            if e.button() == Qt.RightButton:
                self.maskItem.mode = 'remove'
                self.maskItem.save_history = True
                self.paint(True)

    def paint(self, forcePaint=False):
        # If cursor position is not set
        if self.xy is None:
            return

        xy = self.getImageItem().mapFromScene(self.xy)
        radius = self.radius

        if xy.x() < 0 or xy.x() >= self.shape[0] or xy.y() < 0 or xy.y() >= self.shape[1]:
            return

        # Show current cursor position and painting preview
        self.currentCursor = np.zeros(self.shape+(4,), dtype=np.uint8)
        cursorMask = np.zeros(self.shape, dtype=np.bool)

        # Different mask modes
        # Single pixel
        if self.radius == 0:
            cursorMask[int(xy.x()), int(xy.y())] = True

        # Square
        elif self.mode == 'block':
            cursorMask[int(xy.x() - radius // 2):int(xy.x() + radius // 2 + 1),
                       int(xy.y() - radius // 2):int(xy.y() + radius // 2) + 1] = True

        # Circle
        else:
            rr, cc = disk((xy.x(), xy.y()), radius, shape=self.shape)
            cursorMask[rr, cc] = True

        # Show the cursorMask colored
        self.currentCursor[cursorMask] = self.colorCursor

        # if mouse is clicked without SHIFT
        if self.maskItem.clicked or forcePaint:
            # Depending on mode,
            #  add or remove pixels from mask
            val = self.colorMask if self.maskItem.mode == 'add' else self.colorBlack
            modifiers = QApplication.keyboardModifiers()

            if self.maskItem.save_history:
                self.history.append(self.mask.copy())

            # Assign value
            # Floodfill using current xy position as seed pixel
            if modifiers == Qt.ControlModifier:
                im = (rgb2gray(self.getImageItem().image)*255).astype(np.uint8)
                f = floodfill(im,
                              (int(xy.x()),
                               int(xy.y())),
                               tolerance=self.tolerance,
                               only_darker_px=self.only_darker_px)

                self.mask[f == 1] = val

            # Otherwise use the current cursor mask
            else:
                self.mask[cursorMask] = val

            self.showMask = True
            self.saved = False

        # Update cursor image
        self.currentCursorItem.setImage(self.currentCursor)
        # Update mask image
        if self.showMask:
            self.maskItem.setImage(self.mask)

        # Debugging - found out that one needs to accept the drag event
        # self.setWindowTitle('{}'.format(self.maskItem.clicked))

    def mouseMoveEvent(self, e):
        # Save mouse position
        self.xy = e[0]

        # Call painting routine to update cursor and mask images
        if not self.maskItem.spaceIsDown:
            self.paint()

    def getMask(self):
        return self.mask.sum(2) > 0

    def setZ(self, im, mask=None, levels=None):
        self.setImage(im, autoRange=False, autoLevels=False)
        self.history = []
        self.shape = im.shape[:2]

        self.mask = np.zeros(self.shape + (4,), dtype=np.uint8)

        if mask is not None:
            self.mask[mask] = self.colorMask

        self.maskItem.setImage(self.mask)
        self.paint()

    def setColor(self, colorCursor=None, colorMask=None, colorOthers=None, colorBlack=None):
        if colorCursor:
            self.colorCursor = colorCursor

        if colorMask:
            self.colorMask = colorMask

        if colorOthers:
            self.colorOthers = colorOthers

        if colorBlack:
            self.colorBlack = colorBlack

        # Draw again the scene with new colors
        self.mask[self.mask.sum(2) > 0] = self.colorMask
        self.paint()

class Stack(QWidget):
    def __init__(self, stack, mask=None, is_folder=False):
        super().__init__()

        self.stack = stack
        self.is_folder = is_folder

        if mask is None:
            if is_folder:
                self.mask = [np.zeros(im.shape[:2], dtype=np.bool) for im in stack]

            else:
                self.mask = np.zeros(stack.shape[:3], dtype=np.bool)
            
        else:
            self.mask = mask

        self.curId = 0
        self.listActive = False

        self.w = Annotator(self.stack[self.curId],
                           self.mask[self.curId],
                           parent=self)

        self.l = QGridLayout()

        self.l.addWidget(self.w, 0, 0, 1, 2)
        self.w.show()
        #self.setFixedWidth(self.w.width())
        #self.setFixedHeight(self.w.height())

        self.z = QSlider(orientation=Qt.Horizontal)
        self.z.setMinimum(0)

        if is_folder:
            self.z.setMaximum(len(self.stack)-1)
        else:
            self.z.setMaximum(self.stack.shape[0]-1)
        self.z.setValue(0)
        self.z.setSingleStep(1)
        self.z.valueChanged.connect(self.changeZ)

        # Listen to signals from other the pyqtgraph widget and the custom Image Item
        self.w.keyPressSignal.connect(self.keyPress)
        self.w.maskItem.wheel_change.connect(self.wheelChange)

        self.l.addWidget(QLabel("z position"), 1, 0)
        self.l.addWidget(self.z, 1, 1)

        self.setLayout(self.l)

    def changeZ(self):
        # Save current mask
        self.mask[self.curId] = self.w.getMask()

        # Save current view state (zoom, position, ...)
        viewBoxState = self.w.getView().getState()
        # Save current levels
        levels = self.w.getImageItem().levels

        # New image position
        self.curId = self.z.value()

        # Boundary check
        self.curId = max(self.curId, 0)
        
        if self.is_folder:
            self.curId = min(self.curId, len(self.stack))
        else:
            self.curId = min(self.curId, self.stack.shape[0])

        # Set the new image
        im = self.stack[self.curId]

        self.w.setZ(im, self.mask[self.curId], levels)

        self.w.getView().setState(viewBoxState)
        self.w.getImageItem().setLevels(levels)

    def wheelChange(self, direction):
        self.z.setValue(self.curId+direction)

    def keyPress(self, key):
        modifiers = QApplication.keyboardModifiers()

        # WASD for +1 -1 -1 +1
        if key == Qt.Key_D or key == Qt.Key_W:
            self.z.setValue(self.curId+1)

        elif key == Qt.Key_A or (key == Qt.Key_S and modifiers != Qt.ControlModifier):
            self.z.setValue(self.curId -1)

        # Copy mask from previous (-1) mask
        elif key == Qt.Key_C:
            if self.mask[self.curId].sum() == 0 and self.curId > 0:
                # Replace mask
                self.mask[self.curId] = self.mask[self.curId-1]
                # Get the state (i.e. position, zoom, ...)
                viewBoxState = self.w.getView().getState()
                levels = self.w.getImageItem().levels
                # Set new mask
                self.w.setZ(self.stack[self.curId], self.mask[self.curId])
                # Set view again
                self.w.getView().setState(viewBoxState)
                self.w.getImageItem().setLevels(levels)

    def getMasks(self):
        self.mask[self.curId] = self.w.getMask()
        return self.mask

    def keyPressEvent(self, e):
        modifiers = QApplication.keyboardModifiers()

        if e.key() == Qt.Key_S and modifiers == Qt.ControlModifier:
            self.w.keyPressSignal.emit(e.key())

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_fn = None
        self.status = self.statusBar()
        self.menu = self.menuBar()

        self.file = self.menu.addMenu("&File")
        self.file.addAction("Open file", self.open)
        self.file.addAction("Open folder", self.openFolder)
        self.file.addAction("Save", self.save)
        self.file.addSeparator()
        self.file.addAction("Export mask", self.export)
        self.file.addSeparator()
        self.file.addAction("Close", self.close)

        self.settings = self.menu.addMenu("&Settings")
        self.settings.setDisabled(True)
        self.settings.addAction("Set Mask Color", self.setMaskColor)
        self.settings.addAction("Set Cursor Color", self.setCursorColor)
        self.settings.addSeparator()
        self.settings.addAction("Change tolerance", self.changeTolerance)

        self.onlyDarkerPx = QAction("Floodfill only for darker pixel", self, checkable=True)
        self.onlyDarkerPx.setChecked(True)
        self.onlyDarkerPx.triggered.connect(self.setOnlyDarkerPx)

        self.settings.addAction(self.onlyDarkerPx)
        self.settings.addSeparator()
        self.settings.addAction("Save settings", self.saveSettings)
        self.settings.addAction("Load settings", self.loadSettings)
        # Prepare for dynamic shortcuts
        # self.settings.addAction("Change shortcuts", self.changeShortcuts)
        

        self.fn = None
        self.list = None
        self.d = None
        self.stack = None
        self.files = None

        self.setGeometry(300, 300, 800, 600)
        self.setWindowTitle("PiPrA")

    def setEqualize(self):
        if self.stack:
            self.stack.equalize = self.equalize.isChecked()

    def setOnlyDarkerPx(self):
        self.stack.w.only_darker_px = self.onlyDarkerPx.isChecked()

    def changeTolerance(self):
        i, ok = QInputDialog.getInt(self, 
        "Set tolerance", 
        "floodfill tolerance [grayscale], default 5:", 
        self.stack.w.tolerance, 
        0, 
        100, 
        1)

        if ok:
            self.stack.w.tolerance = i

    def saveSettings(self):
        settings_fn = QFileDialog.getSaveFileName(filter="*.settings")[0]

        if settings_fn:
            print(settings_fn)

            with open(settings_fn, "w") as fp:
                json.dump({
                    'colorCursor': self.stack.w.colorCursor,
                    'colorMask': self.stack.w.colorMask,
                    'tolerance': self.stack.w.tolerance,
                    'onlyDarkerPx': self.onlyDarkerPx.isChecked()
                }, fp, indent=4)

            self.settings_fn = settings_fn

    def loadSettings(self, settings_fn=None):
        if settings_fn is None:
            settings_fn = QFileDialog.getOpenFileName(filter="*.settings")[0]

        if os.path.isfile(settings_fn):
            with open(settings_fn, 'r') as fp:
                settings = json.load(fp)

            try:
                self.stack.w.setColor(colorCursor=settings['colorCursor'],
                                    colorMask=settings['colorMask'])
            except Exception as e:
                print(f"Could not set settings color: \n{e}")

            try:
                self.stack.w.tolerance = settings['tolerance']
            except Exception as e:
                print(f"Could not set settings tolerance: \n{e}")

            try:
                self.onlyDarkerPx.setChecked(settings['onlyDarkerPx'])
            except Exception as e:
                print(f"Could not set settings only darker px: \n{e}")

            self.stack.changeZ()

            self.settings_fn = settings_fn

    def updateStatus(self):
        self.status.showMessage('z: {} x: {} y: {}'.format(self.stack.z.value(), self.stack.w.shape[0],  self.stack.w.shape[1]))

    def getColor(self, init_color):
        old_color = QColor(*init_color)
        new_color = QColorDialog.getColor(old_color, options=QColorDialog.ShowAlphaChannel)
        self.status.showMessage("Changed color from {} to {}".format(old_color.name(), new_color.name()), 1000)
        return new_color.getRgb()

    def setMaskColor(self):
        self.stack.w.setColor(colorMask=self.getColor(self.stack.w.colorMask))

    def setCursorColor(self):
        self.stack.w.setColor(colorCursor=self.getColor(self.stack.w.colorMask))

    def open(self, file=None):
        # A video is loaded
        if self.stack is not None:
            # And it was changed
            if not self.stack.w.saved:
                # Ask for saving
                save_it = QMessageBox.question(self,
                                                 "Save?",
                                                 "You haven't saved this file. \nDo you want to save it now?",
                                                 QMessageBox.Yes | QMessageBox.No)

                if save_it == QMessageBox.Yes:
                    self.save()

        if file is None:
            file = QFileDialog.getOpenFileName(directory=self.d)[0]

        self.status.showMessage(file)

        if file:
            self.fn = file
            self.setWindowTitle(self.fn)
            self.fn_mask = ".".join(file.split(".")[:-1]) + ".mask"

            self.d = os.path.dirname(self.fn)

            if file.endswith("nrrd"):
                import nrrd
                s, metadata = nrrd.read(file)
                s = s.transpose(2, 0, 1).copy()
                s = np.repeat(s[..., None], 3, 3)

            else:
                s = io.mimread(file, memtest=False)

                if len(s[0].shape) == 2:
                    s = np.asarray(s, dtype=s[0].dtype).transpose(0, 2, 1)
                    s = np.repeat(s[..., None], 3, 3)
                else:
                    s = np.asarray(s, dtype=s[0].dtype).transpose(0, 2, 1, 3)
                print("Stack shape: ", s.shape)

            if os.path.isfile(self.fn_mask):
                mask = fl.load(self.fn_mask, "/mask")
                print("Mask shape:  ", mask.shape)
            else:
                mask = None

            # self.stack = Stack((rgb2gray(s)*255).astype(np.uint8) if len(s.shape) == 4 else s, mask)
            self.stack = Stack(s, mask)
            self.setCentralWidget(self.stack)
            self.stack.z.valueChanged.connect(self.updateStatus)
            self.stack.w.keyPressSignal.connect(self.savekeyboard)

        # Debug mode
        else:
            from skimage.filters import gaussian
            from skimage.draw import ellipse

            s = np.random.random_integers(173, 255, 100 * 100 * 20).reshape(20, 100, 100).astype(np.uint8)

            for i in range(s.shape[0]):
                rr, cc = ellipse(s.shape[1]//2, 
                                 s.shape[2]//2, 
                                 17 * np.sin(0.2 * i) + 5, 
                                 40, 
                                 s.shape[1:])

                s[i][rr, cc] = 125
                s[i] = gaussian(s[i], 2.5, preserve_range=True)

            self.stack = Stack(s)
            self.setCentralWidget(self.stack)
            self.stack.z.valueChanged.connect(self.updateStatus)
            self.stack.w.keyPressSignal.connect(self.savekeyboard)

        self.settings.setEnabled(True)

        if self.settings_fn:
            self.loadSettings(settings_fn=self.settings_fn)

    def openFolder(self, ext="png"):
        folder = QFileDialog.getExistingDirectory()

        if folder:
            files = glob(os.path.join(folder, "*."+ext))
            ims = [io.imread(fn).transpose(1, 0, 2) for fn in files]

            self.fn = folder
            self.files = files
            self.setWindowTitle(folder)
            self.fn_mask = os.path.join(folder, "images.mask")

            self.d = folder

            print("Stack shape: ", len(ims))

            if os.path.isfile(self.fn_mask):
                mask = fl.load(self.fn_mask, "/mask")
            else:
                mask = None

            self.stack = Stack(ims, mask, is_folder=True)
            self.setCentralWidget(self.stack)
            self.stack.z.valueChanged.connect(self.updateStatus)
            self.stack.w.keyPressSignal.connect(self.savekeyboard)

            self.settings.setEnabled(True)

            if self.settings_fn:
                self.loadSettings(settings_fn=self.settings_fn)


    def save(self):
        if not self.fn:
            QMessageBox.critical(self, "No file loaded", "Please load first a file.")
            return

        else:
            self.stack.w.saved = True

            if "ö" in self.fn or "ü" in self.fn or "ö" in self.fn:
                # QMessageBox.information(self, 
                #                     "Umlaut found",
                #                     "You cannot save Umlaut with flammkuchen... \n"+\
                #                     "I try to avoid it, but this tool will \n"+\
                #                     "not find the mask file automatically. \n"+\
                #                     "Please consider renaming it!",
                #                     QMessageBox.Ok)

                print("before: ", self.fn_mask)
                self.fn_mask = self.fn_mask.replace("ö","oe").replace("ü","ue").replace("ä","ae")
                print("after:  ", self.fn_mask)

            fl.save(self.fn_mask, {'mask': self.stack.getMasks(), "files": self.files}, compression='blosc')
            print('saving done.')

            self.status.showMessage("Masks saved as {} ...".format(self.fn_mask), 1000)

    def export(self):
        if not self.fn:
            QMessageBox.critical(self, "No file loaded", "Please load first a file.")
            return

        fn = QFileDialog.getSaveFileName(caption="Select file that should contain exported data",
            filter="MP4 (*.mp4);; TIFF (*.tif)")[0]

        if fn:
            if fn.endswith(".tif"):
                io.mimwrite(fn, self.stack.getMasks().astype(np.uint8).transpose(0,2,1)*255)
                QMessageBox.information(self,
                    "Data exported",
                    f"Binary masks where exported as uint8/TIF file: \n{fn}")

            elif fn.endswith(".mp4"):
                io.mimwrite(fn, 
                    self.stack.getMasks().astype(np.uint8).transpose(0,2,1)*255,
                    macro_block_size=None)

                QMessageBox.information(self,
                    "Data exported",
                    f"Binary masks where exported as MP4 file: \n{fn}")

            else:
                pass
        

    def savekeyboard(self, key):
        modifiers = QApplication.keyboardModifiers()

        if key == Qt.Key_S and modifiers == Qt.ControlModifier:
            self.save()

    def close(self):
        reply = QMessageBox.question(self,
            "Closing?",
            "Do you really want to close PiPrA?\nHave you saved everything?")

        if reply == QMessageBox.Yes:
            super().close()

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)

    m = Main()
    m.show()

    sys.exit(app.exec_())

