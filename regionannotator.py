from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, QSlider, QLabel, QFileDialog, QColorDialog
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtCore import Qt, pyqtSignal
import pyqtgraph as pg
import numpy as np
import imageio as io
import deepdish as dd
import os
from skimage.draw import circle
import json


class customImageItem(pg.ImageItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clicked = False
        self.mode = 'add'

    def mouseDragEvent(self, e):
        modifiers = QApplication.keyboardModifiers()

        # When SHIFT is pressed,
        #  allow left mouse drag
        #  and right mouse zoom
        if modifiers == Qt.ShiftModifier:
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

    #def mouseClickEvent(self, ev):
    #    self.clicked = True
    #    super().mouseClickEvent(ev)


class Annotator(pg.ImageView):
    mySignal = pyqtSignal(int)

    def __init__(self, im, mask=None, parent=None):
        # Set Widget as parent to show ImageView in Widget
        super().__init__(parent=parent)

        # Set 2D image
        self.setImage(im)
        self.shape = im.shape

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

        if mask is not None:
            self.mask[mask] = self.colorMask

        self.maskItem = customImageItem(
            self.mask,
            compositionMode=QPainter.CompositionMode_Plus,
        )

        # Radius of block or circle
        self.radius = 6
        self.mode = 'block'
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
        self.mySignal.emit(ev.key())

        # Increase radius
        if ev.key() == Qt.Key_8:
            if self.radius <= 10:
                self.radius += 2 if self.mode == 'block' else 1

        # Decrease radius
        elif ev.key() == Qt.Key_2:
            if self.radius >= 2:
                self.radius -= 2 if self.mode == 'block' else 1

        elif ev.key() == Qt.Key_Q:
            if self.showMask:
                self.maskItem.setImage(np.zeros_like(self.mask))

            else:
                self.maskItem.setImage(self.mask)

            self.showMask = not self.showMask

        elif ev.key() == Qt.Key_M:
            self.mode = 'circle' if self.mode == 'block' else 'block'

        self.paint()

    def mousePressEvent(self, e):
        modifiers = QApplication.keyboardModifiers()

        if modifiers != Qt.ShiftModifier:
            if e.button() == Qt.LeftButton:
                self.maskItem.mode = 'add'
                self.paint(True)

            if e.button() == Qt.RightButton:
                self.maskItem.mode = 'remove'
                self.paint(True)

    def paint(self, forcePaint=False):
        # If cursor position is not set
        if self.xy is None:
            return

        pos1 = self.getView().mapFromViewToItem(self.getImageItem(), self.xy)  #
        pos2 = self.getImageItem().mapFromScene(self.xy)

        xy = self.getImageItem().mapFromScene(self.xy)
        radius = self.radius

        # Show current cursor position and painting preview
        self.currentCursor = np.zeros_like(self.currentCursor)

        if self.mode == 'block':
            self.currentCursor[int(xy.x() - radius // 2):int(xy.x() + radius // 2 + 1),
                     int(xy.y() - radius // 2):int(xy.y() + radius // 2) + 1] = self.colorCursor

        else:
            rr, cc = circle(xy.x(), xy.y(), radius, self.shape)
            self.currentCursor[rr, cc] = self.colorCursor

        # if mouse is clicked without SHIFT
        if self.maskItem.clicked or forcePaint:
            # Depending on mode,
            #  add or remove pixels from mask
            val = self.colorMask if self.maskItem.mode == 'add' else self.colorBlack

            # Assign value
            if self.mode == 'block':
                self.mask[int(xy.x() - radius // 2):int(xy.x() + radius // 2 + 1),
                          int(xy.y() - radius // 2):int(xy.y() + radius // 2) + 1] = val

            else:
                rr, cc = circle(xy.x(), xy.y(), radius, self.shape)
                self.mask[rr, cc] = val

            # Update image
            self.maskItem.setImage(self.mask)

            self.showMask = True

        # Update cursor image
        self.currentCursorItem.setImage(self.currentCursor)

        # Debugging - found out that one needs to accept the drag event
        # self.setWindowTitle('{}'.format(self.maskItem.clicked))

    def mouseMoveEvent(self, e):
        # Save mouse position
        self.xy = e[0]

        # Call painting routine to update cursor and mask images
        self.paint()

    def getMask(self):
        return self.mask.sum(2) > 0

    def setZ(self, im, mask=None):
        self.setImage(im)
        self.shape = im.shape

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
    def __init__(self, stack, mask=None):
        super().__init__()

        self.stack = stack

        if mask is None:
            self.mask = np.zeros_like(stack, dtype=np.bool)
        else:
            self.mask = mask

        self.curId = 0

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
        self.z.setMaximum(self.stack.shape[0]-1)
        self.z.setValue(0)
        self.z.setSingleStep(1)
        self.z.valueChanged.connect(self.changeZ)
        self.w.mySignal.connect(self.keyPress)

        self.l.addWidget(QLabel("z position"), 1, 0)
        self.l.addWidget(self.z, 1, 1)

        self.setLayout(self.l)

    def changeZ(self):
        self.mask[self.curId] = self.w.getMask()

        viewBoxState = self.w.getView().getState()

        self.curId = self.z.value()

        # Boundary check
        self.curId = max(self.curId, 0)
        self.curId = min(self.curId, self.stack.shape[-1])

        self.w.setZ(self.stack[self.curId], self.mask[self.curId])

        self.w.getView().setState(viewBoxState)

    def keyPress(self, key):
        modifiers = QApplication.keyboardModifiers()

        # WASD for +1 -1 -1 +1
        if key == Qt.Key_D or key == Qt.Key_W:
            self.z.setValue(self.curId+1)

        elif key == Qt.Key_A or (key == Qt.Key_S and modifiers != Qt.ControlModifier):
            self.z.setValue(self.curId-1)

        elif key == Qt.Key_C:
            if self.mask[self.curId].sum() == 0 and self.curId > 0:
                self.mask[self.curId] = self.mask[self.curId-1]
                viewBoxState = self.w.getView().getState()
                self.w.setZ(self.stack[self.curId], self.mask[self.curId])
                self.w.getView().setState(viewBoxState)

    def getMasks(self):
        self.mask[self.curId] = self.w.getMask()
        return self.mask

    def keyPressEvent(self, e):
        modifiers = QApplication.keyboardModifiers()

        if e.key() == Qt.Key_S and modifiers == Qt.ControlModifier:
            self.w.mySignal.emit(e.key())

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_fn = None
        self.status = self.statusBar()
        self.menu = self.menuBar()

        self.file = self.menu.addMenu("&File")
        self.file.addAction("Open", self.open)
        self.file.addAction("Save", self.save)

        self.settings = self.menu.addMenu("&Settings")
        self.settings.setDisabled(True)
        self.settings.addAction("Set Mask Color", self.setMaskColor)
        self.settings.addAction("Set Cursor Color", self.setCursorColor)
        self.settings.addAction("Save settings", self.saveSettings)
        self.settings.addAction("Load settings", self.loadSettings)

        self.fn = None

        #s = np.random.random_integers(0, 255, 100*100*100).reshape(100, 100, 100).astype(np.uint8)

        #self.stack = Stack(s)
        #self.setCentralWidget(self.stack)

       # self.stack.z.valueChanged.connect(self.updateStatus)
        self.setGeometry(300, 300, 800, 600)

    def saveSettings(self):
        settings_fn = QFileDialog.getSaveFileName(directory=r"C:\Users\kistas\PycharmProjects\RegionAnnotator",
                                                  filter="*.settings")[0]

        if settings_fn:
            print(settings_fn)

            with open(settings_fn, "w") as fp:
                json.dump({
                    'colorCursor': self.stack.w.colorCursor,
                    'colorMask': self.stack.w.colorMask,
                }, fp, indent=4)

            self.settings_fn = settings_fn

    def loadSettings(self, settings_fn=None):

        if settings_fn is None:
            settings_fn = QFileDialog.getOpenFileName(directory=r"C:\Users\kistas\PycharmProjects\RegionAnnotator",
                                                      filter="*.settings")[0]

        with open(settings_fn, 'r') as fp:
            settings = json.load(fp)

        self.stack.w.setColor(colorCursor=settings['colorCursor'],
                              colorMask=settings['colorMask'])


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

    def open(self):
        file = QFileDialog.getOpenFileName(directory=r"W:\phoniatrie\nas-pp1\Backup_NAS_alt\Deep Learning\Daten\Stepp\HSV Data")[0]
        self.status.showMessage(file)

        if file:
            self.fn = file
            self.fn_mask = ".".join(file.split(".")[:-1])+".mask"

            s = io.mimread(file, memtest=False)
            s = np.array(s, dtype=s[0].dtype).transpose(0, 2, 1, 3)
            print("Stack shape: ", s.shape)

            if os.path.isfile(self.fn_mask):
                mask = dd.io.load(self.fn_mask, "/mask")
                print("Mask shape: ", mask.shape)
            else:
                mask = None

            self.stack = Stack(s[..., 0], mask)
            self.setCentralWidget(self.stack)
            self.stack.z.valueChanged.connect(self.updateStatus)
            self.stack.w.mySignal.connect(self.savekeyboard)

        # Debug mode
        else:
            s = np.random.random_integers(0, 255, 100 * 100 * 20).reshape(20, 100, 100).astype(np.uint8)

            self.stack = Stack(s)
            self.setCentralWidget(self.stack)
            self.stack.z.valueChanged.connect(self.updateStatus)
            self.stack.w.mySignal.connect(self.savekeyboard)

        self.settings.setEnabled(True)

        if self.settings_fn:
            self.loadSettings(settings_fn=self.settings_fn)

    def save(self):
        if self.fn:
            dd.io.save(self.fn_mask, {'mask': self.stack.getMasks()}, compression='blosc')
            print('saving done.')
            self.status.showMessage("Masks saved as {} ...".format(self.fn_mask), 1000)

    def savekeyboard(self, key):
        modifiers = QApplication.keyboardModifiers()

        if key == Qt.Key_S and modifiers == Qt.ControlModifier:
            self.save()

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)

    m = Main()
    m.show()

    sys.exit(app.exec_())
