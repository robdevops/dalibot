import uuid

def encode(fields, files):
	"""Build a multipart/form-data body with the standard library.
	fields: {name: value}; files: {name: (filename, content_type, bytes)}. Returns (content_type, body)."""
	boundary = uuid.uuid4().hex
	body = b''
	for name, value in fields.items():
		body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
	for name, (filename, content_type, data) in files.items():
		body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
		body += data + b'\r\n'
	body += f'--{boundary}--\r\n'.encode()
	return 'multipart/form-data; boundary=' + boundary, body

def image_type(data):
	"""Return (extension, mime type) for image bytes, based on their first bytes."""
	if data[:8] == b'\x89PNG\r\n\x1a\n':
		return 'png', 'image/png'
	if data[:3] == b'\xff\xd8\xff':
		return 'jpg', 'image/jpeg'
	if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
		return 'webp', 'image/webp'
	if data[:4] == b'GIF8':
		return 'gif', 'image/gif'
	return 'png', 'image/png'
