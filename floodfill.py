from numba import njit
import numpy as np
import time


@njit
def _neighbours_4d(x, y, h, w):
    '''
    Find neighbours of given pixel with border detection
    :param x: x
    :param y: y
    :param h: height of image (related to x)
    :param w: width of image (related to y)
    :return: neighbours as list of (x,y) tuples
    '''
    r = []
    if x-1 >= 0:
        r.append((x-1, y))
    if y+1 < w-1:
        r.append((x, y+1))
    if x+1 < h-1:
        r.append((x+1, y))
    if y-1 >= 0:
        r.append((x, y-1))
    yield r

@njit
def _floodfill(im, seed, tolerance=5, only_darker_px=True):
    '''
    Floodfill algorithm that uses both, absolute gray threshold and edge
    :param im: 2D image to be segmented
    :param edge: 2D image with pronounced edges, e.g. sobel
    :param seed: First starting point for flood filling
    :param edge_thres: Edge threshold
    :param gray_thres_factor: Gray threshold factor (factor times seed gray value)
    :param only_darker_px: Floodfill only intensities lower than seed+tolerance
    :return: Segmented image with -1 for not segmented, 0 contour, 1 fill
    '''
    p = [seed]
    h, w = im.shape
    segmented = np.zeros_like(im, dtype=np.int8) - 1
    gray_thres = im[seed]+tolerance
    seed_intensity = im[seed]

    while len(p):
        pi = p.pop()

        if segmented[pi] < 0:
            
            if only_darker_px and im[pi] <= gray_thres:
                segmented[pi] = 1

                for i in _neighbours_4d(pi[0], pi[1], h, w):
                    p.extend(i)

            elif not only_darker_px and abs(im[pi]-seed_intensity) <= gray_thres:
                segmented[pi] = 1

                for i in _neighbours_4d(pi[0], pi[1], h, w):
                    p.extend(i)
            
            else:
                segmented[pi] = 0

    return segmented

def floodfill(im, seed, time_it=False, tolerance=5, only_darker_px=True):
    if time_it:
        t0 = time.time()

    f = _floodfill(im, seed, tolerance=tolerance, only_darker_px=only_darker_px)

    if time_it:
        print("Flood fill took {:.2f} s".format(time.time()-t0))

    return f
