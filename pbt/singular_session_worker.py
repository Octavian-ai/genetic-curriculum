
import tensorflow as tf
import numpy as np

import traceback
import os.path

from .pbt import *
from .pbt_param import *
from .params import *




class SingularSessionWorker(Worker):
	
	def __init__(self, init_params, hyperparam_spec):
		self.model = None
		self.sess = None
		self.graph = None

		super().__init__(init_params, hyperparam_spec)
		


	def setup_model(self):

		self.graph = tf.Graph()
		with self.graph.as_default():

			input_fn = self.init_params["train_input_fn"](self.friendly_params)
			inpt = input_fn()

			self.model = self.init_params["model_fn"](
				inpt[0],
				inpt[1],
				None,
				self.friendly_params
			)


		
	@property
	def params(self):  
		return self._params;

	# Experimental, plan to roll this out everywhere
	@property
	def friendly_params(self):
		return Params(self.init_params, self._params)
		
	@params.setter
	def params(self, value):
		self._params = value;
		self.setup_model()
		
	def do_step(self, steps):
		# We lazily initialise the estimator as during unpickling we may not have all the params
		if self.model is None:
			self.setup_model()


		with self.graph.as_default():
			with tf.train.SingularMonitoredSession() as sess:
				for i in range(steps):
					_, loss = sess.run([self.model.train_op, self.model.loss])
				
	def do_eval(self):
		if self.model is None:
			self.setup_model()

		with self.graph.as_default():
			with tf.train.SingularMonitoredSession() as sess:
				return sess.run({"loss":self.model.loss})
		


	# Hooks for Pickle
	def __getstate__(self):
		return {
			"_params":          self.params,
			"results":          self.results,
			"id":               self.id,
			"current_count":    self.current_count,
			"total_count":      self.total_count,
		}

	def __setstate__(self, state):
		self.id             = state.get("id", uuid.uuid1())
		self.total_count    = state.get("total_count", 0)
		self.current_count  = state.get("current_count", 0)

		self.results        = state.get("results", {})
		self._params        = state.get("_params", {})

		self.model = None
		self.sess = None

