"""Technical pictures that must be to scale, drawn by the bot itself with Pillow.

An image model can't measure: asked for orbits or distances to scale, it spreads things out to look balanced and
contradicts its own ruler. So when a picture must be to scale, the planning model describes it as data (a spec, see
draw) and this draws it: every orbit, tick and position is where the numbers say. Inner items too close to tell apart at
the full scale are shown again in a zoomed inset, itself to scale. Around it: a title, a subtitle, a table, a legend and
a footnote, as an infographic. No image model is asked, so it costs nothing."""
import io
import math

WIDTH, HEIGHT = 1600, 900
BACKGROUND = (11, 22, 48)
PANEL = (20, 35, 68)
GRID = (52, 72, 110)
TEXT = (235, 240, 250)
MUTED = (150, 170, 205)
ACCENT = (255, 152, 0)
PALETTE = [(79, 195, 247), (255, 167, 38), (255, 213, 79), (129, 199, 132), (186, 104, 200), (240, 98, 146), (144, 164, 174), (255, 112, 67)]
LAYOUTS = ('orbits', 'line')
SAVED = 'To-scale chart drawn by the bot: ' # starts the saved 'base' of a chart, so Retry knows to plan it afresh
MAX_ITEMS = 24
MIN_GAP = 26 # pixels between neighbouring items below which they go to the zoomed inset

def _font(size):
	from PIL import ImageFont
	try:
		return ImageFont.load_default(size=size)
	except (TypeError, OSError): # an old Pillow, or one without FreeType: a small bitmap font
		return ImageFont.load_default()

def _width(draw, text, font):
	left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
	return right - left

def _fit(draw, text, size, max_width, smallest=12):
	"""The largest font, from size down, that fits text within max_width (the text is cut if even the smallest won't)."""
	while size > smallest and _width(draw, text, _font(size)) > max_width:
		size -= 1
	font = _font(size)
	while len(text) > 1 and _width(draw, text, font) > max_width:
		text = text[:-2] + '.'
	return text, font

SUBSTITUTES = {'\u2014': ' - ', '\u2013': '-', '\u00d7': 'x', '\u2248': '~', '\u2212': '-', '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"', '\u2026': '...'}

def _text(value, limit=120):
	"""Text as it can be drawn: on one line, short, and without characters the built-in font lacks."""
	text = ' '.join(str(value or '').split())
	for character, substitute in SUBSTITUTES.items():
		text = text.replace(character, substitute)
	return ' '.join(text.split())[:limit]

def _number(value):
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if math.isfinite(number) and number >= 0 else None

def _label(value):
	return f'{value:,.2f}'.rstrip('0').rstrip('.') if value < 1000 else f'{value:,.0f}'

def nice_ticks(maximum, count=6):
	"""Round tick values from 0 up to at least maximum: steps of 1, 2, 2.5 or 5 times a power of ten."""
	if maximum <= 0:
		return [0]
	raw = maximum / count
	power = 10 ** math.floor(math.log10(raw))
	step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)
	ticks, value = [], 0.0
	while value < maximum + step / 2:
		ticks.append(round(value, 10))
		value += step
	return ticks

def check(spec):
	"""A spec that can be drawn, tidied, or None. See draw for its fields."""
	if not isinstance(spec, dict) or spec.get('layout') not in LAYOUTS:
		return None
	items = []
	for item in (spec.get('items') or [])[:MAX_ITEMS]:
		if isinstance(item, dict) and _text(item.get('name')) and _number(item.get('value')) is not None:
			items.append({'name': _text(item.get('name'), 40), 'value': _number(item.get('value')), 'group': _text(item.get('group'), 30),
				'label': _text(item.get('label'), 50), 'dashed': bool(item.get('dashed'))})
	if len(items) < 2 or max(i['value'] for i in items) <= 0:
		return None
	table = spec.get('table') if isinstance(spec.get('table'), dict) else {}
	columns = [_text(c, 30) for c in (table.get('columns') or [])][:5]
	rows = [[_text(cell, 30) for cell in row][:len(columns)] for row in (table.get('rows') or []) if isinstance(row, list)][:16] if columns else []
	highlight = [i for i in (table.get('highlight') or []) if isinstance(i, int) and 0 <= i < len(rows)]
	return {'layout': spec['layout'], 'title': _text(spec.get('title'), 80), 'subtitle': _text(spec.get('subtitle'), 160),
		'unit': _text(spec.get('unit'), 12), 'centre': _text(spec.get('centre'), 30), 'items': sorted(items, key=lambda i: i['value']),
		'table': {'columns': columns, 'rows': rows, 'highlight': highlight}, 'footnote': _text(spec.get('footnote'), 200)}

def _colours(items):
	groups = []
	for item in items:
		if item['group'] not in groups:
			groups.append(item['group'])
	return {group: PALETTE[i % len(PALETTE)] for i, group in enumerate(groups)}

def _groups(items, jump=2.0):
	"""The items split where the distance jumps (the next is at least jump times further out), innermost group first:
	for the solar system, the inner planets, the giant planets, then anything far beyond."""
	groups = [[items[0]]]
	for previous, item in zip(items, items[1:]):
		if previous['value'] > 0 and item['value'] / previous['value'] >= jump:
			groups.append([item])
		else:
			groups[-1].append(item)
	return groups

def _fits(group, maximum, extent):
	"""Can this group's items be told apart in a view of extent pixels from 0 to maximum? Neighbouring labels sit on
	alternate sides, so half the crowding gap between neighbours is enough."""
	scale = extent / maximum
	values = [0.0] + [i['value'] for i in group]
	return all((b - a) * scale >= MIN_GAP / 2 for a, b in zip(values, values[1:]))

def _levels(items, extent, inset_extent, insets=2):
	"""The views to draw, [(items shown, maximum, items labelled)]: the full view first, then zoomed insets, each to
	scale. Each view labels one group of items (see _groups), the outermost in the full view; a group that can be told
	apart in the view outside it shares that view instead of getting its own."""
	groups = _groups(items)
	levels = [(items, items[-1]['value'], list(groups.pop()))]
	while groups:
		group = groups.pop()
		shown, maximum, labelled = levels[-1]
		size = extent if len(levels) == 1 else inset_extent
		if _fits(group, maximum, size) or len(levels) > insets: # fits where it is, or no room for another inset
			labelled.extend(group)
			continue
		inner = [i for i in items if i['value'] <= group[-1]['value']]
		levels.append((inner, group[-1]['value'] * 1.12, list(group)))
	return levels

def _item_label(item, unit):
	return item['label'] or f"{item['name']} {_label(item['value'])}" + (f' {unit}' if unit else '')

def _dashed_circle(draw, centre, radius, colour, width=2, dash=10):
	steps = max(12, int(2 * math.pi * radius / dash))
	for i in range(0, steps, 2):
		a, b = 2 * math.pi * i / steps, 2 * math.pi * (i + 1) / steps
		draw.line([(centre[0] + radius * math.cos(a), centre[1] + radius * math.sin(a)), (centre[0] + radius * math.cos(b), centre[1] + radius * math.sin(b))], fill=colour, width=width)

def _orbits(draw, box, items, colours, unit, centre_name, labelled, maximum, ruler=True):
	"""Circles around a centre, each radius exactly item value * scale, with each item a dot on its circle."""
	x0, y0, x1, y1 = box
	centre = ((x0 + x1) / 2, (y0 + y1) / 2 + 10)
	radius = min(x1 - x0, y1 - y0) / 2 - 30
	scale = radius / maximum
	font, small = _font(19), _font(16)
	if ruler: # a radial scale, exact, along the upper right diagonal
		angle = -math.pi / 4
		for tick in nice_ticks(maximum, 5)[1:]: # not 0: that is the centre, with its own label
			r = tick * scale
			if r > radius + 1:
				break
			x, y = centre[0] + r * math.cos(angle), centre[1] + r * math.sin(angle)
			draw.line([(x - 5, y - 5), (x + 5, y + 5)], fill=MUTED, width=2)
			draw.text((x + 8, y - 22), _label(tick), fill=MUTED, font=small)
		end = (centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle))
		draw.line([centre, end], fill=GRID, width=1)
		if unit:
			draw.text((end[0] + 8, end[1] - 8), unit, fill=MUTED, font=small)
	# labelled items alternate between two rays, down-right and down-left: neighbours on a ray are then at least two
	# crowding gaps apart, so their labels can't overlap
	rays = [math.radians(65), math.radians(115)]
	side = 0
	for item in items:
		r = item['value'] * scale
		colour = colours[item['group']]
		if item['dashed']:
			_dashed_circle(draw, centre, r, colour)
		else:
			draw.ellipse([centre[0] - r, centre[1] - r, centre[0] + r, centre[1] + r], outline=colour, width=2)
		if item in labelled:
			a = rays[side]
			x, y = centre[0] + r * math.cos(a), centre[1] + r * math.sin(a)
			draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=colour, outline=BACKGROUND, width=2)
			text = _item_label(item, unit)
			w = _width(draw, text, font)
			tx = x + 12 if side == 0 else x - 12 - w
			tx = min(max(tx, x0 + 6), x1 - 6 - w) # kept inside its panel
			draw.text((tx, y - 10), text, fill=TEXT, font=font)
			side = 1 - side
	draw.ellipse([centre[0] - 9, centre[1] - 9, centre[0] + 9, centre[1] + 9], fill=(255, 213, 79))
	if centre_name: # above left: the labels are below, on the two rays
		draw.text((centre[0] - 12 - _width(draw, centre_name, small), centre[1] - 30), centre_name, fill=TEXT, font=small)
	return centre, scale

def _line(draw, box, items, colours, unit, centre_name, labelled, maximum):
	"""A horizontal axis from 0 to maximum, each item a dot at exactly value * scale, labels alternating above and below."""
	x0, y0, x1, y1 = box
	axis_y = (y0 + y1) / 2
	left, right = x0 + 30, x1 - 40
	scale = (right - left) / maximum
	font, small = _font(19), _font(16)
	draw.line([(left, axis_y), (right + 20, axis_y)], fill=MUTED, width=3)
	draw.polygon([(right + 30, axis_y), (right + 18, axis_y - 7), (right + 18, axis_y + 7)], fill=MUTED)
	for tick in nice_ticks(maximum, 6):
		x = left + tick * scale
		if x > right + 1:
			break
		draw.line([(x, axis_y), (x, axis_y + 12)], fill=MUTED, width=2)
		text = _label(tick) + (f' {unit}' if unit and tick == 0 else '')
		if tick == 0 and centre_name: # what is at 0 is named at its tick, clear of the item labels
			text = f'{centre_name} {text}'
			draw.text((x - 4, axis_y + 16), text, fill=TEXT, font=small)
			continue
		draw.text((x - _width(draw, text, small) / 2, axis_y + 16), text, fill=MUTED, font=small)
	draw.ellipse([left - 10, axis_y - 10, left + 10, axis_y + 10], fill=(255, 213, 79))
	rows = [axis_y - 62, axis_y + 44, axis_y - 96, axis_y + 78] # label rows: above, below, further above, further below
	taken = {row: [] for row in rows}
	for item in items:
		x = left + item['value'] * scale
		colour = colours[item['group']]
		draw.ellipse([x - 7, axis_y - 7, x + 7, axis_y + 7], fill=colour, outline=BACKGROUND, width=2)
		if item in labelled:
			text = _item_label(item, unit)
			w = _width(draw, text, font)
			tx = min(max(x - w / 2, x0 + 6), x1 - 6 - w)
			row = next((r for r in rows if all(tx > b + 10 or tx + w < a - 10 for a, b in taken[r])), rows[-1])
			taken[row].append((tx, tx + w))
			above = row < axis_y
			draw.line([(x, axis_y - 9 if above else axis_y + 9), (x, row + (22 if above else 0))], fill=colour, width=1)
			draw.text((tx, row), text, fill=TEXT, font=font)
	return scale

def _table(draw, box, table):
	x0, y0, x1, y1 = box
	columns, rows = table['columns'], table['rows']
	if not columns or not rows:
		return y0
	row_h = min(34, (y1 - y0) // (len(rows) + 1))
	size = max(13, min(19, row_h - 12))
	font = _font(size)
	widths = [max([_width(draw, columns[c], font)] + [_width(draw, row[c], font) for row in rows if c < len(row)]) + 24 for c in range(len(columns))]
	total = sum(widths)
	widths = [w * (x1 - x0) / total for w in widths]
	draw.rectangle([x0, y0, x1, y0 + row_h], fill=GRID)
	x = x0
	for c, header in enumerate(columns):
		text, f = _fit(draw, header, size, widths[c] - 12)
		draw.text((x + 10, y0 + (row_h - size) / 2 - 1), text, fill=TEXT, font=f)
		x += widths[c]
	for r, row in enumerate(rows):
		y = y0 + row_h * (r + 1)
		if r in table['highlight']:
			draw.rectangle([x0, y, x1, y + row_h], fill=ACCENT)
		draw.line([(x0, y + row_h), (x1, y + row_h)], fill=GRID, width=1)
		x = x0
		for c in range(len(columns)):
			cell = row[c] if c < len(row) else ''
			text, f = _fit(draw, cell, size, widths[c] - 12)
			draw.text((x + 10, y + (row_h - size) / 2 - 1), text, fill=(20, 20, 30) if r in table['highlight'] else TEXT, font=f)
			x += widths[c]
	return y0 + row_h * (len(rows) + 1)

def draw(spec):
	"""A PNG of a to-scale infographic, from a spec checked by check():
	layout 'orbits' (circles around a centre, e.g. planets' orbits) or 'line' (positions along one axis); title;
	subtitle; unit (e.g. 'AU'); centre (what is at 0, e.g. 'Sun'); items, each {name, value (a number, in unit),
	group (for colour and the legend), label (optional, else name and value), dashed (optional, for an orbit drawn
	dashed)}; table {columns, rows, highlight (row numbers)}; footnote."""
	from PIL import Image, ImageDraw
	spec = check(spec)
	if not spec:
		raise ValueError('nothing that can be drawn to scale')
	im = Image.new('RGB', (WIDTH, HEIGHT), BACKGROUND)
	d = ImageDraw.Draw(im)
	title, title_font = _fit(d, spec['title'] or 'To scale', 50, WIDTH - 80)
	d.text((40, 24), title, fill=TEXT, font=title_font)
	if spec['subtitle']:
		subtitle, subtitle_font = _fit(d, spec['subtitle'], 24, WIDTH - 80)
		d.text((42, 88), subtitle, fill=(120, 200, 255), font=subtitle_font)
	items, colours, unit = spec['items'], _colours(spec['items']), spec['unit']
	maximum = max(i['value'] for i in items)
	main = (30, 135, 930, 840)
	d.rounded_rectangle(main, radius=14, fill=PANEL)
	right = (960, 135, WIDTH - 30, 840)
	orbits = spec['layout'] == 'orbits'
	inset_height = 300 if orbits else 220
	levels = _levels(items, (min(main[2] - main[0], main[3] - main[1]) / 2 - 30) if orbits else (main[2] - main[0] - 70),
		(min((right[2] - right[0]) / 2 - 8, inset_height - 30) / 2 - 30) if orbits else ((right[2] - right[0]) / 2 - 78))
	for n, (shown, view_max, labelled) in enumerate(levels):
		if n == 0:
			box = main if orbits else (main[0], main[1] + 120, main[2], main[3] - 120)
		else: # the insets side by side across the top of the right-hand panel
			count = len(levels) - 1
			width = (right[2] - right[0] - 16 * (count - 1)) / count
			bx = right[0] + (n - 1) * (width + 16)
			box = (bx, right[1], bx + width, right[1] + inset_height)
			d.rounded_rectangle(box, radius=12, fill=PANEL, outline=GRID)
			factor = levels[0][1] / view_max
			d.text((box[0] + 14, box[1] + 10), f"Zoom x{_label(round(factor, 1) if factor < 10 else round(factor))}, to scale", fill=(120, 200, 255), font=_font(18))
			box = (box[0], box[1] + 30, box[2], box[3])
		if orbits:
			_orbits(d, box, shown, colours, unit, spec['centre'], labelled, view_max, ruler=(n == 0))
		else:
			_line(d, box, shown, colours, unit, spec['centre'], labelled, view_max)
	if len(levels) > 1: # say where the others are labelled
		elsewhere = [i['name'] for i in sorted((i for level in levels[1:] for i in level[2]), key=lambda i: i['value'])]
		note, font = _fit(d, f"{', '.join(elsewhere)}: labelled in the zoom", 17, main[2] - main[0] - 40)
		d.text((main[0] + 20, main[1] + 14), note, fill=MUTED, font=font)
	y = right[1] + (inset_height + 20 if len(levels) > 1 else 0)
	bottom = _table(d, (right[0], y, right[2], right[3] - 60), spec['table'])
	x, ly = right[0], max(bottom + 16, right[3] - 40) if spec['table']['rows'] else y
	for group, colour in colours.items(): # the legend
		if not group:
			continue
		d.ellipse([x, ly + 4, x + 14, ly + 18], fill=colour)
		d.text((x + 20, ly), group, fill=TEXT, font=_font(17))
		x += 40 + _width(d, group, _font(17))
	footnote = spec['footnote'] or 'Distances to scale.'
	text, font = _fit(d, footnote, 18, WIDTH - 80)
	d.text((40, HEIGHT - 42), text, fill=MUTED, font=font)
	with io.BytesIO() as out:
		im.save(out, format='PNG')
		return out.getvalue()
