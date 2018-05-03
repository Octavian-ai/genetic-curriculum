

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
import queue as libqueue
import multiprocessing
from multiprocessing import Pool, Queue, SimpleQueue

from .param import FixedParam

from util import Ploty

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FP = collections.namedtuple('FallbackParam', ['value'])

multiprocessing.set_start_method('fork')


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
		self.result_queue = Queue()
		self.children = []

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

		try:
			logging.info("Number of CPUs: {}".format(multiprocessing.cpu_count()))
		except NotImplementedError:
			pass


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


	def step_singlethreaded(self, epoch):
		for i in self.workers:
			try:
				steps = i.params.get("micro_step", FP(1)).value
				logger.info("{}.train({})".format(i.id, steps))
				i.step(steps)
				logger.info("{}.eval()".format(i.id))
				i.eval()
				
			except Exception:
				traceback.print_exc()
				self._remove_worker(i, epoch)
				continue

		if len(self.workers) == 0:
			raise Exception("All workers failed, your model has bugs")

	def step_multithreaded(self, epoch):

		# --------------------------------------------------------------------------
		# Run parallel trainings
		# --------------------------------------------------------------------------

		steps = self.args.micro_step

		total_runners = len(self.workers)
		try:
			total_runners = multiprocessing.cpu_count()
		except NotImplementedError:
			pass

		not_running = [i for i in self.workers if not i.running]
		random.shuffle(not_running)
		not_running = not_running[:total_runners]

		for i in not_running:
			# i.record_start()
			i.start_time = 0

			if self.args.single_threaded:
				pid = 0
			else:
				pid = os.fork()

			self.result_queue.cancel_join_thread()

			# CHILD WORKER
			if pid == 0:
				try:
					logger.info("{}.train({})".format(i.id, steps))
					i.step(steps)
					logger.info("{}.eval()".format(i.id))
					results = i.eval()
					self.result_queue.put((i.id, results, True))
					logger.info("{}.result queue put success".format(i.id))					

				except Exception as ex:
					traceback.print_exc()
					# self.result_queue.put((i.id, None, False))
					logger.info("{}.result queue put fail".format(i.id))
				
				if not self.args.single_threaded:
					sleep(1)
					logger.info("os._exit(OK)")
					os._exit(os.EX_OK)
				
			
			# SUPERVISOR
			else:
				self.children.append(pid)

		
		sleep(50)

		# --------------------------------------------------------------------------
		# Collect the results
		# --------------------------------------------------------------------------
		
		def process_result(r):
			wid, results, success = r
			
			for i in self.workers:
				if i.id == wid:
					if success:
						i.record_finish(self.args.micro_step, results)
						logger.info("{}.record_finish({})".format(wid, results))
					else:
						self._remove_worker(i)

					break


		try:
			# Wait on at least one result
			process_result(self.result_queue.get_nowait())

			while not self.result_queue.empty():
				logger.info("result_queue.get()")
				process_result(self.result_queue.get_nowait())

		except libqueue.Empty:
			logger.info("result_queue empty")
			pass




	def step(self, epoch):
		self.step_multithreaded(epoch)

	def exploit(self, epoch):
		if len(self.workers) > 0:
			stack = list(self.workers)
			random.shuffle(stack) # Tie-break randomly
			stack = sorted(stack, key=self.score)
			
			n20 = max(math.ceil(len(stack)*0.2), 1)
			top20 = stack[-n20:]
			bottom20 = stack[:n20]

			for i in bottom20:
				if i.is_ready() and not i.running:
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

		time_per_step = [i.time_per_step for i in self.workers if i.time_per_step is not None]
		self.plot_progress.add_result(epoch, (np.mean(time_per_step) if len(time_per_step) > 0 else -1), "time_per_step")

		best_worker = max(self.workers, key=self.score)

		for key, val in best_worker.params.items():
			if not isinstance(val, FixedParam):
				if isinstance(val.metric, int) or isinstance(val.metric, float):
					self.plot_progress.add_result(epoch, val.metric, key+"_best")

		self.plot_progress.write()
		self.plot_workers.write()
		self.plot_hyper.write()


		
	def run(self, epochs=1000):
		try: 
			i = 0;
			while True:
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
						self.save(i)

				if len(self.workers) > 0:
					if self.workers[0].total_count > epochs:
						break


				i += 1


		except SystemExit as ex:
			for child in self.children:
				try:
					os.kill(child, signal.SIGKILL)
				except Exception: # It's already dead
					pass

			raise ex
			
