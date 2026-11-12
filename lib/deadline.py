"""On Lambda, the function is killed when its timeout runs out. Killed means no reply to the user, a stuck state on the
message, and Lambda re-running the whole request (which pays for the images twice). So the bot works out how much time is
left and gives up on slow waits a little early, so it can still tell the user what happened."""
import time

_deadline = None

def start(context, margin=15):
	"""Called at the start of each Lambda invocation. margin is how many seconds to keep back for sending the result or an error."""
	global _deadline
	try:
		_deadline = time.time() + context.get_remaining_time_in_millis() / 1000 - margin
	except Exception:
		_deadline = None

def limit(seconds):
	"""A network timeout of at most `seconds`, shortened if the Lambda deadline is closer. Unchanged outside Lambda."""
	if _deadline is None:
		return seconds
	return max(1, min(seconds, _deadline - time.time()))
