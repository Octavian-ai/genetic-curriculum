
import traceback
import argparse
import os.path
import os

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
				"length": RandIntRangeParamOf(1, int(os.getenv("MAX_LENGTH", 2)))(),
				"repeats": RandIntRangeParamOf(1, int(os.getenv("MAX_REPEATS", 5)))(),
			}


	def _mutate_dict(self, heat):
		return {
			k: val.mutate(heat)
			for k, val in self.v.items()
		}

	def mutate(self, heat):
		return type(self)(self.batch_size, self._mutate_dict(heat))

	@property
	def name_str(self):
		return "l"+ str(self.v["length"].value) + "r" + str(self.v["repeats"].value)


	@property
	def value(self):
		return repeat_copy.RepeatCopy(
			num_bits=4, 
			batch_size=self.batch_size, 
			**self.metric
		)

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
		# return (worker.results["loss"] + 1) / worker.results["total_elements"]
		return worker.results["correct_elements"] - worker.results["loss"]/10
	except Exception:
		return None

def name_fn(worker):
	return worker.params["dataset"].name_str + "_" + worker.params["heritage"].value + "_" + str(worker.id)[-5:-1]

def gen_baseline_params(args):

	def g():
		"""This is a set of params for generating the 'baseline' workers, e.g. the reference
		   that this experiment is trying to out-perform
		   """

		param_spec = gen_param_spec(args)

		lengths = [pow(2,i) for i in range(0, 6)]
		repeats = [pow(2,i) for i in range(0, 6)]

		datasets = []

		for i in lengths:
			for j in repeats:
				datasets.append(DatasetParam(args.batch_size, {
					"length":  RangeParam([FixedParam(i), FixedParam(i)]),
					"repeats": RangeParam([FixedParam(j), FixedParam(j)]),
				}))

		param_sets = []
		for i in datasets:
			params = param_spec.realize()
			params["dataset"] = i
			param_sets.append(params)

		return param_sets

	return g

def get_supervisor(args):
	return Supervisor(args, gen_param_spec(args), score, name_fn, False, gen_baseline_params=gen_baseline_params(args))






