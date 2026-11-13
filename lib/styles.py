# key: (button label, short phrase appended to the prompt). Kept in alphabetical order of label: the buttons appear in this order.
# Removing a style leaves its saved images in old records; a press of its button on an old message just refreshes the buttons.
STYLES = {
	'render3d':    ('3D render', 'as a 3D render'),
	'8bit':        ('8-bit', 'as 8-bit pixel art'),
	'anime':       ('Anime', 'as anime art'),
	'birdseye':    ("Bird's eye", "seen from a bird's eye view"),
	'bw':          ('Black & white', 'in black & white'),
	'cartoon':     ('Cartoon', 'as a cartoon'),
	'comicbook':   ('Comic book', 'as a comic book illustration'),
	'cyberpunk':   ('Cyberpunk', 'as cyberpunk art'),
	'ega':         ('EGA', 'as EGA 16-color pixel art'),
	'lithograph':  ('Lithograph', 'as a lithograph print'),
	'monet':       ('Monet', 'in the style of Claude Monet'),
	'photo':       ('Photo', 'as a photograph'),
	'picasso':     ('Picasso', 'in the style of Pablo Picasso'),
	'popart':      ('Pop art', 'as pop art'),
	'stamp':       ('Rubber stamp', 'as a rubber stamp print'),
	'stencil':     ('Stencil', 'as stencil art'),
	'ukiyoe':      ('Ukiyo-e', 'as a ukiyo-e woodblock print'),
	'vangogh':     ('Van Gogh', 'in the style of Vincent van Gogh'),
	'watercolour': ('Watercolour', 'as a watercolour painting'),
	'wormseye':    ("Worm's eye", "seen from a worm's eye view"),
}

# Buttons that change the camera angle, not the art style: the prompt keeps its own style words (an oil painting stays
# an oil painting, seen from above), and variations don't use them as a style.
VIEWPOINTS = {'birdseye', 'wormseye'}

import unicodedata

def fold(text):
	"""Lower-case and strip accents, so 'Dalí' matches 'Dali' and 'Photo' matches 'PHOTOGRAPH'."""
	return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).casefold()

def contains_label(text, label):
	return fold(label) in fold(text)

# The button text must appear in the prompt (a substring: "Photo" is in "as a photograph"),
# so what you press is what the model is told. Fail at start-up if an edit breaks that.
for _key, (_label, _cue) in STYLES.items():
	assert contains_label(_cue, _label), f"style {_key!r}: button text {_label!r} is not in its phrase {_cue!r}"

def with_style(prompt, style, fix=None):
	"""prompt + the style phrase, checked to contain the button text.
	If it doesn't, fix(prompt, label) (a model) gets one chance to repair it, and as a last resort we append the label."""
	label, cue = STYLES[style]
	styled = prompt.rstrip(' .,;:!?') + ', ' + cue # no 'alleyway., as stencil art'
	if not contains_label(styled, label) and fix:
		styled = fix(styled, label) or styled
	if not contains_label(styled, label):
		styled += ', ' + label
	return styled
