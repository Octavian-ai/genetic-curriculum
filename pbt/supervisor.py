

import numpy as np
import random
import pickle
import pathlib
import traceback
from glob import glob
import uuid
import os
import os.path
import collections
import sys
import math
import time
from time import sleep
import signal


from google.cloud import pubsub_v1

from .param import FixedParam, FP
from .specs import *

from util import Ploty

import logging
logger = logging.getLogger(__name__)


class Supervisor(object):
	"""
		Implementation of Population Based Training. 
		Supervisor manages and optimises the experiments


		# Notes on 'PBT theory'

		Ways to create a new worker:
		 - Fresh worker (random initialisation)
		 - Mutate from top performer (asexual reproduction)
		 - Breed partners (sexual reproduction)

		Reproduction introduces random mutations into properties
		If mutation perturbation samples from a long tailed distribution, 
		then there is a chance of black swan discoveries. This is important.
		This makes reproduction and fresh worker spawning statistically 
		equivalent at the limit.

		Events to trigger creating new worker:
		 - Fewer workers in pool than desired size

		Events to trigger culling a worker:
		 - Crashes
		 - More workers in pool than desired size
		 - Worker poor performer after macro cycle



	"""
	def __init__(self, 
				 args,
				 SubjectClass, 
				 init_params,
				 hyperparam_spec, 
				 score,
				 n_workers=10, 
				 save_freq=20,
				 heat=1.0
				 ):

		self.args = args
		self.SubjectClass = SubjectClass
		self.init_params = init_params
		self.hyperparam_spec = hyperparam_spec
		self.score = score
		self.heat = heat
		self.save_freq = save_freq
		self.save_counter = save_freq


		assert "micro_step" in hyperparam_spec, "Hyperparameters must include micro_step"
		assert "macro_step" in hyperparam_spec, "Hyperparameters must include macro_step"


		# Function or Integer supported
		if isinstance(n_workers, int) or isinstance(n_workers, float):
			self.n_workers = lambda step: round(n_workers)
		else:
			self.n_workers = n_workers

		self.fail_count = 0
		self.workers = []
		self.plot_workers  = Ploty(args, title='Worker performance', x='Time', y="Score")
		self.plot_progress = Ploty(args, title='Training progress', x='Time', y="Value")
		self.plot_hyper    = Ploty(args, title='Hyper parameters', x='Time', y="Value")

		self.publisher = pubsub_v1.PublisherClient()
		self.run_topic_path = self.publisher.topic_path(self.args.project, "pbt_run")
		self.result_topic_path = self.publisher.topic_path(self.args.project, "pbt_result")


	def save(self):
		p = os.path.join(self.args.output_dir, "population")

		try:
			pathlib.Path(p).mkdir(parents=True, exist_ok=True) 
		except:
			pass

		existing_pop = os.path.join(self.args.output_dir, "population/worker_*.pkl")
		for i in glob(existing_pop):
			os.unlink(i)

		for worker in self.workers:
			worker.save(os.path.join(p, "worker_{}.pkl".format(worker.id)))

		logger.info("Saved workers")

	def load(self, input_dir=None):
		if input_dir is None:
			input_dir = self.args.output_dir

		pop_dir = os.path.join(input_dir, "population/worker_*.pkl")
		logger.info("Trying to load workers from " + pop_dir)

		self.workers = []
		for i in glob(pop_dir):
			try:
				w = self.SubjectClass.load(i, self.init_params)
				self.workers.append(w)
				logger.info("Loaded {}".format(w.id))

			except Exception as e:
				print(e)


	def scale_workers(self, epoch):

		delta = self.n_workers(epoch) - len(self.workers)

		if delta != 0:
			logger.info("Resizing worker pool by {}".format(delta))

		if delta < 0:
			stack = list(self.workers)
			random.shuffle(stack) # Tie-break randomly
			stack = sorted(stack, key=self.score)
			
			n20 = round(len(self.workers)*0.2)
			bottom20 = stack[:n20]

			readies = [i for i in bottom20 if i.is_ready()]
			sort(readies, key=self.score)
			for i in readies[:min(-delta, len(readies))]:
				self.workers.remove(i)

		elif delta > 0:	
			for i in range(delta):
				self.add_random_worker()

	def add_random_worker(self):
		additional = self.SubjectClass(self.init_params, self.hyperparam_spec)
		self.workers.append(additional)

	def breed_worker(self, worker):

		score = self.score(worker)
		stack = sorted(stack, key=lambda i: abs(score-self.score(i)))
		partner = random.choice(stack[:5])

		ap = worker.params
		bp = partner.params

		params = {
			k: v.breed(ap[k], bp[k], self.heat) for k, v in self.hyperparam_spec.items()
		}

		child = self.SubjectClass(self.init_params, self.hyperparam_spec)
		child.params = params
		self.workers.append(child)
		return child

	



	# TODO: Make params into a virtual dictionary (and wrap .value for the caller)
	def params_equal(self, p1, p2):
		for k, v in p1.items():
			if v != p2[k]:
				return False
		return True

	def __len__(self):
		return len(self.workers)

	@property
	def best_worker(self):
		return max(self.workers, key=self.score)
	

	def _remove_worker(self, worker, epoch):
		self.workers.remove(worker)
		self.fail_count += 1
		self.plot_progress.add_result(epoch, self.fail_count, "failed_workers")


	def single_step(self, worker):
		steps = worker.params.get("micro_step", FP(1)).value
		logger.info("{}.train({})".format(worker.id, steps))
		worker.step(steps)
		logger.info("{}.eval()".format(worker.id))
		return worker.eval()

	def step_singlethreaded(self, epoch):
		for i in self.workers:
			try:
				self.single_step(i)
				
			except Exception:
				traceback.print_exc()
				self._remove_worker(i, epoch)
				continue

		if len(self.workers) == 0:
			raise Exception("All workers failed, your model has bugs")



	def step_distributed(self, epoch):

		# --------------------------------------------------------------------------
		# Run parallel trainings
		# --------------------------------------------------------------------------

		not_running = [
			i for i in self.workers 
			if time.time() - i.time_started > self.args.job_timeout
		]
		
		for i in not_running:
			i.record_start()
			run_spec = RunSpec(i.id, i.params)
			data = pickle.dumps(run_spec)
			self.publisher.publish(self.run_topic_path, data=data)
			print('Sent run message: {}'.format(run_spec))

		sleep(40)



	def step(self, epoch):
		self.step_distributed(epoch)

	def exploit(self, epoch):
		if len(self.workers) > 0:
			stack = list(self.workers)
			random.shuffle(stack) # Tie-break randomly
			stack = sorted(stack, key=self.score)
			
			n20 = max(math.ceil(len(stack)*0.2), 1)
			top20 = stack[-n20:]
			bottom20 = stack[:n20]

			for i in bottom20:
				if i.is_ready() and (time.time() - i.time_started > self.args.job_timeout):
					mentor = random.choice(top20)
					logger.info("{} replace with mutated {}".format(i.id, mentor.id))
					i.params = mentor.explore(self.heat)
					logger.info("reset count")
					i.reset_count()
					logger.info("reset count done")




	def breed(self, epoch):
		for i in self.workers:
			if i.is_ready():

				newbie = self.breed_worker(i)

				try:
					# Warning: executing this in the main thread will break
					# because Tensorflow is not thread safe.
					newbie.eval()

				except Exception:
					traceback.print_exc()
					self._remove_worker(newbie, epoch)
					continue


	def print_status(self, epoch):

		measures = {
			"score": self.score
		}

		if len(self.workers) > 0 and self.workers[0].results is not None:
			for key in self.workers[0].results.keys():
				measures[key] = lambda i: i.results.get(key, -1)
		
		for i, worker in enumerate(self.workers):

			self.plot_workers.add_result(epoch, self.score(worker),  str(i)+"_score")

			for key, fn in measures.items():
				self.plot_hyper.add_result(epoch, fn(worker),  str(i)+"_"+key, "s", '--')

			for key, val in worker.params.items():
				if not isinstance(val, FixedParam):
					if isinstance(val.metric, int) or isinstance(val.metric, float):
						self.plot_hyper.add_result(epoch, val.metric, str(i)+"_"+key)

		for key, fn in measures.items():
			vs = [fn(i) for i in self.workers]

			if len(vs) > 0:
				best = max(vs)
				worst = min(vs)
				self.plot_progress.add_result(epoch, best, key+"_max")
				self.plot_progress.add_result(epoch, worst, key+"_min")

		self.plot_progress.add_result(epoch, len(self.workers), "n_workers")

		steps = sum([i.performance[0] for i in self.workers])
		time = sum([i.performance[1] for i in self.workers])

		steps_per_min = steps / time * 60 if time > 0 else 0
		self.plot_progress.add_result(epoch, steps_per_min, "steps_per_min")

		best_worker = max(self.workers, key=self.score)

		for key, val in best_worker.params.items():
			if not isinstance(val, FixedParam):
				if isinstance(val.metric, int) or isinstance(val.metric, float):
					self.plot_progress.add_result(epoch, val.metric, key+"_best")

		self.plot_progress.write()
		self.plot_workers.write()
		self.plot_hyper.write()


	def manage(self):
		subscriber = pubsub_v1.SubscriberClient()
		result_subscription_path = subscriber.subscription_path(self.args.project, "pbt_result_worker")

		def result_callback(message):
			result_spec = pickle.loads(message.data)
			logger.info('Received result message: {}'.format(result_spec))
			
			for i in self.workers:
				if i.id == result_spec.id:
					if result_spec.success:
						i.record_finish(self.args.micro_step, result_spec.results)
						logger.info("{}.record_finish({})".format(result_spec.id, result_spec.results))
					else:
						self._remove_worker(i)

					message.ack()
					return

			message.nack()

		subscriber.subscribe(result_subscription_path, callback=result_callback)

		self.run()

	def drone(self):
		subscriber = pubsub_v1.SubscriberClient()
		run_subscription_path = subscriber.subscription_path(self.args.project, "pbt_run_worker")
		flow_control = pubsub_v1.types.FlowControl(max_messages=1)

		def run_callback(message):
			
			run_spec = pickle.loads(message.data)
			logger.info('Received run message: {}'.format(run_spec))
			
			try:
				worker = self.SubjectClass(self.init_params, self.hyperparam_spec)
				worker.params = run_spec.params
				worker.id = run_spec.id
				results = self.single_step(worker)
				result_spec = ResultSpec(run_spec.id, results, True)

			except Exception as e:
				traceback.print_exc()
				result_spec = ResultSpec(run_spec.id, None, False)

			data = pickle.dumps(result_spec)
			self.publisher.publish(self.result_topic_path, data=data)
			message.ack()


		# import concurrent.futures
		# executor_kwargs = {}
		# if sys.version_info[:2] == (2, 7) or sys.version_info >= (3, 6):
		# 	executor_kwargs['thread_name_prefix'] = (
		# 		'ThreadPoolExecutor-ThreadScheduler')
		# executor = concurrent.futures.ThreadPoolExecutor(
		# 	max_workers=1,
		# 	**executor_kwargs
		# )

		# from .scheduler import ThreadScheduler
		# scheduler = ThreadScheduler(executor)

		subscriber.subscribe(run_subscription_path, 
			callback=run_callback, 
			flow_control=flow_control,
			# scheduler= scheduler
			)

		while True:
			sleep(5)


		
	def run(self, epochs=1000):
	
		for i in range(epochs):
			started = time.time()
			logger.info("Epoch {}".format(i))
			self.scale_workers(i)
			self.step(i)

			logging.info("Exploit")
			self.exploit(i)

			logging.info("Print status")
			self.print_status(i)

			if self.args.save:
				if i % self.save_freq == self.save_freq-1:
					self.save()

			if len(self.workers) > 0:
				if self.workers[0].total_count > epochs:
					break

			
