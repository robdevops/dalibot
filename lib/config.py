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
# Numeric Telegram user ids allowed to message the bot privately (and to use /credits), or the word "all" to let
# everyone who can reach the bot do so, for when access is already limited elsewhere, such as in BotFather.
_allowed = _str('TELEGRAM_ALLOWED_USER_IDS', '').split()
config_telegramAllowAll = any(word.lower() == 'all' for word in _allowed)
config_telegramAllowedUserIDs = [word for word in _allowed if word.lower() != 'all']

def telegram_user_allowed(user_id):
	"""May this user message the bot privately?"""
	return config_telegramAllowAll or str(user_id) in config_telegramAllowedUserIDs
config_telegramBotCommand = _str('TELEGRAM_BOT_COMMAND', 'dream').lstrip('/')
config_telegramBotToken = _str('TELEGRAM_BOT_TOKEN')
config_telegramOutgoingToken = _str('TELEGRAM_OUTGOING_TOKEN')
config_telegramOutgoingWebhook = _str('TELEGRAM_OUTGOING_WEBHOOK')
config_http_timeout = int(_str('DALIBOT_HTTP_TIMEOUT', 10))
config_openrouter_api_key = _str('OPENROUTER_API_KEY')
config_openrouter_image_model = _str('OPENROUTER_IMAGE_MODEL', 'openai/gpt-image-2') # cheapest of the three

# command -> (model, description). The default command (TELEGRAM_BOT_COMMAND) uses OPENROUTER_IMAGE_MODEL.
image_models = {
	'gpt': ('openai/gpt-image-2', 'GPT Image 2 (cheapest)'),
	'flux': ('black-forest-labs/flux-3-image-klein', 'FLUX.3 Klein (fastest)'),
	'qwen': ('qwen/qwen-image-2.1-turbo', 'Qwen Image 2.1 Turbo'),
}
image_models[config_telegramBotCommand] = (config_openrouter_image_model, 'the default model')
# other names for the default command; a name that is already a command of its own is not an alias
COMMAND_ALIASES = {alias: config_telegramBotCommand for alias in ('imagine',) if alias not in image_models}
CREDITS_COMMANDS = ('credits', 'tokens', 'usage', 'cost') # show what the bot has spent on OpenRouter
config_openrouter_text_model = _str('OPENROUTER_TEXT_MODEL', 'meta-llama/llama-3.1-8b-instruct') # cheap model that rewrites prompts for styles
MIN_PROMPT_WORDS = 3 # shorter typed prompts are ignored; shorter prompts on a button press are expanded by the text model
config_image_timeout = int(_str('DALIBOT_IMAGE_TIMEOUT', 120))

# Where we remember each image message's prompt and the images made for it (as Telegram file_ids), so the
# buttons can switch between them. sqlite for self-hosted, dynamodb on Lambda. See lib/store.py.
config_store = _str('DALIBOT_STORE', 'dynamodb' if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') else 'sqlite').lower()
config_store_days = int(_str('DALIBOT_STORE_DAYS', 90)) # forget messages after this long
config_store_db = _str('DALIBOT_DB', 'var/dalibot.db')
if not config_store_db.startswith('/'):
	config_store_db = bot_dir + '/' + config_store_db
config_store_table = _str('DALIBOT_TABLE', 'dalibot')
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
