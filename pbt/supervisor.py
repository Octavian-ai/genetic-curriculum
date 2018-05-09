

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

from .param import FixedParam, FixedParamOf, FP
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

	def print_status(self, epoch):

		measures = {
			"score": self.score
		}

		if len(self.workers) > 0 and self.workers[0].results is not None:
			for key in self.workers[0].results.keys():
				measures[key] = lambda i: i.results.get(key, -1)

		def plot_param_metrics(plot, epoch, worker, prefix="", suffix=""):
			for key, val in worker.params.items():
				if not isinstance(val, FixedParam):
					if isinstance(val.metric, int) or isinstance(val.metric, float):
						plot.add_result(epoch, val.metric, prefix+key+suffix)
					elif isinstance(val.metric, dict):
						for mkey, mval in val.metric.items():
							if isinstance(mval, int) or isinstance(mval, float):
								plot.add_result(epoch, mval, prefix+key+"_"+mkey+suffix)

		
		for i, worker in enumerate(self.workers):

			self.plot_workers.add_result(epoch, self.score(worker),  str(i)+"_score")

			for key, fn in measures.items():
				self.plot_hyper.add_result(epoch, fn(worker),  str(i)+"_"+key, "s", '--')

			plot_param_metrics(self.plot_hyper, epoch, worker, str(i)+"_")

		for key, fn in measures.items():
			vs = [fn(i) for i in self.workers]

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

		best_worker = max(self.workers, key=self.score)
		plot_param_metrics(self.plot_progress, epoch, best_worker, suffix="_best")

		self.plot_progress.write()
		self.plot_workers.write()
		self.plot_hyper.write()


	def scale_workers(self, epoch):

		if isinstance(self.n_workers, int) or isinstance(self.n_workers, float):
			target = round(self.n_workers)
		else:
			target = self.n_workers(epoch)

		delta = target - len(self.workers)

		if delta != 0:
			logger.info("Resizing worker pool by {}".format(delta))

		if delta < 0:
			stack = list(self.workers)
			random.shuffle(stack) # Tie-break randomly
			stack = sorted(stack, key=self.score)
			
			n20 = round(len(self.workers)*0.2)
			bottom20 = stack[:n20]

			readies = [i for i in bottom20 if i.is_ready()]
			readies.sort(key=self.score)
			for i in readies[:min(-delta, len(readies))]:
				self.workers.remove(i)

		elif delta > 0:	
			for i in range(delta):
				self.add_random_worker()

	def add_random_worker(self):
		additional = self.SubjectClass(self.init_params, self.hyperparam_spec)
		self.workers.append(additional)

	def add_worker_from_params(self, params):
		additional = self.SubjectClass(self.init_params, self.hyperparam_spec)
		additional.params = params
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

	


	def __len__(self):
		return len(self.workers)

	@property
	def best_worker(self):
		return max(self.workers, key=self.score)
	

	def _remove_worker(self, worker, epoch):
		self.workers.remove(worker)
		self.fail_count += 1
		self.plot_progress.add_result(epoch, self.fail_count, "failed_workers")


	def single_worker_step(self, worker):
		steps = worker.friendly_params.get("micro_step", 1)
		logger.info("{}.train({})".format(worker.id, steps))
		worker.step(steps)
		logger.info("{}.eval()".format(worker.id))
		return worker.eval()

	def step_singlethreaded(self, epoch):
		for i in self.workers:
			try:
				self.single_worker_step(i)
				
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
			run_spec = RunSpec(i.id, i.params, self.args.group)
			data = pickle.dumps(run_spec)
			self.publisher.publish(self.run_topic_path, data=data)
			logger.info('{}.start()'.format(i.id))

		sleep(120)



	def step(self, epoch):
		if self.args.single_threaded:
			self.step_singlethreaded(epoch)
		else:
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
					i.reset_count()




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


	


	def manage(self):

		if not self.args.single_threaded:
			def result_callback(message):
				try:
					result_spec = pickle.loads(message.data)

					if result_spec.group == self.args.group:
						# logger.info('Received result message: {}'.format(result_spec))
						for i in self.workers:
							if i.id == result_spec.id:
								if result_spec.success:
									i.record_finish(self.args.micro_step, result_spec.results)
									logger.info("{}.finish({})".format(result_spec.id, result_spec.results))
								else:
									self._remove_worker(i)

								message.ack()
								return
				except:
					# Ok, that message wasn't for my codebase
					pass

				message.nack()

			subscriber = pubsub_v1.SubscriberClient()
			result_subscription_path = subscriber.subscription_path(self.args.project, "pbt_result_worker")
			subscriber.subscribe(result_subscription_path, callback=result_callback)

		self.run()

	def drone(self):
		
		def run_callback(message):
			try:
				run_spec = pickle.loads(message.data)

				if run_spec.group == self.args.group:
					logger.info('Received run message: {}'.format(run_spec))
					
					try:
						worker = self.SubjectClass(self.init_params, self.hyperparam_spec)
						worker.params = run_spec.params
						worker.id = run_spec.id
						message.ack() # training takes too long and the ack will miss its window
						results = self.single_worker_step(worker)
						result_spec = ResultSpec(run_spec.id, results, True, group=self.args.group)

					except Exception as e:
						traceback.print_exc()
						result_spec = ResultSpec(run_spec.id, None, False, group=self.args.group)

					data = pickle.dumps(result_spec)
					self.publisher.publish(self.result_topic_path, data=data)
					
					return

			except:
				# Message was from different version of the code or there are bugs in worker or those params just fail
				# Swallow message, keep the channel tidy
				# The supervisor will retry if that supervisor is still running
				# Each group is expected to be running on one codebase

				message.ack()
				pass

			message.nack()


		# Hack because lib crashes
		while True:
			try:
				# Hack for single-threaded
				from .google_pubsub_thread import Policy
				subscriber = pubsub_v1.SubscriberClient(Policy)
				run_subscription_path = subscriber.subscription_path(self.args.project, "pbt_run_worker")
				flow_control = pubsub_v1.types.FlowControl(max_messages=1)

				s = subscriber.subscribe(run_subscription_path, 
					callback=run_callback, 
					flow_control=flow_control
					)

				s.future.result()
			except Exception:
				sleep(5)

		
	def run(self, epochs=1000):
		epoch = 0
		while True:
			logger.info("Epoch {}".format(epoch))
			self.scale_workers(epoch)
			self.step(epoch)
			self.exploit(epoch)
			self.print_status(epoch)

			if self.args.save:
				if epoch % self.save_freq == self.save_freq-1:
					self.save()

			if len(self.workers) > 0:
				oldest = max(self.workers, key=lambda w: w.total_count)
				if oldest.total_count > epochs * self.args.micro_step:
					logger.info("Training completed ({} epochs, oldest worker completed {} total steps)".format(epoch, oldest.total_count))
					break

			epoch += 1

			
