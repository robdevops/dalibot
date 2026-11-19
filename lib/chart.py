"""Technical pictures that must be to scale, drawn by the bot itself with Pillow.

An image model can't measure: asked for orbits or distances to scale, it spreads things out to look balanced and
contradicts its own ruler. So when a picture must be to scale, the planning model describes it as data (a spec, see
draw) and this draws it: every orbit, tick and position is where the numbers say. Items too close to tell apart at the
full scale are shown again in zoomed insets, each to scale and with its own ruler. Around it: a title, a subtitle, a
table, a legend and a footnote, as an infographic. No image model is asked, so it costs nothing."""
import io
import math

WIDTH, HEIGHT = 1600, 900
BACKGROUND = (11, 22, 48)
PANEL = (20, 35, 68)
GRID = (52, 72, 110)
TEXT = (235, 240, 250)
MUTED = (150, 170, 205)
HEADING = (120, 200, 255)
ACCENT = (255, 152, 0)
SUN = (255, 213, 79)
PALETTE = [(79, 195, 247), (255, 167, 38), (255, 213, 79), (129, 199, 132), (186, 104, 200), (240, 98, 146), (144, 164, 174), (255, 112, 67)]
LAYOUTS = ('orbits', 'line')
SAVED = 'To-scale chart drawn by the bot: ' # starts the saved 'base' of a chart, so Retry knows to plan it afresh
MAX_ITEMS = 24
MAX_COLUMNS, MAX_ROWS = 5, 16
MIN_GAP = 26 # pixels between neighbouring items below which they are too close to label apart
YEAR_UNITS = ('year', 'years', 'yr', 'ad', 'ce', 'bc', 'bce')
SUBSTITUTES = {'—': ' - ', '–': '-', '×': 'x', '≈': '~', '−': '-', '’': "'", '‘': "'", '“': '"', '”': '"', '…': '...'}

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
	return number if math.isfinite(number) else None

def _label(value, plain=None):
	"""A number as it is written on the picture: no needless decimals, and thousands separators unless plain (years)."""
	if plain:
		return f'{value:.0f}' if value == int(value) else f'{value:g}'
	return f'{value:,.2f}'.rstrip('0').rstrip('.') if abs(value) < 1000 else f'{value:,.0f}'

def nice_ticks(low, high, count=6):
	"""Round tick values covering low to high: steps of 1, 2, 2.5 or 5 times a power of ten."""
	if high <= low:
		return [low]
	raw = (high - low) / max(1, count)
	power = 10 ** math.floor(math.log10(raw))
	step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)
	value = math.ceil(low / step - 1e-9) * step
	ticks = []
	while value <= high + 1e-9 * step:
		ticks.append(round(value, 10))
		value += step
	return ticks

def check(spec):
	"""A spec that can be drawn, tidied, or None. See draw for its fields."""
	if not isinstance(spec, dict) or spec.get('layout') not in LAYOUTS:
		return None
	orbits = spec['layout'] == 'orbits'
	items = []
	for item in (spec.get('items') or [])[:MAX_ITEMS]:
		value = _number(item.get('value')) if isinstance(item, dict) else None
		if value is not None and _text(item.get('name')) and (value >= 0 or not orbits):
			items.append({'name': _text(item.get('name'), 40), 'value': value, 'group': _text(item.get('group'), 30),
				'label': _text(item.get('label'), 50), 'dashed': bool(item.get('dashed'))})
	if len(items) < 2:
		return None
	items.sort(key=lambda i: i['value'])
	low, high = items[0]['value'], items[-1]['value']
	start = 0.0 if orbits else _number(spec.get('start'))
	if start is None: # a line starts at 0, unless its values are all far from it (a timeline of years): then near the first
		start = 0.0 if 0 <= low <= 0.4 * high else low - (high - low) * 0.06
	start = min(start, low)
	if high - start <= 0:
		return None
	table = spec.get('table') if isinstance(spec.get('table'), dict) else {}
	columns = [_text(c, 30) for c in (table.get('columns') or [])][:MAX_COLUMNS]
	rows = [[_text(cell, 30) for cell in row][:len(columns)] for row in (table.get('rows') or []) if isinstance(row, list)] if columns else []
	highlight = [i for i in (table.get('highlight') or []) if isinstance(i, int) and 0 <= i < min(len(rows), MAX_ROWS)]
	unit = _text(spec.get('unit'), 12)
	return {'layout': spec['layout'], 'title': _text(spec.get('title'), 80), 'subtitle': _text(spec.get('subtitle'), 160),
		'unit': unit, 'centre': _text(spec.get('centre'), 30), 'start': start, 'items': items, 'plain': unit.lower() in YEAR_UNITS,
		'table': {'columns': columns, 'rows': rows[:MAX_ROWS], 'more': max(0, len(rows) - MAX_ROWS), 'highlight': highlight},
		'footnote': _text(spec.get('footnote'), 200)}

def _colours(items):
	groups = []
	for item in items:
		if item['group'] not in groups:
			groups.append(item['group'])
	return {group: PALETTE[i % len(PALETTE)] for i, group in enumerate(groups)}

def _groups(items, start, jump=2.0):
	"""The items split where the distance from the start jumps (the next is at least jump times further), innermost
	group first: for the solar system, the inner planets, the giant planets, then anything far beyond."""
	groups = [[items[0]]]
	for previous, item in zip(items, items[1:]):
		if previous['value'] - start > 0 and (item['value'] - start) / (previous['value'] - start) >= jump:
			groups.append([item])
		else:
			groups[-1].append(item)
	return groups

def _fits(group, start, maximum, extent):
	"""Can this group's items be told apart in a view of extent pixels from start to maximum? Neighbouring labels sit
	on alternate sides, so half the crowding gap between neighbours is enough."""
	scale = extent / (maximum - start)
	values = [start] + [i['value'] for i in group]
	return all((b - a) * scale >= MIN_GAP / 2 for a, b in zip(values, values[1:]))

MIN_ZOOM = 1.5 # an inset that wouldn't magnify at least this much isn't worth it: its group stays in the view outside

def _levels(items, start, extent, inset_extent, insets=2):
	"""The views to draw, [(items shown, maximum, items labelled)]: the full view first, then zoomed insets, each to
	scale. Each view labels one group of items (see _groups), the outermost in the full view; a group that can be told
	apart in the view outside it shares that view instead of getting its own."""
	groups = _groups(items, start)
	levels = [(items, items[-1]['value'], list(groups.pop()))]
	while groups:
		group = groups.pop()
		shown, maximum, labelled = levels[-1]
		size = extent if len(levels) == 1 else inset_extent
		zoom_max = start + (group[-1]['value'] - start) * 1.12
		zoom = (inset_extent / (zoom_max - start)) / (size / (maximum - start))
		if _fits(group, start, maximum, size) or len(levels) > insets or zoom < MIN_ZOOM:
			labelled.extend(group) # fits where it is, or no room for another inset, or one wouldn't magnify it
			continue
		inner = [i for i in items if i['value'] <= group[-1]['value']]
		levels.append((inner, zoom_max, list(group)))
	return levels

def _item_label(item, unit, plain):
	return item['label'] or f"{item['name']} {_label(item['value'], plain)}" + (f' {unit}' if unit and not plain else '')

def _dashed_circle(draw, centre, radius, colour, width=2, dash=10):
	steps = max(12, int(2 * math.pi * radius / dash))
	for i in range(0, steps, 2):
		a, b = 2 * math.pi * i / steps, 2 * math.pi * (i + 1) / steps
		draw.line([(centre[0] + radius * math.cos(a), centre[1] + radius * math.sin(a)), (centre[0] + radius * math.cos(b), centre[1] + radius * math.sin(b))], fill=colour, width=width)

def _tick_count(draw, low, high, width, plain, unit, font):
	"""As many ticks as fit side by side in width, judged by the widest label they would have."""
	count = 6
	while count > 2:
		ticks = nice_ticks(low, high, count)
		widest = max(_width(draw, _label(t, plain) + (f' {unit}' if unit else ''), font) for t in ticks)
		if len(ticks) * (widest + 24) <= width:
			break
		count -= 1
	return count

def _orbits(draw, box, items, colours, unit, centre_name, labelled, maximum, plain):
	"""Circles around a centre, each radius exactly item value * scale, each labelled item a dot on its circle, and a
	numbered radial ruler. Returns (pixels per unit, items that could not be labelled)."""
	x0, y0, x1, y1 = box
	centre = ((x0 + x1) / 2, (y0 + y1) / 2 + 10)
	radius = min(x1 - x0, y1 - y0) / 2 - 30
	scale = radius / maximum
	font, small = _font(19 if radius > 150 else 16), _font(16 if radius > 150 else 14)
	angle = -math.pi / 4 # the ruler, along the upper right diagonal
	for tick in nice_ticks(0, maximum, 5 if radius > 150 else 3)[1:]: # not 0: that is the centre, with its own label
		r = tick * scale
		x, y = centre[0] + r * math.cos(angle), centre[1] + r * math.sin(angle)
		draw.line([(x - 5, y - 5), (x + 5, y + 5)], fill=MUTED, width=2)
		draw.text((x + 8, y - 20), _label(tick, plain), fill=MUTED, font=small)
	end = (centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle))
	draw.line([centre, end], fill=GRID, width=1)
	if unit:
		draw.text((min(end[0] + 8, x1 - 6 - _width(draw, unit, small)), end[1] - 6), unit, fill=MUTED, font=small)
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
			draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=colour, outline=BACKGROUND, width=2)
			text = _item_label(item, unit, plain)
			w = _width(draw, text, font)
			tx = x + 12 if side == 0 else x - 12 - w
			tx = min(max(tx, x0 + 6), x1 - 6 - w) # kept inside its panel
			draw.text((tx, y - 10), text, fill=TEXT, font=font)
			side = 1 - side
	draw.ellipse([centre[0] - 8, centre[1] - 8, centre[0] + 8, centre[1] + 8], fill=SUN)
	if centre_name: # above left: the labels are below, on the two rays
		draw.text((max(x0 + 6, centre[0] - 12 - _width(draw, centre_name, small)), centre[1] - 28), centre_name, fill=TEXT, font=small)
	return scale, []

def _line(draw, box, items, colours, unit, centre_name, labelled, start, maximum, plain):
	"""A horizontal axis from start to maximum, each item a dot at exactly (value - start) * scale, numbered ticks, and
	labels in the first free row, above or below. Returns (pixels per unit, items there was no room to label)."""
	x0, y0, x1, y1 = box
	axis_y = (y0 + y1) / 2
	left, right = x0 + 30, x1 - 40
	scale = (right - left) / (maximum - start)
	small = _font(16 if x1 - x0 > 400 else 14)
	font = _font(19 if x1 - x0 > 400 else 16)
	draw.line([(left, axis_y), (right + 20, axis_y)], fill=MUTED, width=3)
	draw.polygon([(right + 30, axis_y), (right + 18, axis_y - 7), (right + 18, axis_y + 7)], fill=MUTED)
	ticks = nice_ticks(start, maximum, _tick_count(draw, start, maximum, right - left, plain, unit, small))
	for tick in ticks:
		x = left + (tick - start) * scale
		draw.line([(x, axis_y), (x, axis_y + 10)], fill=MUTED, width=2)
		text = _label(tick, plain) + (f' {unit}' if unit and not plain and tick == ticks[0] else '')
		if tick == 0 and centre_name: # what is at 0 is named at its tick
			text = f'{centre_name} {text}'
		draw.text((min(max(x - _width(draw, text, small) / 2, x0 + 4), x1 - 4 - _width(draw, text, small)), axis_y + 14), text, fill=MUTED, font=small)
	if centre_name and start <= 0 <= maximum:
		x = left - start * scale
		draw.ellipse([x - 9, axis_y - 9, x + 9, axis_y + 9], fill=SUN)
	# label rows, nearest first, kept to those inside the panel
	rows = [r for r in (axis_y - 54, axis_y + 38, axis_y - 86, axis_y + 70, axis_y - 118, axis_y + 102) if r >= y0 + 4 and r + 22 <= y1 - 4]
	taken = {row: [] for row in rows}
	unlabelled = []
	for item in items:
		x = left + (item['value'] - start) * scale
		colour = colours[item['group']]
		draw.ellipse([x - 7, axis_y - 7, x + 7, axis_y + 7], fill=colour, outline=BACKGROUND, width=2)
		if item not in labelled:
			continue
		text = _item_label(item, unit, plain)
		w = _width(draw, text, font)
		tx = min(max(x - w / 2, x0 + 6), x1 - 6 - w)
		row = next((r for r in rows if all(tx > b + 10 or tx + w < a - 10 for a, b in taken[r])), None)
		if row is None: # no room left: listed in a note instead of written over another label
			unlabelled.append(item)
			continue
		taken[row].append((tx, tx + w))
		above = row < axis_y
		draw.line([(x, axis_y - 9 if above else axis_y + 9), (x, row + (22 if above else 0))], fill=colour, width=1)
		draw.text((tx, row), text, fill=TEXT, font=font)
	return scale, unlabelled

def _table(draw, box, table):
	x0, y0, x1, y1 = box
	columns, rows = table['columns'], table['rows']
	if not columns or not rows:
		return y0
	lines = len(rows) + 1 + (1 if table['more'] else 0)
	row_h = min(34, (y1 - y0) // lines)
	size = max(12, min(19, row_h - 12))
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
	bottom = y0 + row_h * (len(rows) + 1)
	if table['more']:
		draw.text((x0 + 10, bottom + 6), f"+{table['more']} more rows not shown", fill=MUTED, font=_font(max(12, size - 2)))
		bottom += row_h
	return bottom

def _legend(draw, box, colours):
	"""Coloured dots and group names, wrapped onto more lines if they need it, and shortened if even that won't do."""
	x0, y0, x1, y1 = box
	x, y = x0, y0
	for group, colour in colours.items():
		if not group:
			continue
		text, f = _fit(draw, group, 17, x1 - x0 - 24)
		w = 24 + _width(draw, text, f)
		if x + w > x1 and x > x0:
			x, y = x0, y + 26
		if y + 20 > y1:
			break
		draw.ellipse([x, y + 4, x + 14, y + 18], fill=colour)
		draw.text((x + 20, y), text, fill=TEXT, font=f)
		x += w + 16

def draw(spec):
	"""A PNG of a to-scale infographic, from a spec checked by check():
	layout 'orbits' (circles around a centre, e.g. planets' orbits) or 'line' (positions along one axis); title;
	subtitle; unit (e.g. 'AU', or 'year' for a timeline); centre (what is at 0, e.g. 'Sun'); start (line only: where
	the axis starts, if not 0, e.g. for years); items, each {name, value (a number, in unit), group (for colour and the
	legend), label (optional, else name and value), dashed (optional, for an orbit drawn dashed)}; table {columns,
	rows, highlight (row numbers)}; footnote."""
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
		d.text((42, 88), subtitle, fill=HEADING, font=subtitle_font)
	items, colours, unit, plain, start = spec['items'], _colours(spec['items']), spec['unit'], spec['plain'], spec['start']
	orbits = spec['layout'] == 'orbits'
	main = (30, 135, 930, 840)
	right = (960, 135, WIDTH - 30, 840)
	d.rounded_rectangle(main, radius=14, fill=PANEL)
	inset_height = 300 if orbits else 220
	levels = _levels(items, start, (min(main[2] - main[0], main[3] - main[1]) / 2 - 30) if orbits else (main[2] - main[0] - 70),
		(min((right[2] - right[0]) / 2 - 8, inset_height - 30) / 2 - 30) if orbits else ((right[2] - right[0]) / 2 - 78))
	scales, unlabelled = [], []
	for n, (shown, view_max, labelled) in enumerate(levels):
		header = None
		if n == 0:
			box = main if orbits else (main[0], main[1] + 60, main[2], main[3] - 60)
		else: # the insets side by side across the top of the right-hand panel
			count = len(levels) - 1
			width = (right[2] - right[0] - 16 * (count - 1)) / count
			bx = right[0] + (n - 1) * (width + 16)
			box = (bx, right[1], bx + width, right[1] + inset_height)
			d.rounded_rectangle(box, radius=12, fill=PANEL, outline=GRID)
			header = (box[0] + 14, box[1] + 10)
			box = (box[0], box[1] + 30, box[2], box[3])
		if orbits:
			scale, missed = _orbits(d, box, shown, colours, unit, spec['centre'], labelled, view_max, plain)
		else:
			scale, missed = _line(d, box, shown, colours, unit, spec['centre'], labelled, start, view_max, plain)
		scales.append(scale)
		unlabelled += missed
		if header: # the zoom, from the real pixel scales of this view and the full one
			factor = scale / scales[0]
			d.text(header, f"Zoom x{_label(round(factor, 1) if factor < 10 else round(factor))}, to scale", fill=HEADING, font=_font(18))
	notes = []
	if len(levels) > 1:
		elsewhere = sorted((i for level in levels[1:] for i in level[2]), key=lambda i: i['value'])
		notes.append(f"{', '.join(i['name'] for i in elsewhere)}: labelled in the zoom")
	if unlabelled: # no room for their labels anywhere: their values are given here instead
		notes.append("Not labelled for lack of room: " + ', '.join(_item_label(i, unit, plain) for i in unlabelled))
	for k, note in enumerate(notes):
		text, font = _fit(d, note, 17, main[2] - main[0] - 40)
		d.text((main[0] + 20, main[1] + 14 + 24 * k), text, fill=MUTED, font=font)
	y = right[1] + (inset_height + 20 if len(levels) > 1 else 0)
	bottom = _table(d, (right[0], y, right[2], right[3] - 70), spec['table'])
	_legend(d, (right[0], bottom + 16 if spec['table']['rows'] else y, right[2], right[3]), colours)
	footnote = spec['footnote'] or ('Orbits to scale.' if orbits else 'Positions to scale.')
	text, font = _fit(d, footnote, 18, WIDTH - 80)
	d.text((40, HEIGHT - 42), text, fill=MUTED, font=font)
	with io.BytesIO() as out:
		im.save(out, format='PNG')
		return out.getvalue()
