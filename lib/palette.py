"""The main colours of a picture, drawn as a grid of tiles each labelled with its hex code (#palette, #hex).

Everything happens here with Pillow: no image model is asked, so it costs nothing. The result is not saved to the
image history, because it is a tool, not a picture."""
import io

COLOURS = 8 # tiles in the grid, most common colour first
COLUMNS = 4
TILE = 256 # pixels per side of each tile

GROUPS = 24 # colour groups found first; the COLOURS shown are chosen from these
MIN_DIFFERENCE = 24 # how different (CIE Lab distance) two chosen colours must look; about 2 is barely visible

def colours(image_bytes, number=COLOURS):
	"""The picture's main colours as hex codes ('#1A2B3C'), most common first. Raises if the picture can't be read.

	The pixels are sorted into GROUPS colour groups. From each, the colour shown is the most vivid colour that is
	common in it (a colour that really appears, not the group's average, which shading pulls darker and greyer).
	The groups are then chosen by both how much of the picture they cover and how vivid they are, skipping any
	that look almost the same as one already chosen, so a small bright accent can win a place over a third shade
	of dark grey."""
	from PIL import Image
	im = Image.open(io.BytesIO(image_bytes))
	if im.mode in ('RGBA', 'LA', 'P', 'PA') or 'transparency' in im.info:
		im = im.convert('RGBA')
		background = Image.new('RGB', im.size, (255, 255, 255)) # transparency counts as white, as Telegram shows it
		background.paste(im, mask=im.getchannel('A'))
		im = background
	else:
		im = im.convert('RGB')
	im.thumbnail((160, 160)) # plenty to find the main colours, and fast
	flat = getattr(im, 'get_flattened_data', im.getdata) # getdata is going in Pillow 14
	pixels = list(flat())
	groups = {}
	quantized = im.quantize(colors=GROUPS, method=Image.Quantize.MEDIANCUT, kmeans=2)
	for pixel, group in zip(pixels, getattr(quantized, 'get_flattened_data', quantized.getdata)()):
		groups.setdefault(group, []).append(pixel)
	candidates = [] # (score, share, colour)
	for members in groups.values():
		colour = vivid_common(members)
		share = len(members) / len(pixels)
		# area counts, and so does standing out: being colourful, or being light (pale wings in a dark picture)
		candidates.append((share ** 0.6 * (0.45 + chroma(colour) / 255 + 0.35 * lab(colour)[0] / 100), share, colour))
	candidates.sort(reverse=True)
	chosen = []
	for limit in (MIN_DIFFERENCE, MIN_DIFFERENCE / 2): # a second, looser pass if a picture has few distinct colours
		for score, share, colour in candidates:
			if len(chosen) < number and all(difference(colour, other) >= limit for _, other in chosen):
				chosen.append((share, colour))
	chosen.sort(reverse=True) # most common first
	return ['#{:02X}{:02X}{:02X}'.format(*colour) for share, colour in chosen]

def chroma(colour):
	"""How colourful an (r, g, b) colour is, 0 for grey to 255 for a pure hue."""
	return max(colour) - min(colour)

def vivid_common(members):
	"""The colour that best represents one group: among the shades it contains (grouped into small steps), the one
	that is both common and vivid. Returns the most frequent actual pixel colour in that shade."""
	shades = {}
	for pixel in members:
		shades.setdefault((pixel[0] >> 3, pixel[1] >> 3, pixel[2] >> 3), []).append(pixel)
	best = max(shades.values(), key=lambda shade: len(shade) ** 0.5 * (0.25 + chroma(shade[0]) / 255) ** 2) # favour the bright red of an eye over its dark edge
	counts = {}
	for pixel in best:
		counts[pixel] = counts.get(pixel, 0) + 1
	return max(counts, key=counts.get)

def lab(colour):
	"""(r, g, b) to CIE Lab, where the distance between two colours follows how different they look."""
	def linear(c):
		c /= 255
		return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
	r, g, b = (linear(c) for c in colour)
	x, y, z = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * b, (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
	f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
	return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))

def difference(a, b):
	return sum((p - q) ** 2 for p, q in zip(lab(a), lab(b))) ** 0.5

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
