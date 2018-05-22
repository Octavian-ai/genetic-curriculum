
from google.cloud import pubsub_v1
import traceback
import pickle
import time
import collections

import logging
logger = logging.getLogger(__name__)

# Hack for single-threaded
from .google_pubsub_thread import Policy
from .specs import *
from .queue import *

Perf = collections.namedtuple('Perf', ['time_start', 'time_end', 'steps'])

class Drone(object):
	
	def __init__(self, args, SubjectClass, init_params):
		self.args = args
		self.SubjectClass = SubjectClass
		self.init_params = init_params
		self.worker_cache = {}

		self.performance = []
		self.steps_per_sec = 0

		self.queue_result = GoogleQueue(self.args, ResultSpec, "pbt_result", "pbt_result_worker")
		self.queue_run = GoogleQueue(self.args, RunSpec, "pbt_run", "pbt_run_worker")


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

		self.queue_result.send(result_spec)
		logger.info("{}.send_result({})".format(worker.id, result_spec))


	def _handle_message(self, run_spec, message):

		if run_spec.id in self.worker_cache:
			worker = self.worker_cache[run_spec.id]
		else:
			worker = self.SubjectClass(self.init_params, run_spec.params)
			worker.id = run_spec.id
			self.worker_cache[run_spec.id] = worker

		worker.update_from_run_spec(run_spec)
		message.ack() # training takes too long and the ack will miss its window

		try:
			time_start = time.time()
			logger.info("{}.step_and_eval({}, {})".format(run_spec.id, run_spec.macro_step, run_spec.micro_step))
			for i in range(run_spec.macro_step):
				worker.step_and_eval(run_spec.micro_step)
				self._send_result(run_spec, worker, True)

			self.performance.append(Perf(time_start, time.time(), run_spec.micro_step * run_spec.macro_step))
			self.print_performance()
		except Exception as e:
			traceback.print_exc()
			self._send_result(run_spec, worker, False)
		
		

	def print_performance(self):
		window = 60 * 5
		cutoff = time.time() - window
		perf = [i for i in self.performance if i.time_start >= cutoff]

		if len(perf) > 0:
			start = min([i.time_start for i in perf])
			end = max([i.time_end for i in perf])

			duration = end - start
			steps = sum([i.steps for i in perf])

			self.steps_per_sec = steps / duration
			logger.info("Steps per second: {}".format(self.steps_per_sec))



	def ensure_running(self):
		self.queue_run.ensure_subscribed(lambda data, message: self._handle_message(data, message))
		



