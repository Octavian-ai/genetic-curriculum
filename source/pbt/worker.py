
import tensorflow as tf
import random
import pickle
import uuid
import os
import os.path
import collections
import logging
import sys
import math
import time

# from comet_ml import Experiment

from .params import Params

import logging
logger = logging.getLogger(__name__)


class Worker(object):
	"""Runs a PBT experiment

	Always provide a parameterless init so the Supervisor can spawn workers as needed

	"""
	def __init__(self, init_params, params):
		
		# self.experiment = Experiment(api_key="bRptcjkrwOuba29GcyiNaGDbj")
		self.id = uuid.uuid1()
		
		self.init_params = init_params
		self.params = params

		self.results = {}
		self.total_count = 0
		self.time_started = 0
		self.performance = (0,0)
		self.reset_count()


	
	# --------------------------------------------------------------------------
	# Implement these
	# --------------------------------------------------------------------------

	def do_step(self, steps):
		"""Execute a training step. Returns nothing."""
		pass

	def do_eval(self):
		"""Returns evaluation results as a dict"""
		pass



	# --------------------------------------------------------------------------
	# Parameter methods
	# --------------------------------------------------------------------------

	@property
	def params(self):
		return self._params
	
	@params.setter
	def params(self, params):
		self._params = params
		# self.experiment.log_multiple_params(vars(self.friendly_params))

	def explore(self, heat):
		return {
			k:v.mutate(heat) for k, v in self.params.items()
		}


	# Experimental, plan to roll this out everywhere to replace params
	@property
	def friendly_params(self):
		return Params(self.init_params, self._params)
		

	# --------------------------------------------------------------------------
	# Properties
	# --------------------------------------------------------------------------
	

	# Will crash if model_id param missing
	# @returns dirictory string to save model to
	@property
	def model_dir(self):
		return os.path.join(self.init_params["model_dir"], self.friendly_params["model_id"]["cur"])
	
	# Will crash if model_id param missing	
	# @returns directory string to warm start model from or None if model should not warm start	
	@property
	def warm_start_dir(self):
		if self.friendly_params["model_id"]["warm_start_from"] is None:
			return None
		else:
			return os.path.join(self.init_params["model_dir"], self.friendly_params["model_id"]["warm_start_from"])

	def is_ready(self):
		mi = self.friendly_params["micro_step"]
		ma = self.friendly_params["macro_step"]

		return self.current_count >= mi * ma


	# --------------------------------------------------------------------------
	# Step and eval
	# --------------------------------------------------------------------------

	def reset_count(self):
		self.current_count = 0
		
	def step(self, steps):
		self.current_count += steps
		self.total_count += steps

		started = time.time()
		
		self.do_step(steps)

		time_taken = time.time() - started
		tf.logging.info("train_op/second: {}".format(float(steps)/float(time_taken)))


	def eval(self):
		self.results = self.do_eval()

		return self.results


	def step_and_eval(self, steps):
		logger.info("{}.train({})".format(self.id, steps))
		self.step(steps)
		logger.info("{}.eval()".format(self.id))
		return self.eval()

	# --------------------------------------------------------------------------
	# Multi-process sync
	# --------------------------------------------------------------------------
	
	def record_start(self):
		self.time_started = time.time()
		

	def record_finish(self, steps, results):
		self.current_count += steps
		self.total_count += steps
		self.performance = (steps, time.time()-self.time_started)
		self.time_started = 0
		self.results = results


	# --------------------------------------------------------------------------
	# Load and save
	# --------------------------------------------------------------------------

	def save(self, path):
		with open(path, 'wb') as file:
			pickle.dump(self, file)

	@classmethod
	def load(cls, path, init_params):
		with open(path, 'rb') as file:
			w = pickle.load(file)
		w.init_params = init_params
		w.reset_count()
		return w

	 