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
