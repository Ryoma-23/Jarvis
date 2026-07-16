from PIL import Image, ImageDraw


def create_icon_image():
    image = Image.new("RGB", (64, 64), color=(0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, 63, 63), fill=(0, 90, 180))
    draw.ellipse((10, 10, 54, 54), fill=(255, 255, 255))
    draw.text((25, 22), "J", fill=(0, 90, 180))

    return image