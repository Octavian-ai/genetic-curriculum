
from google.cloud import pubsub_v1
import traceback
import pickle
import time

import logging
logger = logging.getLogger(__name__)

# Hack for single-threaded
from .google_pubsub_thread import Policy
from .specs import *

class Drone(object):
	
	def __init__(self, args, SubjectClass, init_params):
		self.args = args
		self.SubjectClass = SubjectClass
		self.init_params = init_params
		self.worker_cache = {}

		self.subscription = None
		self.publisher = pubsub_v1.PublisherClient()
		self.result_topic_path = self.publisher.topic_path(self.args.project, "pbt_result")

	def _handle_message(self, message):
		try:
			run_spec = pickle.loads(message.data)
			
			if isinstance(run_spec, RunSpec):
				if run_spec.group != self.args.group:
					message.nack()
					return
				else:
					if time.time() - run_spec.time_sent < self.args.message_timeout:
						try:
							if run_spec.id in self.worker_cache:
								worker = self.worker_cache[run_spec.id]
								worker.params = run_spec.params
							else:
								worker = self.SubjectClass(self.init_params, run_spec.params)
								worker.id = run_spec.id
								self.worker_cache[run_spec.id] = worker

							message.ack() # training takes too long and the ack will miss its window
							logger.info("{}.step_and_eval()".format(run_spec.id))
							results = worker.step_and_eval(run_spec.steps)
							result_spec = ResultSpec(self.args.group, run_spec.id, results, True, run_spec.steps, time.time())

						except Exception as e:
							traceback.print_exc()
							result_spec = ResultSpec(self.args.group, run_spec.id, None, False, run_spec.steps, time.time())

						data = pickle.dumps(result_spec)
						self.publisher.publish(self.result_topic_path, data=data)
						
						return

		except pickle.UnpicklingError as ex:
			traceback.print_exc()


		# Swallow bad messages
		# The design is for the supervisor to re-send and to re-spawn drones
		message.ack()

	def subscribe(self):
		subscriber = pubsub_v1.SubscriberClient(Policy)
		run_subscription_path = subscriber.subscription_path(self.args.project, "pbt_run_worker")
		flow_control = pubsub_v1.types.FlowControl(max_messages=1)

		logger.info("Subscribing to {}".format(run_subscription_path))

		self.subscription = subscriber.subscribe(run_subscription_path, 
			callback=lambda message: self._handle_message(message), 
			flow_control=flow_control
		)

	def block(self):
		return self.subscription.future.result()


	def run(self):
		# Hack because lib crashes
		while True:
			try:
				self.subscribe()
				self.block()
			except Exception:
				traceback.print_exc()
				sleep(5)
				pass
				

	def ensure_running(self):
		if self.subscription is None:
			self.subscribe()
		elif self.subscription.future.done():
			self.subscribe()



