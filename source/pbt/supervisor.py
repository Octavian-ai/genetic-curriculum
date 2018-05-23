
import os.path
import time
import pickle
import math
import uuid
from google.cloud import pubsub_v1
import traceback
import random
import yaml
import logging
logger = logging.getLogger(__name__)

from util import Ploty

from .specs import *
from .param import FixedParam
from .queue import QueueFactory
from util import FileWritey, FileReady

class Supervisor(object):

	def __init__(self, args, param_spec, score, reverse=False):
		self.args = args
		self.param_spec = param_spec
		self.score = score
		self.reverse = reverse

		self.workers = {}
		
		self.time_last_save = time.time()
		self.time_last_print = time.time()
		self.print_dirty = False
		self.save_epoch = 0

		self.plot_progress = Ploty(args, title='Training progress', x='Time', y="Value")
		self.plot_measures = {}
		self.measures = {
			"score": self.score
		}

		self.queue_result = QueueFactory.vend(self.args, "pbt_result")
		self.queue_run = QueueFactory.vend(self.args, "pbt_run")
		
		if self.args.load:
			self.load()

	@property
	def file_path(self):
		return os.path.join(self.args.output_dir, self.args.run, "workers.pkl")
		
	def load(self):
		logger.info("Trying to load workers from " + self.file_path)
	
		try:
			with FileReady(self.args, "workers.pkl", True) as file:
				self.workers = pickle.load(file)
				logger.info("Loaded {} workers".format(len(self.workers)))
				
		except Exception:
			self.workers = {}

		self.time_last_save = time.time()


	def save(self):

		logger.info("Saving workers to " + self.file_path)

		with FileWritey(self.args, "workers.pkl", True) as file:
			pickle.dump(self.workers, file)

		with FileWritey(self.args, "workers.yaml", False) as file:
			yaml.dump(self.workers, file)
			
		self.time_last_save = time.time()

	def print(self):
		epoch = self.save_epoch

		# Closure so we capture result_key
		def add_measure(result_key):
			def get_metric(worker):
				try:
					return worker.results[result_key]
				except Exception:
					return -1

			self.measures[result_key] = get_metric
	
		random_worker = random.choice(list(self.workers.values()))
		if random_worker.results is not None:
			for result_key in random_worker.results.keys():
				if result_key not in self.measures:
					add_measure(result_key)
					
	
		for key in self.measures.keys():
			if key not in self.plot_measures:
				self.plot_measures[key] = Ploty(self.args, title="Metric "+key, x='Time', y=key)

		def plot_param_metrics(plot, epoch, worker, prefix="", suffix=""):
			for key, val in worker.params.items():
				if not isinstance(val, FixedParam):
					if isinstance(val.metric, int) or isinstance(val.metric, float):
						plot.add_result(epoch, val.metric, prefix+key+suffix)
					elif isinstance(val.metric, dict):
						for mkey, mval in val.metric.items():
							if isinstance(mval, int) or isinstance(mval, float):
								plot.add_result(epoch, mval, prefix+key+"_"+mkey+suffix)


		stack = list(self.workers.values())
		stack.sort(key=self.score,reverse=self.reverse)
		
		for idx, worker in enumerate(stack):
			for key, value in self.plot_measures.items():
				logger.info("value add_result {}, {}, {}, {}, {}".format(value, key, self.measures[key](worker), str(idx), worker.results))
				value.add_result(epoch, self.measures[key](worker), str(idx))

		for key, fn in self.measures.items():
			vs = [fn(i) for i in self.workers.values()]

			if len(vs) > 0:
				best = max(vs)
				worst = min(vs)
				self.plot_progress.add_result(epoch, best, key+"_max")
				self.plot_progress.add_result(epoch, worst, key+"_min")

		self.plot_progress.add_result(epoch, len(self.workers), "n_workers")

		best_worker = stack[-1]
		plot_param_metrics(self.plot_progress, epoch, best_worker, suffix="_best")

		self.plot_progress.write()
		for value in self.plot_measures.values():
			value.write()

		self.save_epoch += 1
		self.print_dirty = False

	def consider_save(self):
		if time.time() - self.time_last_save > self.args.save_secs:
			self.save()

	def consider_print(self):
		if time.time() - self.time_last_print > self.args.print_secs and self.print_dirty:
			self.print()


	def scale_workers(self):
		delta = self.args.n_workers - len(self.workers)

		if delta > 0:
			for i in range(delta):
				self.add_worker()
		elif delta < 0:
			for i in range(-delta):
				self.remove_worker()

	def get_mentor(self):
		stack = list(self.workers.values())
		random.shuffle(stack) # Tie-break randomly
		stack = sorted(stack, key=self.score, reverse=self.reverse)
		
		n20 = max(round(len(self.workers) * self.args.exploit_pct), 1)
		top20 = stack[-n20:]
		top20 = [i for i in top20 if i.results is not None]

		if len(top20) > 0:
			return random.choice(top20)

		raise ValueError("No top workers have results yet")
			


	def add_worker(self):
		try:
			mentor = self.get_mentor()
			params = mentor.params.mutate(self.args.heat)
			logger.info("New worker from {}.mutate()".format(mentor.id))
			results = mentor.results

		except ValueError:
			logger.info("New worker from param spec realize")
			params = self.param_spec.realize()
			results = None

		newbie = WorkerHeader(params)
		newbie.results = results
		self.workers[newbie.id] = newbie
		self.dispatch(newbie)


	def remove_worker(self):
		if len(self.workers) > 0:
			stack = list(self.workers.values())
			stack.sort(key=self.score, reverse=self.reverse)
			del self.workers[stack[0].id]	


	def consider_exploit(self, worker):
		if worker.recent_steps >= self.args.micro_step * self.args.macro_step:

			stack = list(self.workers.values())
			stack.sort(key=self.score, reverse=self.reverse)
			idx = stack.index(worker)

			if len(stack) > 1 and idx < max(len(stack) * self.args.exploit_pct,1):
				del self.workers[worker.id]
				logger.info("del {}".format(worker.id))
				self.add_worker()
			else:
				self.dispatch(worker)
			

			worker.recent_steps = 0


	def dispatch(self, worker):
		"""Request drone runs this worker"""
		run_spec = worker.gen_run_spec(self.args)
		self.queue_run.send(run_spec)
		logger.info('{}.dispatch()'.format(worker.id))
		worker.time_last_updated = time.time()

	def dispatch_idle(self):
		for i in self.workers.values():
			if time.time() - i.time_last_updated > self.args.job_timeout:
				self.dispatch(i)


	def _handle_result(self, result_spec, ack, nack):		
		if result_spec.id in self.workers:
			i = self.workers[result_spec.id]

			if result_spec.total_steps >= i.total_steps:
				self.print_dirty = True

				if result_spec.success:
					i.update_from_result_spec(result_spec)
					logger.info("{}.record_result({})".format(result_spec.id, result_spec))
					self.consider_exploit(i)
				else:
					logger.info("del {}".format(result_spec.id))
					del self.workers[result_spec.id]
					self.add_worker()
			else:
				logger.warning("{} received results for < current total_steps".format(result_spec.id))
		else:
			logger.debug("{} worker not found for message {}".format(result_spec.id, result_spec))

		# Swallow bad messages
		# The design is for the supervisor to re-send and to re-spawn drones
		ack()


	def close(self):
		self.queue_result.close()
		self.queue_run.close()
	
	def subscribe(self):
		self.queue_result.subscribe(lambda spec, ack, nack: self._handle_result(spec, ack, nack))

	def run_epoch(self):
		self.scale_workers()
		self.dispatch_idle()
		self.consider_save()
		self.consider_print()
		self.subscribe()





