from PIL import Image
import numpy as np
w, h = 2048, 146
d = open('grid.tga', 'rb').read()
a = np.frombuffer(d[18:], dtype=np.uint8).reshape(h, w, 4)
rgb = a[:, :, [2, 1, 0]].astype(np.float32)
al = a[:, :, 3:4].astype(np.float32) / 255.0
comp = (rgb * al + np.array([5, 3, 12]) * (1 - al)).astype(np.uint8)
Image.fromarray(comp).resize((1100, 240), Image.LANCZOS).save('grid_preview.png')
print('wrote grid_preview.png')
