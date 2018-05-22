
from google.cloud import pubsub_v1
import traceback
import pickle

import logging
logger = logging.getLogger(__name__)

from .google_pubsub_thread import Policy


class Queue(object):

	def __init__(self, args, clz):
		self.args = args
		self.clz = clz

	def send(self, message):
		pass

	def subscribe(self, callback):
		pass


class GoogleQueue(Queue):

	def __init__(self, args, clz, topic, subscription):
		super().__init__(args, clz)

		self.pub_topic = topic
		self.sub_name = subscription

		self.sub_client = None
		self.pub_client = None
		self.sub_sub = None

	def send(self, message):
		
		if self.pub_client is None:
			self.pub_client = pubsub_v1.PublisherClient()
			self.topic_path = self.pub_client.topic_path(self.args.project, self.pub_topic)

		data = pickle.dumps(message)
		self.pub_client.publish(self.topic_path, data=data)
		logger.info("{}.publish()".format(self.topic))

	def subscribe(self, callback):
		if self.sub_client is None:
			self.sub_client = pubsub_v1.SubscriberClient(Policy)
			self.sub_path = self.sub_client.subscription_path(self.args.project, self.sub_name)

		self.sub_sub = self.sub_client.subscribe(self.sub_path, 
			callback=lambda message: self._handle_message(message, callback), 
			flow_control=pubsub_v1.types.FlowControl(max_messages=1)
		)

		logger.info("Subscribed to {} {}".format(self.sub_path, self.args.run))

	def ensure_subscribed(self, callback):
		if self.sub_sub is None or self.sub_sub.future.done():
			self.subscribe(callback)

	def _handle_message(message, callback):
		try:
			spec = pickle.loads(message.data)
		except Exception:
			# swallow malformed
			message.ack()
			return

		if isinstance(spec, self.clz):
			if time.time() - spec.time_sent < self.args.message_timeout:
				if spec.group != self.args.run:
					# not for us!
					message.nack()
					return
				else:
					callback(spec, message)
			else:
				logger.debug("Timed out message")
		else:
			logger.debug("Received unexpected class {}".format(spec))


		# Swallow bad messages
		# The design is for the supervisor to re-send and to re-spawn drones
		message.ack()



