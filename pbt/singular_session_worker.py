
import tensorflow as tf
import numpy as np

import traceback
import os.path

from .worker import Worker
from .param import *
from .params import *



class SingularSessionWorker(Worker):
	
	def __init__(self, init_params, hyperparam_spec):
		self.model = None
		self.graph = None
		self.sess = None
		self._params = {}

		super().__init__(init_params, hyperparam_spec)


	def close(self):
		if self.sess is not None:
			self.sess.close()
			self.sess = None

		self.graph = None
		self.model = None
		


	def setup_model(self, mode="train"):
		self.close()

		self.graph = tf.Graph()
		with self.graph.as_default():

			input_fn = self.init_params[mode+"_input_fn"](self.friendly_params)
			inpt = input_fn()

			self.model = self.init_params["model_fn"](
				inpt[0],
				inpt[1],
				None,
				self.friendly_params
			)

			self.model_mode = mode

			hooks = [
			]

			if mode == "train":
				self.saver = tf.train.Saver()
				self.checkpoint_saver = tf.train.CheckpointSaverHook(
						checkpoint_dir=self.model_dir,
						save_steps=self.friendly_params["micro_step"],
						saver=self.saver)

				hooks.append(self.checkpoint_saver)


			if tf.summary.merge_all() is not None:
				hooks.append(
					tf.train.SummarySaverHook(
						save_secs=30, 
						output_dir=self.model_dir, 
						summary_op=tf.summary.merge_all()
					)
				)

			if os.path.exists(self.model_dir):
				# We should resume from that location
				load_dir = self.model_dir
			else:
				# We should try to warm start
				load_dir = self.warm_start_dir

			self.sess = tf.train.SingularMonitoredSession(
				hooks=hooks, checkpoint_dir=load_dir
			)


		
	@property
	def params(self):  
		return self._params;
		
	@params.setter
	def params(self, value):
		self._params = value


		
	def do_step(self, steps):
		self.setup_model("train")

		with self.graph.as_default():
			for i in range(steps):
				_, loss = self.sess.run([self.model.train_op, self.model.loss])

			# self.checkpoint_saver.end(self.sess.raw_session())

		self.close()
				
	def do_eval(self):
		self.setup_model("eval")

		with self.graph.as_default():
			# TODO: copy eval_metrics boilerplate
			return self.sess.run({"loss":self.model.loss})

		self.close()
		


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

