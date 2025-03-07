import configparser
import os

# TO CONFIGURE, DO NOT EDIT THIS FILE. EDIT dalibot.conf IN THE PARENT DIRECTORY

config = configparser.ConfigParser()
bot_dir = os.path.realpath(os.path.dirname(__file__) + '/../')
os.chdir(bot_dir)
config.read(bot_dir + '/dalibot.ini')
config['DEFAULT'] = {
					 'archive': False,
					 'archive_dir': 'var/cache',
					 'telegramAllowedUserIDs': '',
					 'telegramBotCommand': 'dream',
					 'http_timeout': 10,
					 'ip': '127.0.0.1',
					 'port': 5000,
					 'max_upload_size': 2500000,
					 'debug': False
					}

config_archive = config.getboolean('main', 'archive')
config_archive_dir = config['main']['archive_dir'].rstrip('/')
if not config_archive_dir.startswith('/'):
	config_archive_dir = bot_dir + '/' + config_archive_dir
config_telegramAllowedUserIDs = config['main']['telegramAllowedUserIDs'].split()
config_telegramBotCommand = config['main']['telegramBotCommand'].lstrip('/')
config_telegramBotToken = config['main'].get('telegramBotToken', False)
config_telegramOutgoingToken = config['main'].get('telegramOutgoingToken', False)
config_telegramOutgoingWebhook = config['main'].get('telegramOutgoingWebhook', False)
config_http_timeout = int(config['main']['http_timeout'])
config_openai_api_key = config['main'].get('openai_api_key', False)
config_openai_organization = config['main'].get('openai_organization', False)
config_slackOAuthToken = config['main'].get('slackOAuthToken', False)
config_slackOutgoingToken = config['main'].get('slackOutgoingToken', False)
config_slackOutgoingWebhook = config['main'].get('slackOutgoingWebhook', False)
config_ip = config['main']['ip']
config_port = int(config['main']['port'])
config_max_upload_size = int(config['main']['max_upload_size'])
debug = config.getboolean('main', 'debug')

webhooks = {}
if 'slack_webhook' in config['main']:
	webhooks['slack'] = config['main']['slack_webhook'].rstrip('/')
if 'discord_webhook' in config['main']:
	webhooks['discord'] = config['main']['discord_webhook'].rstrip('/').replace('/slack', '') + '/slack'
if 'telegramBotToken' in config['main']:
	webhooks['telegram'] = 'https://api.telegram.org/bot' + config_telegramBotToken.rstrip('/') + '/'

