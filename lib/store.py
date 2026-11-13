"""Remembers, for each image message the bot posted, its prompt and the images made for it.

The images themselves stay in Telegram: we keep only each image's file_id, so switching back to an
earlier image is a single edit with no upload. A record looks like:

    {'prompt': 'a red fox in snow', 'command': 'flux', 'current': 'monet',
     'images': {'_': {'file_id': ..., 'caption': ..., 'base': ...}, 'monet': {...}}}

'_' is the image with no style. 'base' is the prompt after any expansion and cleanup, before the style
phrase is added, so Remix can reuse it and skip the text model.

Each photo of a variations album (made from a photo the user sent) gets its own record too, so a gallery can find them:
'kind' is 'variation', 'prompt' is what the user wrote with their photo (may be empty), and the one image is under '_'
with that photo's caption (its style and viewpoint). Albums have no buttons, so the bot itself never reads these back.
Backends: SQLite (self-hosted, standard library only) and DynamoDB (Lambda).
Storage problems are logged and never stop the bot from generating images.
"""
import json
import os
import sqlite3
import time
from sys import stderr

from lib.config import *

BASE = '_' # key for the unstyled image (DynamoDB does not allow empty attribute names)

def key(style):
	return style or BASE

class SqliteStore:
	def __init__(self, path, days):
		self.path = path
		self.days = days
		os.makedirs(os.path.dirname(path), exist_ok=True)
		if not os.path.exists(path):
			os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)) # prompts live here: owner only
		db = self._connect()
		try:
			db.execute('CREATE TABLE IF NOT EXISTS messages (chat_id TEXT, message_id TEXT, data TEXT, updated INTEGER, PRIMARY KEY (chat_id, message_id))')
			db.execute('DELETE FROM messages WHERE updated < ?', (int(time.time()) - days * 86400,))
		finally:
			db.close()

	def _connect(self):
		return sqlite3.connect(self.path, timeout=10, isolation_level=None) # we manage transactions ourselves

	def get(self, chat_id, message_id):
		db = self._connect()
		try:
			row = db.execute('SELECT data FROM messages WHERE chat_id=? AND message_id=?', (str(chat_id), str(message_id))).fetchone()
		finally:
			db.close()
		return json.loads(row[0]) if row else None

	def _modify(self, chat_id, message_id, change):
		"""Read, change and write one record atomically, creating it if it does not exist."""
		db = self._connect()
		try:
			db.execute('BEGIN IMMEDIATE')
			row = db.execute('SELECT data FROM messages WHERE chat_id=? AND message_id=?', (str(chat_id), str(message_id))).fetchone()
			record = json.loads(row[0]) if row else None
			record = change(record)
			db.execute('INSERT OR REPLACE INTO messages VALUES (?, ?, ?, ?)', (str(chat_id), str(message_id), json.dumps(record), int(time.time())))
			db.execute('COMMIT')
		except BaseException:
			db.execute('ROLLBACK') if db.in_transaction else None
			raise
		finally:
			db.close()

	def save_image(self, chat_id, message_id, prompt, command, style, file_id, caption, base=None, kind=None):
		def change(record):
			record = record or dict({'prompt': prompt, 'command': command, 'images': {}}, **({'kind': kind} if kind else {}))
			record['images'][key(style)] = {'file_id': file_id, 'caption': caption, 'base': base}
			record['current'] = key(style)
			return record
		self._modify(chat_id, message_id, change)

	def set_current(self, chat_id, message_id, style):
		def change(record):
			if record is None:
				raise KeyError('no such message')
			record['current'] = key(style)
			return record
		self._modify(chat_id, message_id, change)

	def put(self, chat_id, message_id, record):
		self._modify(chat_id, message_id, lambda _: record)

	def describe(self):
		db = self._connect()
		try:
			count = db.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
		finally:
			db.close()
		return f'SQLite at {self.path}, {count} saved image messages'

class DynamoStore:
	def __init__(self, table, days):
		import boto3 # included in the Lambda Python runtime
		self.table = boto3.resource('dynamodb').Table(table)
		self.days = days

	def _id(self, chat_id, message_id):
		return f'{chat_id}:{message_id}'

	def get(self, chat_id, message_id):
		item = self.table.get_item(Key={'id': self._id(chat_id, message_id)}).get('Item')
		if not item:
			return None
		return {'prompt': item['prompt'], 'command': item['command'], 'current': item['current'], 'images': item['images']}

	def save_image(self, chat_id, message_id, prompt, command, style, file_id, caption, base=None, kind=None):
		from botocore.exceptions import ClientError
		id = self._id(chat_id, message_id)
		expires = int(time.time()) + self.days * 86400 # DynamoDB TTL deletes the item after this
		item = {'id': id, 'prompt': prompt, 'command': command, 'current': key(style), 'images': {}, 'ttl': expires}
		if kind:
			item['kind'] = kind
		try: # create the record the first time we see this message
			self.table.put_item(Item=item, ConditionExpression='attribute_not_exists(id)')
		except ClientError as e:
			if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
				raise
		self.table.update_item(Key={'id': id},
			UpdateExpression='SET images.#k = :image, #cur = :k, #ttl = :ttl',
			ExpressionAttributeNames={'#k': key(style), '#cur': 'current', '#ttl': 'ttl'},
			ExpressionAttributeValues={':image': {'file_id': file_id, 'caption': caption, 'base': base}, ':k': key(style), ':ttl': expires})

	def put(self, chat_id, message_id, record):
		self.table.put_item(Item={'id': self._id(chat_id, message_id), 'prompt': record['prompt'], 'command': record['command'],
			'current': record['current'], 'images': record['images'], 'ttl': int(time.time()) + self.days * 86400})

	def describe(self):
		self.get('check', 'check') # a read, which fails if the table, region or permissions are wrong
		return f"DynamoDB table '{self.table.name}' in {self.table.meta.client.meta.region_name} (reads work)"

	def set_current(self, chat_id, message_id, style):
		self.table.update_item(Key={'id': self._id(chat_id, message_id)},
			UpdateExpression='SET #cur = :k', ConditionExpression='attribute_exists(id)',
			ExpressionAttributeNames={'#cur': 'current'}, ExpressionAttributeValues={':k': key(style)})

_backend = None

def backend():
	global _backend
	if _backend is None:
		if config_store == 'dynamodb':
			_backend = DynamoStore(config_store_table, config_store_days)
		elif config_store == 'sqlite':
			_backend = SqliteStore(config_store_db, config_store_days)
		else:
			raise ValueError(f'DALIBOT_STORE must be sqlite or dynamodb, not {config_store!r}')
	return _backend

def check():
	"""Say at start-up whether the image history works, so a missing table, wrong region or unreadable file
	shows in the logs straight away instead of as buttons that quietly regenerate."""
	try:
		print('Image history:', backend().describe(), file=stderr)
	except Exception as e:
		print(f'Image history is NOT working ({config_store}): {e!r}. The style buttons will regenerate images instead of switching between saved ones.', file=stderr)

def _safely(operation, default, *args):
	try:
		return getattr(backend(), operation)(*args)
	except Exception as e:
		print(f'Store {operation} failed (continuing without history):', repr(e), file=stderr)
		return default

def get(chat_id, message_id):
	return _safely('get', None, chat_id, message_id)

def save_image(chat_id, message_id, prompt, command, style, file_id, caption, base=None, kind=None):
	return _safely('save_image', None, chat_id, message_id, prompt, command, style, file_id, caption, base, kind)

def save_variations(chat_id, prompt, command, sent, captions):
	"""Remember each photo of a variations album: sent is what sendMediaGroup returned, captions the caption of each photo."""
	for photo, caption in zip(sent or [], captions):
		if photo.get('message_id') and photo.get('file_id'):
			save_image(chat_id, photo['message_id'], prompt, command, None, photo['file_id'], caption, kind='variation')

def set_current(chat_id, message_id, style):
	return _safely('set_current', None, chat_id, message_id, style)

def carry_over(chat_id, old_message_id, new_message_id, current=None):
	"""Copy a message's saved images to another message, for when the old one can't be edited and a new one is posted.
	current is the style the new message shows (the old record's current style if not given). Returns True if copied."""
	record = get(chat_id, old_message_id)
	if not record:
		return False
	if current is not None:
		record['current'] = key(current)
	return _safely('put', False, chat_id, new_message_id, record) is not False
