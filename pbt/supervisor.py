
import tensorflow as tf
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

from .param import FixedParam

from util import Ploty

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FP = collections.namedtuple('FallbackParam', ['value'])

		
		
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
				 ):

		self.args = args
		self.SubjectClass = SubjectClass
		self.init_params = init_params
		self.hyperparam_spec = hyperparam_spec
		self.score = score
		self.save_freq = save_freq
		self.save_counter = save_freq
		self.heat = 1.0

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


	def save(self):
		p = os.path.join(self.args.output_dir, "population")

		try:
			pathlib.Path(p).mkdir(parents=True, exist_ok=True) 
		except:
			pass

		# TODO: delete workers

		for worker in self.workers:
			worker.save(os.path.join(p, "worker_{}.pkl".format(worker.id)))

		logger.info("Saved workers")

	def load(self, input_dir):
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
		additional.count = random.randint(0,
			round(additional.params.get('macro_step', FP(5)).value * 0.2)
		)
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

	def print_status(self, epoch, time_taken):

		measures = {
			"score": self.score,
			"loss": lambda i: i.results.get('loss', -1),
			# "train": lambda i: i.results.get('train_acc', -1)
		}
		
		for i, worker in enumerate(self.workers):
			for key, fn in measures.items():
				self.plot_workers.add_result(epoch, fn(worker),  str(i)+_+key, "s", '-')

			for key, val in worker.params.items():
				if not isinstance(val, FixedParam):
					if isinstance(val.metric, int) or isinstance(val.metric, float):
						self.plot_hyper.add_result(epoch, val.metric, str(i)+"_" +key)

		for key, fn in measures.items():
			vs = [fn(i) for i in self.workers]

			if len(vs) > 0:
				best = max(vs)
				worst = min(vs)
				self.plot_progress.add_result(epoch, best, key+"_max")
				self.plot_progress.add_result(epoch, worst, key+"_min")

		self.plot_progress.add_result(epoch, len(self.workers), "n_workers")
		self.plot_progress.add_result(epoch, time_taken, "time_per_epoch")


		best_worker = max(self.workers, key=self.score)

		for key, val in best_worker.params.items():
			if not isinstance(val, FixedParam):
				if isinstance(val.metric, int) or isinstance(val.metric, float):
					self.plot_progress.add_result(epoch, val.metric, key+"_best")

		self.plot_progress.write()
		self.plot_workers.write()
		self.plot_hyper.write()



	# TODO: Make params into a virtual dictionary (and wrap .value for the caller)
	def params_equal(self, p1, p2):
		for k, v in p1.items():
			if v != p2[k]:
				return False
		return True

	def _remove_worker(self, worker, epoch):
		self.workers.remove(worker)
		self.fail_count += 1
		self.plot_progress.add_result(epoch, self.fail_count, "failed_workers")


	def step(self, epoch):
		for i in self.workers:
			try:
				steps = i.params.get("micro_step", FP(1)).value
				logger.info("{}.train({})".format(i.id, steps))
				i.step(steps)
				i.eval()
				logger.info("{}.eval()".format(i.id))
			except Exception:
				traceback.print_exc()
				self._remove_worker(i, epoch)
				continue

		if len(self.workers) == 0:
			raise Exception("All workers failed, your model has bugs")

		self.save_counter -= 1;
		if self.save_counter <= 0:
			self.save()
			self.save_counter = self.save_freq

	def exploit(self, worker):
		
		# Edge case: never exploit
		if len(self.workers) == 1:
			return None

		stack = list(self.workers)
		random.shuffle(stack) # Tie-break randomly
		stack = sorted(stack, key=self.score)
		
		n20 = max(math.ceil(len(stack)*0.2), 1)
		top20 = stack[-n20:]
		bottom20 = stack[:n20]
		
		if worker in bottom20:
			mentor = random.choice(top20)
			return mentor
		else:
			return None

	def explore(self, epoch):
		for i in self.workers:
			if i.is_ready():

				logger.info("{} is ready, attempting exploit".format(i.id))
				
				i.reset_count()
				better = self.exploit(i)

				if better is not None:
					if not self.params_equal(i.params, better.params):
						logger.info("{} replace with mutated {}".format(i.id, better.id))
						i.params = better.explore(self.heat)

						try:
							i.eval()
						except Exception:
							traceback.print_exc()
							self._remove_worker(i, epoch)
							continue

	def breed(self, epoch):
		for i in self.workers:
			if i.is_ready():

				newbie = self.breed_worker(i)

				try:
					newbie.eval()

				except Exception:
					traceback.print_exc()
					self._remove_worker(newbie, epoch)
					continue


		
	def run(self, epochs=1000):
		for i in range(epochs):
			started = time.time()
			logger.info("Epoch {}".format(i))
			self.scale_workers(i)
			self.step(i)
			self.explore(i)
			self.print_status(i, time.time()-started)
			
