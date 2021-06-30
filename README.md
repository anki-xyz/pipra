# PiPrA (Pixel Precise Annotator)

[![PyPI Version](https://img.shields.io/pypi/v/pipra)](https://pypi.org/project/pipra/)

![PiPrA Logo](docs/images/pipra.png)

```PiPrA``` allows to label data in a binary fashing (fore-and background) pixel-precisely, using painting or flood filling.
It opens tiff stacks and videos (as supported by imageio ```mimread```), and can operate on single frames.

To try out the ```PiPrA``` tool, simple close the **Open File** dialog,
to get some dummy data.

# How to get PiPrA

    > pip install pipra
    
And then you can execute it by just writing

    > pipra

# Dependencies

- PyQt5 (in Anaconda)
- ImageIO (in Anaconda)
- Scikit-image (in Anaconda)
- [flammkuchen](https://github.com/portugueslab/flammkuchen) (```pip install flammkuchen```)
- [PyQtGraph](http://www.pyqtgraph.org/) (```pip install pyqtgraph```)

Works with the latest libraries much better (PyQt5==5.15.4, pyqtgraph==0.12.1, python==3.7.10).

# How it works

1) Open a video or a folder with images (currently, PiPrA is looking for PNGs only)
2) The brush is by default magenta, the foreground green, you can change these colors in the settings, 
and you are able to save and restore old settings.
3) Draw with left mouse click, you can paint a larger surface by keeping the left mouse button pressed.
Alternatively: you may use the outline mode for large areas (see shortcuts below)
4) Remove area with right mouse click with given brush size
5) Use the mouse wheel to zoom in/out 
6) Adjust contrast/brightness by adjusting the levels on the right hand side. These settings are kept for the entire video.
7) To move the scene, keep the ```Shift``` key pressed.
8) For flood fill mode, keep ```Ctrl``` pressed, and click on the desired seed pixel.

# Saving and Exporting

Everything is stored as HDF5 file, the dimensions are (z/time, x, y), dtype is boolean.
Use ```flammkuchen``` or ```PyTables``` to read the file.
Also, when annotating a folder, it contains a list of the filenames in the same order as the masks.

You can also export masks to a more common format, such as TIF files or MP4 (`Ctrl+E`).

# Shortcuts

These shortcuts make your life much easier:

- ```X``` to remove the mask
- ```Ctrl+Left Click``` flood fill, seeded with the clicked px
- ```Shift+Left Click+Mouse move``` Move scene
- ```Ctrl+Z``` go back in history
- ```Ctrl+S``` save mask/segmentation
- ```C``` copy mask from previous frame
- ```Q``` toggle mask on/off
- ```W```, ```A```, ```S```, ```D``` to change frame forward (```W, D```)/backward (```A, S```)
- ```M``` change brush from circle to block
- `O` change brush to outline mode: **Draw outline around ROI, then the inside will be filled**
- ```2``` make brush smaller (as small as 1 px)
- ```8``` make brush bigger 

## New shortcuts

- `Space pressed+Left Click+Mouse move` Move scene (similar to photoshop)
- `Ctrl+Mouse wheel` change frame forward (wheel up) and backward (wheel down)
- `Ctrl+E` Export segmentation as TIF or MP4
- `Ctrl+O` Open file

# Acknowledging `PiPrA`

We have not published ```PiPrA``` yet.
To acknowledge `PiPrA`, please use currently the following citation:

Gómez, P.\*, Kist, A.M.\*, Schlegel, P. et al. BAGLS, a multihospital Benchmark for Automatic Glottis Segmentation. Sci Data 7, 186 (2020). https://doi.org/10.1038/s41597-020-0526-3
