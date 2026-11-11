import os

# CONFIGURE VIA ENVIRONMENT VARIABLES. See dalibot.env.template

bot_dir = os.path.realpath(os.path.dirname(__file__) + '/../')
os.chdir(bot_dir)

def _str(name, default=False):
	return os.environ.get(name, '').strip() or default

def _bool(name):
	return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')

config_archive = _bool('DALIBOT_ARCHIVE')
config_archive_dir = _str('DALIBOT_ARCHIVE_DIR', 'var/cache').rstrip('/')
if not config_archive_dir.startswith('/'):
	config_archive_dir = bot_dir + '/' + config_archive_dir
config_telegramAllowedUserIDs = _str('TELEGRAM_ALLOWED_USER_IDS', '').split()
config_telegramBotCommand = _str('TELEGRAM_BOT_COMMAND', 'dream').lstrip('/')
config_telegramBotToken = _str('TELEGRAM_BOT_TOKEN')
config_telegramOutgoingToken = _str('TELEGRAM_OUTGOING_TOKEN')
config_telegramOutgoingWebhook = _str('TELEGRAM_OUTGOING_WEBHOOK')
config_http_timeout = int(_str('DALIBOT_HTTP_TIMEOUT', 10))
config_openai_api_key = _str('OPENAI_API_KEY')
config_openai_organization = _str('OPENAI_ORGANIZATION')
config_openai_image_model = _str('OPENAI_IMAGE_MODEL', 'dall-e-3')
config_slackOAuthToken = _str('SLACK_OAUTH_TOKEN')
config_slackOutgoingToken = _str('SLACK_OUTGOING_TOKEN')
config_slackOutgoingWebhook = _str('SLACK_OUTGOING_WEBHOOK')
config_ip = _str('DALIBOT_IP', '127.0.0.1')
config_port = int(_str('DALIBOT_PORT', 5000))
config_max_upload_size = int(_str('DALIBOT_MAX_UPLOAD_SIZE', 2500000))
debug = _bool('DALIBOT_DEBUG')

webhooks = {}
if _str('SLACK_WEBHOOK'):
	webhooks['slack'] = _str('SLACK_WEBHOOK').rstrip('/')
if _str('DISCORD_WEBHOOK'):
	webhooks['discord'] = _str('DISCORD_WEBHOOK').rstrip('/').replace('/slack', '') + '/slack'
if config_telegramBotToken:
	webhooks['telegram'] = 'https://api.telegram.org/bot' + config_telegramBotToken.rstrip('/') + '/'
