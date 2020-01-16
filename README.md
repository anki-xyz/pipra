# PiPrA (Pixel Precise Annotator)
```PiPrA``` allows to label data in a binary fashing (fore-and background) pixel-precisely, using painting or flood filling.
It opens tiff stacks and videos (as supported by imageio ```mimread```), and can operate on single frames.

To try out the ```PiPrA``` tool, simple close the **Open File** dialog,
to get some dummy data.

# Dependencies

- PyQt5 (in Anaconda)
- ImageIO (in Anaconda)
- Scikit-image (in Anaconda)
- [flammkuchen](https://github.com/portugueslab/flammkuchen) (```pip install flammkuchen```)
- [PyQtGraph](http://www.pyqtgraph.org/) (```pip install pyqtgraph```)

# How it works

1) Open a video or a folder with images (currently, PiPrA is looking for PNGs only)
2) The brush is by default magenta, the foreground green, you can change these colors in the settings, 
and you are able to save and restore old settings.
3) Draw with left mouse click, you can paint a larger surface by keeping the left mouse button pressed.
4) Remove area with right mouse click
5) Use the mouse wheel to zoom in/out 
6) Adjust contrast/brightness by adjusting the levels on the right hand side. These settings are kept for the entire video.
7) To move the scene, keep the ```Shift``` key pressed.
8) For flood fill mode, keep ```Ctrl``` pressed, and click on the desired seed pixel.

# Saving

Everything is stored as HDF5 file, the dimensions are (z/time, x, y), dtype is boolean.
Use ```flammkuchen``` or ```PyTables``` to read the file.
Also, when annotating a folder, it contains a list of the filenames in the same order as the masks.

# Shortcuts

These shortcuts make your life much easier:

- ```X``` to remove the mask
- ```Ctrl+Z``` go back in history
- ```Ctrl+S``` save mask/segmentation
- ```C``` copy mask from previous frame
- ```Q``` toggle mask on/off
- ```W```, ```A```, ```S```, ```D``` to change frame forward/backward
- ```M``` change brush from circle to block
- ```2``` make brush smaller (as small as 1 px)
- ```8``` make brush bigger 

# How to cite PiPrA

We published ```PiPrA``` here, please use the following citation:

tbd.
