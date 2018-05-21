
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

	def _send_result(self, run_spec, worker, success):
		result_spec = ResultSpec(
			self.args.run, 
			run_spec.id, 
			worker.results, 
			success, 
			run_spec.micro_step,
			worker.recent_steps,
			worker.total_steps, 
			time.time())
		
		data = pickle.dumps(result_spec)
		self.publisher.publish(self.result_topic_path, data=data)
		logger.info("{}.send_result({})".format(worker.id, result_spec))


	def _handle_message(self, message):

		try:
			run_spec = pickle.loads(message.data)
		except Exception:
			message.ack()
			return

		if isinstance(run_spec, RunSpec):
			if time.time() - run_spec.time_sent < self.args.message_timeout:
				if run_spec.group != self.args.run:
					message.nack()
					return
				else:
					# logger.info("Received message {}".format(run_spec))

					if run_spec.id in self.worker_cache:
						worker = self.worker_cache[run_spec.id]
					else:
						worker = self.SubjectClass(self.init_params, run_spec.params)
						worker.id = run_spec.id
						self.worker_cache[run_spec.id] = worker

					worker.update_from_run_spec(run_spec)
					message.ack() # training takes too long and the ack will miss its window

					try:
						logger.info("{}.step_and_eval({}, {})".format(run_spec.id, run_spec.macro_step, run_spec.micro_step))
						for i in range(run_spec.macro_step):
							worker.step_and_eval(run_spec.micro_step)
							self._send_result(run_spec, worker, True)

					except Exception as e:
						traceback.print_exc()
						self._send_result(run_spec, worker, False)
					
					return
			else:
				logger.debug("Timed out message")
		else:
			logger.debug("Received non RunSpec {}".format(run_spec))


		# Swallow bad messages
		# The design is for the supervisor to re-send and to re-spawn drones
		message.ack()

	def subscribe(self):
		subscriber = pubsub_v1.SubscriberClient(Policy)
		run_subscription_path = subscriber.subscription_path(self.args.project, "pbt_run_worker")
		flow_control = pubsub_v1.types.FlowControl(max_messages=1)

		logger.info("Subscribing to {} {}".format(run_subscription_path, self.args.run))

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



