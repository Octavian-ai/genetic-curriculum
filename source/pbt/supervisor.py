
import os.path
import time
import pickle
import math
import uuid
from google.cloud import pubsub_v1
import traceback
import random
import logging
logger = logging.getLogger(__name__)

from util import Ploty

from .specs import *
from .param import FixedParam
from util import FileWritey, FileReady

class Supervisor(object):

	def __init__(self, args, param_spec, score):
		self.args = args
		self.param_spec = param_spec
		self.score = score

		self.workers = {}
		
		self.time_last_save = time.time()
		self.time_last_print = time.time()
		self.save_epoch = 0

		self.plot_workers  = Ploty(args, title='Worker performance', x='Time', y="Score")
		self.plot_progress = Ploty(args, title='Training progress', x='Time', y="Value")
		self.plot_hyper    = Ploty(args, title='Hyper parameters', x='Time', y="Value")

		self.publisher = pubsub_v1.PublisherClient()
		self.subscription = None
		self.run_topic_path = self.publisher.topic_path(self.args.project, "pbt_run")
		
		if self.args.load:
			self.load()

	@property
	def file_path(self):
		return os.path.join(self.args.output_dir, "workers.pkl")
		

	def load(self):
		logger.info("Trying to load workers from " + self.file_path)
	
		try:
			with FileReady(self.args, "workers.pkl", True) as file:
				self.workers = pickle.load(file)
				
		except FileNotFoundError:
			self.workers = {}


		self.time_last_save = time.time()


	def save(self):
		try:
			pathlib.Path(self.file_path).mkdir(parents=True, exist_ok=True) 
		except:
			pass

		logger.info("Saving workers to " + self.file_path)

		with FileWritey(self.args, "workers.pkl", True) as file:
			pickle.dump(self.workers, file)

		self.time_last_save = time.time()

	def print(self):
		epoch = self.save_epoch

		measures = {
			"score": self.score
		}

		try:
			random_worker = random.choice(list(self.workers.values()))
			for key in random_worker.results.keys():
				measures[key] = lambda i: i.results.get(key, -1) if i.results is not None else -1
		except Exception:
			pass

		def plot_param_metrics(plot, epoch, worker, prefix="", suffix=""):
			for key, val in worker.params.items():
				if not isinstance(val, FixedParam):
					if isinstance(val.metric, int) or isinstance(val.metric, float):
						plot.add_result(epoch, val.metric, prefix+key+suffix)
					elif isinstance(val.metric, dict):
						for mkey, mval in val.metric.items():
							if isinstance(mval, int) or isinstance(mval, float):
								plot.add_result(epoch, mval, prefix+key+"_"+mkey+suffix)

		
		for i, worker in self.workers.items():

			self.plot_workers.add_result(epoch, self.score(worker),  str(i))

			for key, fn in measures.items():
				self.plot_hyper.add_result(epoch, fn(worker),  str(i)+"_"+key, "s", '--')

			plot_param_metrics(self.plot_hyper, epoch, worker, str(i)+"_")

		for key, fn in measures.items():
			vs = [fn(i) for i in self.workers.values()]

			if len(vs) > 0:
				best = max(vs)
				worst = min(vs)
				self.plot_progress.add_result(epoch, best, key+"_max")
				self.plot_progress.add_result(epoch, worst, key+"_min")

		self.plot_progress.add_result(epoch, len(self.workers), "n_workers")

		# steps_per_sec = [
		# 	i.performance[0] / i.performance[1]
		# 	for i in self.workers if i.performance[1] > 0
		# ]
		# self.plot_progress.add_result(epoch, sum(steps_per_sec), "steps_per_sec")

		best_worker = max(self.workers.values(), key=self.score)
		plot_param_metrics(self.plot_progress, epoch, best_worker, suffix="_best")

		self.plot_progress.write()
		self.plot_workers.write()
		self.plot_hyper.write()
		self.save_epoch += 1

	def consider_save(self):
		if time.time() - self.time_last_save > self.args.save_secs:
			self.save()

	def consider_print(self):
		if time.time() - self.time_last_print > self.args.print_secs:
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
		stack = sorted(stack, key=self.score)
		
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

		except ValueError:
			params = self.param_spec.realize()

		newbie = WorkerHeader(params)
		self.workers[newbie.id] = newbie
		self.dispatch(newbie)


	def remove_worker(self):
		if len(self.workers) > 0:
			stack = list(self.workers.values())
			stack.sort(key=self.score)
			del self.workers[stack[0].id]	


	def consider_exploit(self, worker):
		if worker.recent_steps >= self.args.micro_step * self.args.macro_step:

			stack = list(self.workers.values())
			stack.sort(key=self.score)
			idx = stack.index(worker)

			if idx < max(len(stack) * self.args.exploit_pct,1):
				try:
					mentor = self.get_mentor()
					logger.info("{}.mutate()".format(worker.id))
					worker.params = mentor.params.mutate(self.args.heat)
				except ValueError:
					pass

			worker.recent_steps = 0


	def dispatch(self, worker):
		"""Request drone runs this worker"""
		run_spec = RunSpec(self.args.group, worker.id, worker.params, self.args.micro_step, time.time())
		data = pickle.dumps(run_spec)
		self.publisher.publish(self.run_topic_path, data=data)
		logger.info('{}.dispatch()'.format(worker.id))
		worker.time_dispatched = time.time()

	def dispatch_idle(self):
		for i in self.workers.values():
			if time.time() - i.time_dispatched > self.args.job_timeout:
				self.dispatch(i)

	def subscribe(self):
		subscriber = pubsub_v1.SubscriberClient()
		result_subscription_path = subscriber.subscription_path(self.args.project, "pbt_result_worker")
		logger.info("Subscribing to {} {}".format(result_subscription_path, self.args.group))
		self.subscription = subscriber.subscribe(result_subscription_path, callback=lambda message:self._handle_result(message))
		return self.subscription


	def _handle_result(self, message):
		try:
			result_spec = pickle.loads(message.data)
			
			if isinstance(result_spec, ResultSpec):
				if result_spec.group != self.args.group:
					# logger.info("Message for another group")
					message.nack()
					return
				else:
					if time.time() - result_spec.time_sent < self.args.message_timeout:

						if result_spec.id in self.workers:
							i = self.workers[result_spec.id]

							if result_spec.success:
								i.record_result(result_spec)
								logger.info("{}.record_result({})".format(result_spec.id, result_spec.results))
								self.consider_exploit(i)
								self.dispatch(i)
							else:
								logger.info("{}.delete()".format(result_spec.id))
								del self.workers[result_spec.id]
								self.add_worker()

							message.ack()
							return

						else:
							logger.warning("{} worker not found for message {}".format(result_spec.id, result_spec))
					else:
						logger.warning("Message timeout")

		except pickle.UnpicklingError as ex:
			# Ok, that message wasn't for my codebase
			pass

		# Swallow bad messages
		# The design is for the supervisor to re-send and to re-spawn drones
		message.ack()


	def close(self):
		if self.subscription is not None:
			self.subscription.close()

	
	def ensure_running(self):
		if self.subscription is None:
			self.subscribe()
		elif self.subscription.future.done():
			self.subscribe()

	def run_epoch(self):
		self.scale_workers()
		self.dispatch_idle()
		self.consider_save()
		self.consider_print()





