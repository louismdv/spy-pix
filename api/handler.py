import base64
import requests
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import os
import redis
import sys

PIXEL = base64.b64decode(
	"R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

# Ntfy topic from environment
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
# Redis connection from environment
REDIS_URL = os.environ.get("REDIS_URL", "")

ACTIVATION_DELAY_MINUTES = 0.5

# Initialize Redis client
redis_client = None
if REDIS_URL:
	try:
		redis_client = redis.from_url(REDIS_URL, decode_responses=True)
		print(f"[INFO] Redis connected successfully", file=sys.stderr)
	except Exception as e:
		print(f"[ERROR] Redis connection failed: {str(e)}", file=sys.stderr)
		redis_client = None
else:
	print(f"[WARNING] No REDIS_URL found in environment", file=sys.stderr)

def get_email_key_data(email_key):
	"""Get email open data from Redis."""
	if not redis_client:
		print(f"[DEBUG] Redis not connected, returning None for {email_key}", file=sys.stderr)
		return None

	try:
		data = redis_client.get(email_key)
		result = json.loads(data) if data else None
		print(f"[DEBUG] Redis GET {email_key}: {result}", file=sys.stderr)
		return result
	except Exception as e:
		print(f"[Non existent key] Redis GET failed for {email_key}: {str(e)}", file=sys.stderr)
		return None

def save_email_key_data(email_key, data):
	"""Save email open data to Redis."""
	if not redis_client:
		print(f"[DEBUG] Redis not connected, skipping save for {email_key}", file=sys.stderr)
		return False

	try:
		redis_client.set(email_key, json.dumps(data))
		print(f"[DEBUG] Redis SET {email_key}: {data}", file=sys.stderr)
		return True
	except Exception as e:
		print(f"[ERROR] Redis SET failed for {email_key}: {str(e)}", file=sys.stderr)
		return False

class handler(BaseHTTPRequestHandler):
	def do_GET(self):
		parsed_url = urlparse(self.path)
		params = parse_qs(parsed_url.query)
		email_recipient = params.get("recipient", ["unknown"])[0]
		email_title = params.get("title", ["unknown"])[0]

		# Get IP from Vercel's forwarded header
		ip = self.headers.get("x-forwarded-for", "unknown")
		if "," in ip:  # Handle multiple IPs in x-forwarded-for
			ip = ip.split(",")[0].strip()
		
		now = datetime.now(timezone.utc)
		timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")
		
		print(f"[INFO] Request from {ip}: recipient={email_recipient}, title={email_title}", file=sys.stderr)
		print(f"[DEBUG] NTFY_TOPIC={NTFY_TOPIC}, Redis connected={redis_client is not None}", file=sys.stderr)

		if email_recipient == "unknown" or email_title == "unknown":
			print("[DEBUG] Request filtered: missing recipient or title parameters", file=sys.stderr)
		
		elif email_recipient != "unknown" and email_title != "unknown":
			print(f"[INFO] Valid request, processing email open", file=sys.stderr)
			email_key = f"email:{email_recipient}:{email_title}"

			# Get existing opens data from KV
			email_key_data = get_email_key_data(email_key)
			is_zero_open = email_key_data is None

			# Tracker activated notification (first time seeing this email)
			if is_zero_open:
				# First time seeing this email - set activation time
				activation_time = now + timedelta(minutes=ACTIVATION_DELAY_MINUTES)
				data = {
					"first_open": timestamp,
					"count": 0,
					"activation_time": activation_time.isoformat()
				}
				save_email_key_data(email_key, data)
				print(f"[INFO] Zero open recorded. Activation time set to {activation_time.isoformat()}", file=sys.stderr)
				
				# Send activation notification
				self._send_notification(
					email_recipient=email_recipient,
					email_title=email_title,
					timestamp=timestamp,
					ip=ip,
					count=0,
					notification_type="Tracker Activated",
					tag="sparkle"
				)
			
			else:
				# Check if we're past activation time
				activation_time = datetime.fromisoformat(email_key_data["activation_time"])
				
				# If not activated yet, ignore this open
				if now < activation_time:
					time_remaining = (activation_time - now).total_seconds()
					print(f"[INFO] Not activated yet. {time_remaining:.0f} seconds remaining", file=sys.stderr)
				if email_key_data["count"]>3:
					print(f"[INFO] Open count {email_key_data['count']} exceeds threshold, skipping notification", file=sys.stderr)
				# If past activation time - increment counter and notify
				else:
					email_key_data["count"] += 1
					save_email_key_data(email_key, email_key_data)

					if email_key_data['count'] == 1:
						notification_type = "First Open"
						tag = "open_file_folder"
					else:
						notification_type = "Reopened"
						tag = "arrows_counterclockwise"
					
					self._send_notification(
						email_recipient=email_recipient,
						email_title=email_title,
						timestamp=timestamp,
						ip=ip,
						count=email_key_data['count'],
						notification_type=notification_type,
						tag=tag
					)

		self._return_pixel()
	
	def _send_notification(self, email_recipient, email_title, timestamp, ip, count, notification_type, tag):
		"""Send notification to ntfy.sh"""
		try:
			if not NTFY_TOPIC:
				print("[WARNING] NTFY_TOPIC not set, skipping notification", file=sys.stderr)
				return
			
			headers = {
				"Title": f"{email_title}: {notification_type}",
				"Content-Type": "text/plain; charset=utf-8",
				"Tags": tag
			}
			message = f"Recipient: {email_recipient}\nTime: {timestamp}\nIP: {ip}\nTotal Opens: {count}"
			
			response = requests.post(
				f"https://ntfy.sh/{NTFY_TOPIC}",
				data=message.encode('utf-8'),
				headers=headers,
				timeout=3
			)
			
			if response.status_code != 200:
				print(f"[ERROR] Notification failed with status {response.status_code}: {response.text}", file=sys.stderr)
			else:
				print(f"[SUCCESS] Notification sent: {notification_type}", file=sys.stderr)
		except Exception as e:
			print(f"[ERROR] Failed to send notification: {str(e)}", file=sys.stderr)

	def _return_pixel(self):
		"""Helper to return the tracking pixel"""
		self.send_response(200)
		self.send_header("Content-Type", "image/gif")
		self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
		self.send_header("Content-Length", str(len(PIXEL)))
		self.end_headers()
		self.wfile.write(PIXEL)