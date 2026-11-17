"""The main colours of a picture, drawn as a grid of tiles each labelled with its hex code (#palette, #hex).

Everything happens here with Pillow: no image model is asked, so it costs nothing. The bot records the result with
kind 'palette', so a gallery can leave palettes out."""
import io

COLOURS = 8 # tiles in the grid, most common colour first (16 with the "16 colours" button)
COLUMNS = 4
TILE = 256 # pixels per side of each tile

GROUPS = 24 # colour groups found first; the colours shown are chosen from these
MIN_DIFFERENCE = 24 # how different (CIE Lab distance) two chosen colours must look; about 2 is barely visible
LIGHT = 80 # Lab lightness from which a colour counts as light (cream, white)
LIGHT_SHARE = 0.03 # a light area at least this big always gets a tile
MODES = ('vivid', 'average')

TONES = (('Shadows', 0, 35), ('Midtones', 35, 70), ('Highlights', 70, 101)) # bands of Lab lightness
TONE_COLOURS = 4 # tiles per band in the Tones view
TONE_MIN_SHARE = 0.01 # a band with less of the picture than this is left empty

def load(image_bytes):
	"""The picture's pixels as (r, g, b), from a small copy of it. Raises if the picture can't be read."""
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
	return list(getattr(im, 'get_flattened_data', im.getdata)()) # getdata is going in Pillow 14

def colours(image_bytes, number=COLOURS, mode='vivid'):
	"""The picture's main colours as hex codes ('#1A2B3C'), most common first. Raises if the picture can't be read.
	See choose() for how they are picked and what mode does."""
	return choose(load(image_bytes), number, mode)

def tones(image_bytes, mode='vivid'):
	"""The main colours of the picture's shadows, midtones and highlights: [(band name, [hex codes])], up to
	TONE_COLOURS each, most common first. A band with almost none of the picture in it has no colours."""
	pixels = load(image_bytes)
	bands = []
	for name, low, high in TONES:
		inside = [p for p in pixels if low <= lightness(p) < high]
		bands.append((name, choose(inside, TONE_COLOURS, mode, light_tile=False) if len(inside) >= TONE_MIN_SHARE * len(pixels) else []))
	return bands

def choose(pixels, number=COLOURS, mode='vivid', light_tile=True):
	"""The main colours among pixels as hex codes, most common first.

	The pixels are sorted into GROUPS colour groups. Groups are chosen by both how much of the picture they cover and
	how much they stand out (colourful, or light), skipping any that look almost the same as one already chosen, so a
	small bright accent can win a place over a third shade of dark grey. With light_tile, a light area (white fur,
	a cream band) of at least LIGHT_SHARE always gets a tile.
	mode is how each chosen group is shown: 'vivid', the most vivid colour that is common in it (a colour that really
	appears); or 'average', the average of its pixels, which shading pulls darker and greyer.
	The same groups are chosen in every mode, so the modes can be compared tile by tile."""
	from PIL import Image
	im = Image.new('RGB', (len(pixels), 1))
	im.putdata(pixels)
	groups = {}
	quantized = im.quantize(colors=GROUPS, method=Image.Quantize.MEDIANCUT, kmeans=2)
	for pixel, group in zip(pixels, getattr(quantized, 'get_flattened_data', quantized.getdata)()):
		groups.setdefault(group, []).append(pixel)
	candidates = [] # (score, share, vivid colour, members)
	for members in groups.values():
		colour = vivid_common(members)
		share = len(members) / len(pixels)
		# area counts, and so does standing out: being colourful, or being light (pale wings in a dark picture)
		candidates.append((share ** 0.6 * (0.45 + chroma(colour) / 255 + 0.35 * lab(colour)[0] / 100), share, colour, members))
	candidates.sort(key=lambda c: c[0], reverse=True)
	chosen = []
	for limit in (MIN_DIFFERENCE, MIN_DIFFERENCE / 2): # a second, looser pass if a picture has few distinct colours
		for candidate in candidates:
			if len(chosen) < number and candidate not in chosen and all(difference(candidate[2], other[2]) >= limit for other in chosen):
				chosen.append(candidate)
	is_light = lambda candidate: lab(candidate[2])[0] >= LIGHT
	if light_tile and not any(is_light(c) for c in chosen):
		lights = sorted((c for c in candidates if is_light(c)), key=lambda c: c[1], reverse=True)
		light = sum(c[1] for c in lights) # all light groups together: white fur can be spread over several
		if lights and light >= LIGHT_SHARE:
			if len(chosen) >= number:
				chosen.pop() # the last one chosen stood out least
			chosen.append(lights[0])
	chosen.sort(key=lambda c: c[1], reverse=True) # most common first
	shown = []
	for score, share, colour, members in chosen:
		if mode == 'average':
			colour = tuple(sum(p[i] for p in members) / len(members) for i in range(3))
		shown.append('#{:02X}{:02X}{:02X}'.format(*(round(c) for c in colour)))
	return shown

_LINEAR = [c / 255 / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in range(256)]

def lightness(pixel):
	"""Lab lightness (0 black to 100 white) of an (r, g, b) pixel, quickly: a table instead of powers."""
	y = 0.2126 * _LINEAR[pixel[0]] + 0.7152 * _LINEAR[pixel[1]] + 0.0722 * _LINEAR[pixel[2]]
	return 116 * y ** (1 / 3) - 16 if y > 0.008856 else 903.3 * y

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

def _font(size):
	from PIL import ImageFont
	try:
		return ImageFont.load_default(size=size)
	except (TypeError, OSError): # an old Pillow, or one without FreeType: a small bitmap font
		return ImageFont.load_default()

def _tile(draw, x, y, code, font):
	draw.rectangle((x, y, x + TILE - 1, y + TILE - 1), fill=code)
	left, top, right, bottom = draw.textbbox((0, 0), code, font=font)
	draw.text((x + (TILE - (right - left)) // 2 - left, y + TILE - (bottom - top) - TILE // 10 - top), code, fill=label_colour(code), font=font)

def tones_grid(bands):
	"""A PNG of the Tones view: one row per band, its name on the left, then its colours as labelled tiles."""
	from PIL import Image, ImageDraw
	label_width = TILE * 3 // 4
	im = Image.new('RGB', (label_width + TONE_COLOURS * TILE, len(bands) * TILE), (255, 255, 255))
	draw = ImageDraw.Draw(im)
	font, name_font = _font(TILE // 7), _font(TILE // 8)
	for row, (name, hexes) in enumerate(bands):
		y = row * TILE
		left, top, right, bottom = draw.textbbox((0, 0), name, font=name_font)
		draw.text(((label_width - (right - left)) // 2 - left, y + (TILE - (bottom - top)) // 2 - top), name, fill=(0, 0, 0), font=name_font)
		for i, code in enumerate(hexes):
			_tile(draw, label_width + i * TILE, y, code, font)
		if not hexes:
			draw.text((label_width + TILE // 4, y + TILE // 2 - TILE // 14), 'none in this picture', fill=(120, 120, 120), font=font)
	with io.BytesIO() as out:
		im.save(out, format='PNG')
		return out.getvalue()

def grid(hexes):
	"""A PNG of the colours as square tiles, COLUMNS to a row, each with its hex code written on it."""
	from PIL import Image, ImageDraw
	columns = min(COLUMNS, len(hexes))
	rows = -(-len(hexes) // columns)
	im = Image.new('RGB', (columns * TILE, rows * TILE), (255, 255, 255))
	draw = ImageDraw.Draw(im)
	font = _font(TILE // 7)
	for i, code in enumerate(hexes):
		_tile(draw, (i % columns) * TILE, (i // columns) * TILE, code, font)
	with io.BytesIO() as out:
		im.save(out, format='PNG')
		return out.getvalue()
