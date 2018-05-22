
from google.cloud import pubsub_v1
import traceback
import pickle

import logging
logger = logging.getLogger(__name__)

from .google_pubsub_thread import Policy
import pika

class Queue(object):

	def __init__(self, args):
		self.args = args

	def send(self, message):
		pass

	def subscribe(self, callback):
		"""
			callback: (spec, ack, nack) -> None
			It's expected that callback will ack/nack the message
		"""
		pass

	def _handle_message(self, data, callback, ack, nack):
		try:
			spec = pickle.loads(data)
		except Exception:
			logger.debug("Could not unpickle message")
			ack()
			return

		if time.time() - spec.time_sent < self.args.message_timeout:
			if spec.group != self.args.run:
				logger.debug("Message for other group {}".format(spec.group))
				nack()
			else:
				callback(spec, ack, nack)
		else:
			logger.debug("Timed out message")
			ack()

	def ensure_subscribed(self, callback):
		pass

	def close(self, callback):
		pass

class QueueFactory(object):

	@classmethod
	def vend(clz, args, *argv):
		if args.queue_type == "google":
			return GoogleQueue(args, *argv)
		elif args.queue_type == "rabbitmq":
			return RabbitQueue(args, *argv)
		else:
			raise ValueError(args.queue_type)


class RabbitQueue(Queue):

	connection = None

	def __init__(self, args, queue):
		super().__init__(args)

		if RabbitQueue.connection is None:
			parameters = pika.URLParameters(args.amqp_url)
			RabbitQueue.connection = pika.BlockingConnection(parameters)

		self.queue = queue
		self.channel = RabbitQueue.connection.channel()
		self.channel.queue_declare(queue=self.queue, durable=True)

	def send(self, message):
		message = pickle.dumps(message)
		self.channel.basic_publish(
			exchange='',
			routing_key=self.queue,
			body=message,
			properties=pika.BasicProperties(
				delivery_mode = 2, # make message persistent
			))
		logger.info("Sent to {} {}".format(self.queue, self.args.run))

	def subscribe(self, callback):
		def _callback(ch, method, properties, body):
			ack = lambda: ch.basic_ack(delivery_tag = method.delivery_tag)
			nack = lambda: ch.basic_nack(delivery_tag = method.delivery_tag)
			self._handle_message(body, callback, ack, nack)
			logger.info("Received on {} {}".format(self.queue, self.args.run))

		self.channel.basic_qos(prefetch_count=1)
		self.channel.basic_consume(_callback, queue=self.queue)
		self.channel.start_consuming()
		# logger.info("Subscribed to {} {}".format(self.queue, self.args.run))

	def close(self):
		if RabbitQueue.connection is not None:
			RabbitQueue.connection.close()


class GoogleQueue(Queue):

	def __init__(self, args, topic):
		super().__init__(args)

		self.pub_topic = topic
		self.sub_name = topic+"_worker"

		self.sub_client = None
		self.pub_client = None
		self.sub_sub = None

	def send(self, message):
		if self.pub_client is None:
			self.pub_client = pubsub_v1.PublisherClient()
			self.topic_path = self.pub_client.topic_path(self.args.project, self.pub_topic)

		data = pickle.dumps(message)
		self.pub_client.publish(self.topic_path, data=data)

	def subscribe(self, callback):
		if self.sub_client is None:
			self.sub_client = pubsub_v1.SubscriberClient(Policy)
			self.sub_path = self.sub_client.subscription_path(self.args.project, self.sub_name)

		if self.sub_sub is None or self.sub_sub.future.done():
			self.sub_sub = self.sub_client.subscribe(self.sub_path, 
				callback=lambda message: self._handle_message(message.data, callback, lambda:messack.ack(), lambda:messack.nack()), 
				flow_control=pubsub_v1.types.FlowControl(max_messages=1)
			)

		# logger.info("Subscribed to {} {}".format(self.sub_path, self.args.run))


	def close(self):
		if self.sub_sub is not None:
			self.sub_sub.close()

