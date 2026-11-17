"""The main colours of a picture, drawn as a grid of tiles each labelled with its hex code (#palette, #hex).

Everything happens here with Pillow: no image model is asked, so it costs nothing. The result is not saved to the
image history, because it is a tool, not a picture."""
import io

COLOURS = 8 # tiles in the grid, most common colour first
COLUMNS = 4
TILE = 256 # pixels per side of each tile

def colours(image_bytes, number=COLOURS):
	"""The picture's main colours as hex codes ('#1A2B3C'), most common first. Raises if the picture can't be read."""
	from PIL import Image
	im = Image.open(io.BytesIO(image_bytes))
	if im.mode in ('RGBA', 'LA', 'P', 'PA') or 'transparency' in im.info:
		im = im.convert('RGBA')
		background = Image.new('RGB', im.size, (255, 255, 255)) # transparency counts as white, as Telegram shows it
		background.paste(im, mask=im.getchannel('A'))
		im = background
	else:
		im = im.convert('RGB')
	im.thumbnail((200, 200)) # plenty to find the main colours, and fast
	# median cut, refined by k-means, picks colours that actually cover the picture rather than a fixed palette
	quantized = im.quantize(colors=number, method=Image.Quantize.MEDIANCUT, kmeans=2)
	palette = quantized.getpalette()
	counts = sorted(quantized.getcolors(), reverse=True) # [(pixels, palette index)], biggest share first
	hexes = []
	for count, index in counts:
		code = '#{:02X}{:02X}{:02X}'.format(*palette[index * 3:index * 3 + 3])
		if code not in hexes:
			hexes.append(code)
	return hexes

def label_colour(code):
	"""Black or white, whichever reads better on this colour (by its relative luminance)."""
	r, g, b = (int(code[i:i + 2], 16) / 255 for i in (1, 3, 5))
	linear = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
	luminance = 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
	return (0, 0, 0) if luminance > 0.179 else (255, 255, 255)

def grid(hexes):
	"""A PNG of the colours as square tiles, COLUMNS to a row, each with its hex code written on it."""
	from PIL import Image, ImageDraw, ImageFont
	columns = min(COLUMNS, len(hexes))
	rows = -(-len(hexes) // columns)
	im = Image.new('RGB', (columns * TILE, rows * TILE), (255, 255, 255))
	draw = ImageDraw.Draw(im)
	try:
		font = ImageFont.load_default(size=TILE // 7)
	except (TypeError, OSError): # an old Pillow, or one without FreeType: a small bitmap font
		font = ImageFont.load_default()
	for i, code in enumerate(hexes):
		x, y = (i % columns) * TILE, (i // columns) * TILE
		draw.rectangle((x, y, x + TILE - 1, y + TILE - 1), fill=code)
		left, top, right, bottom = draw.textbbox((0, 0), code, font=font)
		draw.text((x + (TILE - (right - left)) // 2 - left, y + TILE - (bottom - top) - TILE // 10 - top), code, fill=label_colour(code), font=font)
	with io.BytesIO() as out:
		im.save(out, format='PNG')
		return out.getvalue()
