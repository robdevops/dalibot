# key: (button label, short phrase appended to the prompt)
STYLES = {
	'monet':       ('Monet', 'in the style of Claude Monet'),
	'dali':        ('Dalí', 'in the style of Salvador Dalí'),
	'picasso':     ('Picasso', 'in the style of Pablo Picasso'),
	'8bit':        ('8-bit', 'as 8-bit pixel art'),
	'ega':         ('EGA', 'as EGA 16-color pixel art'),
	'photo':       ('Photo', 'as a photograph'),
	'watercolour': ('Watercolour', 'as a watercolour painting'),
	'handdrawn':   ('Hand drawn', 'as a hand drawn illustration'),
	'sketch':      ('Sketch', 'as a pencil sketch'),
	'lithograph':  ('Lithograph', 'as a lithograph print'),
	'stamp':       ('Rubber stamp', 'as a rubber stamp print'),
	'tattoo':      ('Tattoo', 'as a tattoo design'),
	'stencil':     ('Stencil', 'as stencil art'),
}

# The button text must appear in the prompt (case-insensitive substring: "Photo" is in "as a photograph"),
# so what you press is what the model is told. Fail at start-up if an edit breaks that.
for _key, (_label, _cue) in STYLES.items():
	assert _label.lower() in _cue.lower(), f"style {_key!r}: button text {_label!r} is not in its phrase {_cue!r}"

def with_style(prompt, style):
	"""prompt + the style phrase, guaranteed to contain the button text."""
	label, cue = STYLES[style]
	styled = prompt + ', ' + cue
	if label.lower() not in styled.lower():
		styled += ', ' + label
	return styled
