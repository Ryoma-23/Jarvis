import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw


def create_image():
    image = Image.new("RGB", (64, 64), color=(0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 63), fill=(200, 0, 0))
    draw.text((24, 22), "J", fill=(255, 255, 255))
    return image


def on_quit(icon, menu_item):
    icon.stop()


menu = pystray.Menu(
    item("終了", on_quit)
)

icon = pystray.Icon(
    "Jarvis Test",
    create_image(),
    "Jarvis Test",
    menu
)

icon.run()