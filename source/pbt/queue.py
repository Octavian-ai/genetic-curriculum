
from google.cloud import pubsub_v1
import traceback
import pickle
import time

import logging
logger = logging.getLogger(__name__)

from .google_pubsub_thread import Policy
import pika

class Queue(object):

	def __init__(self, args):
		self.args = args

	def send(self, message):
		pass

	def get_messages(self, callback):
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


class RabbitQuickChannel(object):

	def __init__(self, args, queue, exchange, topic):
		self.args = args
		self.topic = topic
		self.queue = queue
		self.exchange = exchange

		parameters = pika.URLParameters(args.amqp_url)
		self.connection = pika.BlockingConnection(parameters)

		self.channel = self._open_channel()

	def _open_channel(self):
		channel = self.connection.channel()
		channel.basic_qos(prefetch_count=1)

		channel.exchange_declare(exchange=self.exchange, exchange_type='topic')
		channel.queue_declare(
			queue=self.queue, 
			durable=True,
			arguments={'x-message-ttl' : 1000*self.args.message_timeout})
		channel.queue_bind(queue=self.queue, exchange=self.exchange, routing_key=self.topic)

		return channel

	def __enter__(self):
		return self.channel

	def __exit__(self ,type, value, traceback):
		self.channel.close()
		self.connection.close()


class RabbitQueue(Queue):

	connection = None

	def __init__(self, args, queue):
		super().__init__(args)

		self.topic = args.run
		self.queue = queue + "_" + self.topic
		self.exchange = queue + "_exchange"

		self.logger = logging.getLogger(__name__ + "." + queue + "." + self.topic)


	def send(self, message):
		message = pickle.dumps(message)

		with RabbitQuickChannel(self.args, self.queue, self.exchange, self.topic) as channel:
			channel.basic_publish(
				exchange=self.exchange,
				routing_key=self.topic,
				body=message,
				properties=pika.BasicProperties(
					delivery_mode = 2, # make message persistent
				))
			self.logger.debug("Sent")

	def get_messages(self, callback):
		
		def _callback(ch, method, properties, body):
			def ack():
				ch.basic_ack(delivery_tag = method.delivery_tag)
				self.logger.debug("ACK {}".format(body))

			def nack():
				ch.basic_nack(delivery_tag = method.delivery_tag)
				self.logger.debug("NACK {}".format(body))
			
			self.logger.debug("Received")
			self._handle_message(body, callback, ack, nack)

		messages = []

		with RabbitQuickChannel(self.args, self.queue, self.exchange, self.topic) as channel:
			while True:
				method, properties, body = channel.basic_get(queue=self.queue, no_ack=True)
				if body is not None:
					messages.append(body)
				else: 
					break
				
			# if method is not None:
			# 	channel.basic_ack(delivery_tag = method.delivery_tag)

		self.logger.debug("Received {} messages".format(len(messages)))

		for i in messages:
			self._handle_message(i, callback, lambda:True, lambda:True)

			# _callback(channel, method, properties, body)
		
		# for i in gen:
		# 	logger.info("Consume loop for "+self.queue)
		# 	if i is  None:
		# 		break
		# 		# continue
		# 	else:
		
		# channel.cancel()
		# channel.close()

		# logger.info("Subscribed to {} {}".format(self.queue, self.args.run))

	def close(self):
		# self.channel.cancel()
		# self.channel.close()

		# if RabbitQueue.connection is not None:
			# RabbitQueue.connection.close()
		pass


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

	def get_messages(self, callback):
		if self.sub_client is None:
			self.sub_client = pubsub_v1.SubscriberClient(Policy)
			self.sub_path = self.sub_client.subscription_path(self.args.project, self.sub_name)

		if self.sub_sub is None or self.sub_sub.future.done():
			self.sub_sub = self.sub_client.subscribe(self.sub_path, 
				callback=lambda message: self._handle_message(message.data, callback, lambda:messack.ack(), lambda:messack.nack()), 
				flow_control=pubsub_v1.types.FlowControl(max_messages=1)
			)

		self.logger.debug("Subscribed")


	def close(self):
		if self.sub_sub is not None:
			self.sub_sub.close()

