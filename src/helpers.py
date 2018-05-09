
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
				"length": RandIntRangeParamOf(1, 2)(),
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
		"micro_step": args.micro_step,
		"macro_step": args.macro_step,
		"model_fn": model_fn, 
		"train_input_fn": gen_input_fn(), 
		"eval_input_fn":  gen_input_fn(True),
		"eval_steps": 20,
		"model_dir": args.model_dir,
		"run_config": tf.estimator.RunConfig(save_checkpoints_steps=99999999999,save_checkpoints_secs=None)
	}

	p.update(vars(args))

	return p


def score(worker):
	return worker.results.get("correct_elements", -1)


def get_supervisor(args):

	s = Supervisor(
		args,
		SingularSessionWorker, 
		gen_worker_init_params(args), 
		gen_param_spec(args), 
		score=score,
		n_workers=args.n_workers,
		heat=args.heat)

	return s






