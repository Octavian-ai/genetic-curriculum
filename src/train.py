
import traceback
import argparse
import os.path

import logging
logging.basicConfig()

import tensorflow as tf
import numpy as np

from .args import get_args
from .model import model_fn

from pbt import *

from dnc import *


class DatasetParam(GeneticParam):

	def __init__(self, batch_size, v=None):

		self.batch_size = batch_size
		self.v = v

		if self.v is None:
			initial_max = 5
			self.v = {
				"min_length":  1,
				"max_length":  1,
				"min_repeats": 1,
				"max_repeats": 1,
			}
			self.v = self._mutate_dict(1.0)


	def _mutate_dict(self, heat):
		return {
			k: v + (random.paretovariate(3.0) * heat * random.choice([-1.0,1.0]))
			for k, v in self.v.items()
		}

	def mutate(self, heat):
		return type(self)(self.batch_size, self._mutate_dict(heat))

	def _get_var(self, metric, fn):

		def s(k):
			return round(max(self.v[k], 1))

		return fn(s("min_"+metric),s("max_"+metric))


	@property
	def value(self):
		return repeat_copy.RepeatCopy(
			num_bits=4, 
			batch_size=self.batch_size, 
			min_length =self._get_var("length",  min),
			max_length =self._get_var("length",  max),
			min_repeats=self._get_var("repeats", min),
			max_repeats=self._get_var("repeats", max),
		)

	def __str__(self):
		return str(self.v)

	def __eq__(self, other):
		self.v == other.v

	@property
	def metric(self):
		return self._get_var("length", max) * self._get_var("repeats", max)


def DatasetParamOf(batch_size):
	def m(v=None):
		return DatasetParam(batch_size, v)
	return m

def gen_param_spec(args):

	return {
		"macro_step": FixedParamOf(args.macro_step),
		"micro_step": FixedParamOf(args.micro_step),

		"heritage": Heritage,
		"model_id": ModelId,
		"dataset": DatasetParamOf(args.batch_size),
	}

def gen_input_fn(is_eval=False):
	def g(params):
		def gen():
			seed = 123 if is_eval else None
			dataset_tensors = params["dataset"](seed)

			return (
				dataset_tensors.observations, 
				{
					"target": dataset_tensors.target,
					"mask": dataset_tensors.mask,
					"length": dataset_tensors.length,
				}
			)

		return gen
	return g

def gen_worker_init_params(args):
	
	p = {
		"model_fn": model_fn, 
		"train_input_fn": gen_input_fn(), 
		"eval_input_fn":  gen_input_fn(True),
		"eval_steps": 20,
		"model_dir": args.model_dir,
		"run_config": tf.estimator.RunConfig(save_checkpoints_steps=99999999999,save_checkpoints_secs=None)
	}

	p.update(vars(args))

	return p



def train(args):

	def score(worker):
		return worker.results.get("correct_elements", -1)

	s = Supervisor(
		args,
		SingularSessionWorker, 
		gen_worker_init_params(args), 
		gen_param_spec(args), 
		score=score,
		n_workers=args.n_workers,
		heat=args.heat)

	if args.load:
		s.load()

	s.run(args.epochs)


if __name__ == '__main__':
	args = get_args()

	if args.log_tf:
		tf.logging.set_verbosity('INFO')
		
	train(args)




