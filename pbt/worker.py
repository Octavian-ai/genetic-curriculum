
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

from .params import Params

import logging
logger = logging.getLogger(__name__)


class Worker(object):
	"""Runs a PBT experiment

	Always provide a parameterless init so the Supervisor can spawn workers as needed

	"""
	def __init__(self, init_params, hyperparam_spec):
		self.current_count = 0
		self.total_count = 0
		self.id = uuid.uuid1()
		self.results = {}
		self.init_params = init_params
		self.gen_params(hyperparam_spec)

	def gen_params(self, hyperparam_spec):
		self.params = {
			k: v() for k, v in hyperparam_spec.items()
		}

	@property
	def params(self):
		pass
	
	@params.setter
	def params(self, params):
		pass

	# Experimental, plan to roll this out everywhere to replace params
	@property
	def friendly_params(self):
		return Params(self.init_params, self._params)
		

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




	def reset_count(self):
		self.current_count = 0
	
	def step(self, steps):
		self.current_count += steps
		self.total_count += steps
		self.do_step(steps)
	
	def do_step(self, steps):
		pass
 
	def eval(self):
		self.results = self.do_eval()
		return self.results
	
	def do_eval(self):
		pass

	def is_ready(self):
		mi = self.friendly_params["micro_step"]
		ma = self.friendly_params["macro_step"]

		return self.current_count > mi * ma

	def explore(self, heat):
		return {
			k:v.mutate(heat) for k, v in self.params.items()
		}

	@property
	def macro_steps(self):
		mi = self.friendly_params["micro_step"]
		ma = self.friendly_params["macro_step"]
		return self.total_count / mi / ma
	

	def save(self, path):
		with open(path, 'wb') as file:
			pickle.dump(self, file)

	@classmethod
	def load(cls, path, init_params):
		with open(path, 'rb') as file:
			w = pickle.load(file)
		w.init_params = init_params
		return w


	 