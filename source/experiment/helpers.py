
import traceback
import argparse
import os.path

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
			self.v = {
				"length": RandIntRangeParamOf(1, 4)(),
				"repeats": RandIntRangeParamOf(1, 5)(),
			}


	def _mutate_dict(self, heat):
		return {
			k: val.mutate(heat)
			for k, val in self.v.items()
		}

	def mutate(self, heat):
		return type(self)(self.batch_size, self._mutate_dict(heat))


	@property
	def value(self):
		return repeat_copy.RepeatCopy(
			num_bits=4, 
			batch_size=self.batch_size, 
			**self.metric
		)

	def __str__(self):
		return str(self.v)

	def __eq__(self, other):
		self.v == other.v

	@property
	def metric(self):
		return {
			"min_length":  self.v["length"].value[0],
			"max_length":  self.v["length"].value[1],
			"min_repeats": self.v["repeats"].value[0],
			"max_repeats": self.v["repeats"].value[1],
		}


def DatasetParamOf(batch_size):
	def m(v=None):
		return DatasetParam(batch_size, v)
	return m


def gen_param_spec(args):
	return ParamSpec({
		"heritage": Heritage,
		"model_id": ModelId,
		"dataset": DatasetParamOf(args.batch_size),
	})


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
					"total_targ_batch": dataset_tensors.total_targ_batch,
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
		"run_config": tf.estimator.RunConfig(save_checkpoints_steps=99999999999,save_checkpoints_secs=None)
	}

	p.update(vars(args))

	return p

def get_drone(args):
	return Drone(args, SingularSessionWorker, gen_worker_init_params(args))


def score(worker):
	try:
		return worker.results["correct_elements"]
	except Exception:
		return -1


def get_supervisor_old(args):
	return Supervisor(
		args,
		SingularSessionWorker, 
		gen_worker_init_params(args), 
		gen_param_spec(args), 
		score=score,
		n_workers=args.n_workers,
		heat=args.heat)

def get_supervisor(args):
	return Supervisor(args, gen_param_spec(args), score)






