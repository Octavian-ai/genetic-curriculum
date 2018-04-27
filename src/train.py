
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

	def __init__(self, v=None):

		self.v = v

		if self.v is None:
			self.v = {
				"max_length": 1
			}

	def mutate(self, heat):

		nv = {
			k: max(round(v + random.randint(-3,3)*heat),1)
			for k, v in self.v.items()
		}

		return type(self)(nv)

	@property
	def value(self):
		return repeat_copy.RepeatCopy(4, 16, 1, self.v["max_length"], 1, 2)

	def __str__(self):
		return str(self.v)

	def __eq__(self, other):
		self.v == other.v

	@property
	def metric(self):
		return self.v["max_length"]



def gen_param_spec(args):

	return {
		"macro_step": FixedParamOf(args.macro_step),
		"micro_step": FixedParamOf(args.micro_step),

		"heritage": Heritage,
		"model_id": ModelId,
		"dataset": DatasetParam,
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
				}
			)

		return gen
	return g

def gen_worker_init_params(args):
	
	p = {
		"model_fn": model_fn, 
		"train_input_fn": gen_input_fn(), 
		"eval_input_fn":  gen_input_fn(True),
		"model_dir": args.model_dir,
		"run_config": tf.estimator.RunConfig(save_checkpoints_steps=99999999999,save_checkpoints_secs=None)
	}

	p.update(vars(args))

	return p



def train(args):

	def score(worker):
		return max(100.0 - worker.results.get("loss", 0.0),0.0) * worker.params["dataset"].metric

	s = Supervisor(
		args,
		SingularSessionWorker, 
		gen_worker_init_params(args), 
		gen_param_spec(args), 
		score=score,
		n_workers=args.n_workers)

	s.run(args.epochs)


if __name__ == '__main__':
	tf.logging.set_verbosity('INFO')
	args = get_args()
	train(args)




