import numpy as np
import cv2 

def GrabCut(im, r, iterations=1):
    """GrabCut Algorithm for fast foreground annotation

    Args:
        im (numpy.ndarray): The image data that should be analyzed
        r (tuple): The rectangle coordinates of foreground (x0, y0, x1, y1)
        iterations (int, optional): GrabCut iterations. Defaults to 1.

    Returns:
        numpy.ndarray: The estimated foreground mask from GrabCut
    """
    r = tuple([int(i) for i in r])

    # Init mask
    mask = np.zeros(im.shape[:2], dtype=np.uint8)

    # Init internal fore- and background vectors
    fgModel = np.zeros((1, 65), dtype=np.float64)
    bgModel = np.zeros((1, 65), dtype=np.float64)   

    if len(im.shape) == 2:
        im = cv2.cvtColor(im.copy(), cv2.COLOR_GRAY2BGR)

    mask, _, _ = cv2.grabCut(im.astype(np.uint8).copy(), # Original image
        mask, # Mask
        r,  # Rectangle from pipra
        bgModel, # Internal background model vector
        fgModel, # Intenral foreground model vector
        iterCount=iterations, # Iterations for algorithm
        mode=cv2.GC_INIT_WITH_RECT) # GrabCut using a rectangle

    # Find background
    finalMask = (mask == cv2.GC_BGD) | (mask == cv2.GC_PR_BGD)

    # Return inverted to provide foreground
    return ~finalMask