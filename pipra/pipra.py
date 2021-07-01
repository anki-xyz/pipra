from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, \
    QSlider, QLabel, QFileDialog, QColorDialog, QMessageBox, QInputDialog, \
    QAction, QGraphicsPathItem
from PyQt5.QtGui import QKeySequence, QPainter, QColor, QCursor, QPolygonF, QPen, \
    QPainterPath
from PyQt5.QtCore import Qt, pyqtSignal
import numpy as np
import pyqtgraph as pg
import imageio as io
import flammkuchen as fl
import os
from skimage.draw import disk, polygon
from skimage.color import rgb2gray
import json
from glob import glob

### Import related functions
from .floodfill import floodfill
from .grabcut import GrabCut

class PipraImageItem(pg.ImageItem):
    wheel_change = pyqtSignal(int)
    mouseRelease = pyqtSignal()

    def __init__(self, *args, **kwargs):
        """Custom pyqtgraph ImageItem to allow wheel and mouse events for dragging and drawing
        """
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
        """allows dragging image and live painting

        Args:
            e (event): Qt event 
        """
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
                self.mouseRelease.emit()

            else:
                self.save_history = False


class PipraImageView(pg.ImageView):
    keyPressSignal = pyqtSignal(int)

    def __init__(self, im, mask=None, parent=None):
        """The drawing environment

        Args:
            im (numpy.ndarray): The image to be masked
            mask (numpy.ndarray, optional): The binary mask for `im`, 
                will be initialized as zeros when not provided. Defaults to None.
            parent (QWidget, optional): Used to show ImageView in parent QWidget. Defaults to None.
        """
        # Set Widget as parent to show ImageView in Widget
        super().__init__(parent=parent)

        # Set 2D image
        self.setImage(im)
        self.shape = im.shape[:2]

        self.history = []
        self.saved = True

        # Flood fill settings
        self.tolerance = 5
        self.only_darker_px = True

        # Colors
        self.colorCursor = (255, 0, 100, 255)  # magenta
        self.colorMask   = (20, 240, 92, 255) # green
        self.colorOthers = (30, 30, 20, 255)
        self.colorBlack  = (0, 0, 0, 0)

        # Call mouse moved event slot
        self.proxy = pg.SignalProxy(self.scene.sigMouseMoved,
                                    rateLimit=120,
                                    slot=self.mouseMoveEvent)

        # XY coordinates of mouse
        self.xy = None
        self.xys = []

        # Outline drawing prerequisites
        # Initiliaze a line with zero points
        self.polygon = QGraphicsPathItem(QPainterPath())
        self.polygon.setPen(QPen(Qt.red, 1, Qt.SolidLine))
        self.getView().addItem(self.polygon)

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

        self.maskItem = PipraImageItem(
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

    def keyPressEvent(self, ev):
        """Handling the main shortcuts

        Args:
            ev (QEvent): Qt event
        """
        # If there is a key constantly pressed, i.e. Space for navigating,
        # just don't bother...
        if ev.isAutoRepeat() and ev.key() == Qt.Key_Space:
            ev.ignore()
            return

        # Talk to QMainWidget
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

        # Change Circle and Block
        elif ev.key() == Qt.Key_M:
            self.mode = 'circle' if self.mode == 'block' else 'block'

        # Change to OUTLINE mode
        elif ev.key() == Qt.Key_O:
            if self.mode != 'outline':
                self.mode = 'outline'
                self.enableOutline()

            else:
                self.mode = 'circle'
                self.disableOutline()

        # Change to GRABCUT mode
        elif ev.key() == Qt.Key_P:
            if self.mode != 'grabcut':
                self.mode = 'grabcut'
                self.enableGrabCut()

            else:
                self.mode = 'circle'
                self.disableGrabCut()

        # Cycle through options
        elif ev.key() == Qt.Key_1:
            if self.mode == 'circle':
                self.mode = 'block'

            elif self.mode == 'block':
                self.mode = 'outline'
                self.enableOutline()

            elif self.mode == 'outline':
                self.mode = 'circle'
                self.disableOutline()

        # Go back in history...
        elif ev.key() == Qt.Key_Z and modifiers == Qt.ControlModifier:
            if len(self.history):
                old_mask = self.history.pop()
                self.mask[:, :] = old_mask
                self.maskItem.setImage(self.mask)

        # Clear mask
        elif ev.key() == Qt.Key_X:
            self.mask[:, :] = False

        # Move 
        elif ev.key() == Qt.Key_Space:
            self.maskItem.spaceIsDown = True

        # And draw something, i.e. the changed cursor
        self.paint()

    def keyReleaseEvent(self, ev):
        # Don't bother if this is auto-repeat
        if ev.isAutoRepeat():
            ev.ignore()
            return

        if ev.key() == Qt.Key_Space and self.maskItem.spaceIsDown:
            self.maskItem.spaceIsDown = False

    def mousePressEvent(self, e):
        modifiers = QApplication.keyboardModifiers()

        if modifiers != Qt.ShiftModifier and not self.maskItem.spaceIsDown:
            # Add to mask in drawing mode
            if e.button() == Qt.LeftButton and self.mode not in ('outline', 'grabcut'):
                self.maskItem.mode = 'add'
                self.maskItem.save_history = True
                self.paint(True)

            # Add to mask in outline mode
            elif e.button() == Qt.LeftButton and self.mode == 'outline':
                self.recordPolygon()

            elif e.button() == Qt.LeftButton and self.mode == 'grabcut':
                self.drawRectangle() 

            # Remove from mask in drawing mode
            if e.button() == Qt.RightButton:
                self.maskItem.mode = 'remove'
                self.maskItem.save_history = True
                self.paint(True)

    def paint(self, forcePaint=False):
        """Painting event

        Args:
            forcePaint (bool, optional): Force painting event to be executed. Defaults to False.
        """
        # If cursor position is not set
        if self.xy is None:
            return

        xy = self.getImageItem().mapFromScene(self.xy)
        radius = self.radius

        # Current mouse location is outside of scene, ignore... 
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
        elif self.mode == 'circle':
            rr, cc = disk((xy.x(), xy.y()), radius, shape=self.shape)
            cursorMask[rr, cc] = True

        elif self.mode == 'outline' or self.mode == 'grabcut':
            pass

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

    def enableOutline(self):
        # Change Cursor to visualize it's a different mode
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def disableOutline(self):
        # Change Cursor to visualize it's again normal mode
        self.setCursor(QCursor(Qt.ArrowCursor))

    def enableGrabCut(self):
        # Change Cursor to visualize it's a different mode
        self.setCursor(QCursor(Qt.CrossCursor))

    def disableGrabCut(self):
        # Change Cursor to visualize it's again normal mode
        self.setCursor(QCursor(Qt.ArrowCursor))

    def drawRectangle(self):
        if self.maskItem.clicked:
            # Get mouse coordinates and store them
            xy = self.getImageItem().mapFromScene(self.xy)
            self.xys.append(xy)

            # Get first and last point
            x0, y0 = self.xys[0].x(), self.xys[0].y()
            x1, y1 = self.xys[-1].x(), self.xys[-1].y()

            # Sort corners to ensure corner orientation is
            # top/left to bottom/right
            x0, x1 = min(x0, x1), max(x0, x1)
            y0, y1 = min(y0, y1), max(y0, y1)

            # Save rectangle  x   y  w      h
            self.rectangle = x0, y0, x1-x0, y1-y0

            # Show rectangle 
            path = QPainterPath()
            path.addRect(*self.rectangle)
            self.polygon.setPath(path)

    def recordPolygon(self):
        if self.maskItem.clicked:
            # Store location
            xy = self.getImageItem().mapFromScene(self.xy)
            self.xys.append(xy)
        
            # Create polygon to be drawn on image temporarily
            path = QPainterPath()
            path.addPolygon(QPolygonF(self.xys))
            self.polygon.setPath(path)

    def mouseReleaseEvent(self):
        if self.mode == 'outline':
            # Create polygon from xy locations
            xys = [(i.x(), i.y()) for i in self.xys]
            xys = np.asarray(xys, dtype=np.int32)
            rr, cc = polygon(xys[:,0], xys[:,1], self.shape)

            if self.maskItem.save_history:
                self.history.append(self.mask.copy())

            # Add polygon px inside of contour to mask
            self.mask[rr, cc] = self.colorMask

        elif self.mode == 'grabcut':
            # Get image from scene
            im = self.getImageItem().image 

            # Apply GrabCut algorithm using drawn rectangle as initialization
            mask = GrabCut(im, 
                (self.rectangle[1], self.rectangle[0], self.rectangle[3], self.rectangle[2]))

            # Update mask
            self.mask[mask] = self.colorMask

        else:
            return

        # Update mask
        self.maskItem.setImage(self.mask)

        # Reset polygon for next drawing
        self.xys = []
        self.polygon.setPath(QPainterPath())

    def mouseMoveEvent(self, e):
        # Save mouse position
        self.xy = e[0]

        # Call painting routine to update cursor and mask images
        if not self.maskItem.spaceIsDown and self.mode not in ('outline', 'grabcut'):
            self.paint()

        elif self.mode == 'outline':
            self.recordPolygon()

        elif self.mode == 'grabcut':
            self.drawRectangle()

    def getMask(self):
        """Generates binary mask

        Returns:
            numpy.ndarray: binary mask at current location
        """
        return self.mask.sum(2) > 0

    def setZ(self, im, mask=None):
        """Show image at position z. 

        Args:
            im (numpy.ndarray): The image to be shown
            mask (numpy.ndarray, optional): If already a mask exists, 
                otherwise it will be initialized with zeros. Defaults to None.
        """
        # Set image
        self.setImage(im, autoRange=False, autoLevels=False)

        # Clean history
        self.history = []
        self.shape = im.shape[:2]

        # Create new mask
        self.mask = np.zeros(self.shape + (4,), dtype=np.uint8)

        # If mask is provided, paint foreground pixels
        if mask is not None:
            self.mask[mask] = self.colorMask

        # Show mask image and force paint event
        self.maskItem.setImage(self.mask)
        self.paint()

    def setColor(self, colorCursor=None, colorMask=None, colorOthers=None, colorBlack=None):
        """Set color for cursor, mask, others and black.
        Colors need to be specified in RGBA (0...255).

        Args:
            colorCursor (tuple, optional): Cursor color, default magenta. Defaults to None.
            colorMask (tuple, optional): Mask color, default green. Defaults to None.
            colorOthers (tuple, optional): Other color. Defaults to None.
            colorBlack (tuple, optional): Black color, default pitch black. Defaults to None.
        """
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


#############################################
## PipraStack (central widget in QMainWindow)
#############################################
class PipraStack(QWidget):
    def __init__(self, stack, mask=None, is_folder=False):
        """Stack(QWidget)

        The `PipraStack` class carries the whole image stack and the respective masks.
        If it is a folder, it generates empty masks for each image.

        Args:
            stack (list or numpy.ndarray): The image stack
            mask (numpy.ndarray, optional): The corresponding masks to the image stack. Defaults to None.
            is_folder (bool, optional): If the image stack is derived from a folder. Defaults to False.
        """
        super().__init__()

        self.stack = stack
        self.is_folder = is_folder

        # No masks were provided, i.e. opening video first time
        if mask is None:
            # Create N masks for images in folder
            if is_folder:
                self.mask = [np.zeros(im.shape[:2], dtype=np.bool) for im in stack]

            # Create 1 mask for 3D stack (t, x, y) or (z, x, y)
            else:
                self.mask = np.zeros(stack.shape[:3], dtype=np.bool)
            
        else:
            # Use provided mask
            self.mask = mask

        self.curId = 0
        self.listActive = False

        # Use an ImageView to show the ACTIVE image in stack
        self.w = PipraImageView(self.stack[self.curId],
                           self.mask[self.curId],
                           parent=self)

        self.l = QGridLayout()

        self.l.addWidget(self.w, 0, 0, 1, 2)
        self.w.show()
        
        # Slider for z- or t- position
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
        self.w.maskItem.mouseRelease.connect(self.w.mouseReleaseEvent)

        self.l.addWidget(QLabel("z position"), 1, 0)
        self.l.addWidget(self.z, 1, 1)

        self.setLayout(self.l)

    def changeZ(self):
        """Slot for a change in `z` or `t` along the image stack. 
        Saves the current state and updates the image in the ImageView environment.
        """
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

        self.w.setZ(im, self.mask[self.curId])

        self.w.getView().setState(viewBoxState)
        self.w.getImageItem().setLevels(levels)

    def wheelChange(self, direction):
        """Change z or t signal depending on wheel direction

        Args:
            direction (int): Wheel direction (up or down)
        """
        self.z.setValue(self.curId+direction)

    def keyPress(self, key):
        """Shortcuts for efficient interaction with `pipra`.

        Args:
            key ([type]): [description]
        """
        modifiers = QApplication.keyboardModifiers()

        # WASD for +1 -1 -1 +1
        if key == Qt.Key_D or key == Qt.Key_W:
            self.z.setValue(self.curId+1)

        elif key == Qt.Key_A or (key == Qt.Key_S and modifiers != Qt.ControlModifier):
            self.z.setValue(self.curId -1)

        # Copy mask from previous (-1) mask
        elif key == Qt.Key_C:
            if self.mask[self.curId].sum() == 0:
                if self.curId > 0 and modifiers != Qt.ShiftModifier:
                    # Replace mask
                    m = self.mask[self.curId-1]

                if self.curId < self.mask.shape[0]-1 and modifiers == Qt.ShiftModifier:
                    m = self.mask[self.curId+1]

                self.mask[self.curId] = m
                # Get the state (i.e. position, zoom, ...)
                viewBoxState = self.w.getView().getState()
                levels = self.w.getImageItem().levels

                # Set new mask
                self.w.setZ(self.stack[self.curId], self.mask[self.curId])

                # Set view again
                self.w.getView().setState(viewBoxState)
                self.w.getImageItem().setLevels(levels)

    def getMasks(self):
        """Saves the current mask and returns all masks.

        Returns:
            numpy.ndarray: The masks
        """
        self.mask[self.curId] = self.w.getMask()
        return self.mask

##########################
## Main Window
##########################
class PipraMain(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_fn = None
        self.status = self.statusBar()
        self.menu = self.menuBar()

        self.file = self.menu.addMenu("&File")
        self.file.addAction("Open file", self.open, QKeySequence("Ctrl+O"))
        self.file.addAction("Open folder", self.openFolder)
        self.file.addAction("Save", self.save, QKeySequence("Ctrl+S"))
        self.file.addSeparator()
        self.file.addAction("Export mask", self.export, QKeySequence("Ctrl+E"))
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
        self.setAcceptDrops(True)

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

            # NRRD files from ImageJ or CMTK
            # typically confocal or 2p image data
            if file.endswith("nrrd"):
                import nrrd
                s, metadata = nrrd.read(file)
                s = s.transpose(2, 0, 1).copy()
                s = np.repeat(s[..., None], 3, 3)

            # Reading data with imageio (tif, mp4, ...)
            else:
                try:
                    s = io.mimread(file, memtest=False)

                    if len(s[0].shape) == 2:
                        s = np.asarray(s, dtype=s[0].dtype).transpose(0, 2, 1)
                        s = np.repeat(s[..., None], 3, 3)
                    else:
                        s = np.asarray(s, dtype=s[0].dtype).transpose(0, 2, 1, 3)
                    print("Stack shape: ", s.shape)
                except Exception as e:
                    QMessageBox.critical(self, "Could not load data", f"Could not open\n{file}\n\n{e}")
                    return

            if os.path.isfile(self.fn_mask):
                mask = fl.load(self.fn_mask, "/mask")
                print("Mask shape:  ", mask.shape)
            else:
                mask = None

            # self.stack = Stack((rgb2gray(s)*255).astype(np.uint8) if len(s.shape) == 4 else s, mask)
            self.stack = PipraStack(s, mask)
            self.setCentralWidget(self.stack)
            self.stack.z.valueChanged.connect(self.updateStatus)

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

            self.stack = PipraStack(s)
            self.setCentralWidget(self.stack)
            self.stack.z.valueChanged.connect(self.updateStatus)

        self.settings.setEnabled(True)

        if self.settings_fn:
            self.loadSettings(settings_fn=self.settings_fn)

    def dragEnterEvent(self, ev):
        data = ev.mimeData()
        urls = data.urls()
        if urls:
            if urls[0].scheme() == 'file':
                ev.acceptProposedAction()

    def dropEvent(self, ev):
        # Retrieve file url
        data = ev.mimeData()
        urls = data.urls()

        # Check if dropping event is a file
        if urls and urls[0].scheme() == 'file':
            fn = str(urls[0].path())[1:]

            # Does the file exist?
            if os.path.exists(fn):
                self.open(fn)

            # Otherwise raise error
            else:
                QMessageBox.critical(self,
                    "File not found",
                    f"Could not find file:\n{fn}")

    def openFolder(self, ext="png"):
        folder = QFileDialog.getExistingDirectory()

        if folder:
            files = glob(os.path.join(folder, "*."+ext))

            ims = []

            for fn in files:
                im = io.imread(fn)

                if len(im.shape) == 2:
                    im = im.transpose(1, 0)

                elif len(im.shape) == 3:
                    im = im.transpose(1, 0, 2)

                ims.append(im)

            # Bug if not RGB-images:
            # ims = [io.imread(fn).transpose(1, 0, 2) for fn in files]

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

            self.stack = PipraStack(ims, mask, is_folder=True)
            self.setCentralWidget(self.stack)
            self.stack.z.valueChanged.connect(self.updateStatus)

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
        """Exporting segmentation masks as mp4 or tif file, or as single png files.
        """
        if not self.fn:
            QMessageBox.critical(self, "No file loaded", "Please load first a file.")
            return

        fn = QFileDialog.getSaveFileName(caption="Select file that should contain exported data",
            filter="MP4 (*.mp4);; TIFF (*.tif);; PNG (*.png)")[0]

        if fn:
            masks = self.stack.getMasks().astype(np.uint8).transpose(0,2,1)*255

            if fn.endswith(".tif"):
                io.mimwrite(fn, masks)
                QMessageBox.information(self,
                    "Data exported",
                    f"Binary masks where exported as uint8/TIF file: \n{fn}")

            elif fn.endswith(".mp4"):
                io.mimwrite(fn, 
                    masks,
                    macro_block_size=None)

                QMessageBox.information(self,
                    "Data exported",
                    f"Binary masks where exported as MP4 file: \n{fn}")

            elif fn.endswith(".png"):

                for i, m in enumerate(masks):
                    fn_i = fn.replace(".png", f"_{i}.png")
                    io.imwrite(fn_i, m)

                fn_x = fn.replace(".png", "_X.png")

                QMessageBox.information(self,
                    "Data exported",
                    f"Binary masks where exported as {len(masks)} PNG files: \n{fn_x}")

            else:
                pass

    def close(self):
        reply = QMessageBox.question(self,
            "Closing?",
            "Do you really want to close PiPrA?\nHave you saved everything?")

        if reply == QMessageBox.Yes:
            super().close()

def main():
    """Main entry for pipra
    """
    import sys
    app = QApplication(sys.argv)

    m = PipraMain()
    m.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

