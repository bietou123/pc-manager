"""生成应用图标 assets/app.ico，供打包使用。"""

import os

from PIL import Image, ImageDraw

SIZE = 256
BG_TOP = (59, 130, 246)
BG_BOTTOM = (6, 182, 212)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_image():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    gradient = Image.new("RGBA", (SIZE, SIZE))
    brush = ImageDraw.Draw(gradient)
    for y in range(SIZE):
        brush.line([(0, y), (SIZE, y)], fill=lerp(BG_TOP, BG_BOTTOM, y / (SIZE - 1)) + (255,))

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=56, fill=255)
    img.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    pad, gap = 62, 16
    cell = (SIZE - pad * 2 - gap) // 2
    for row in range(2):
        for col in range(2):
            x = pad + col * (cell + gap)
            y = pad + row * (cell + gap)
            draw.rounded_rectangle([x, y, x + cell, y + cell], radius=14, fill=(255, 255, 255, 255))
    return img


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets = os.path.join(root, "assets")
    os.makedirs(assets, exist_ok=True)

    img = make_image()
    ico_path = os.path.join(assets, "app.ico")
    img.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(os.path.join(assets, "app.png"))
    print(f"图标已生成：{ico_path}")


if __name__ == "__main__":
    main()
