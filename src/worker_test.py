
import unittest
import os
import os.path
import sys

import pbt

from .args import get_args
from .train import gen_param_spec, gen_worker_init_params

class WorkerTestCase(unittest.TestCase):

	def vend_worker(self):
		return pbt.SingularSessionWorker(self.init_params, self.hyperparam_spec)


	# Setup and teardown

	def setUp(self):
		self.args = get_args()
		self.init_params = gen_worker_init_params(self.args)
		self.hyperparam_spec = gen_param_spec(self.args)

	
	# ==========================================================================
	# Tests
	# ==========================================================================
	
	# def test_save_load(self):
	# 	worker1 = self.vend_worker()
	# 	worker1.step(20)
	# 	worker1.eval()
	# 	worker1.save(file_path)
	# 	worker2 = EstimatorWorker.load(file_path, self.init_params)

	# 	self.assertEqual(worker1.results, worker2.results)
	# 	self.assertEqual(worker1.params, worker2.params)

	# 	worker2.eval()

	# 	self.assertDictAlmostEqual(worker1.results, worker2.results, msg="Evaluation after loading and eval should be unchanged")
	# 	self.assertEqual(worker1.params, worker2.params)


	def test_param_copy(self):
		worker1 = self.vend_worker()
		worker1.step(200)
		worker1.eval()

		worker2 = self.vend_worker()
		worker2.params = worker1.params
		worker2.eval()

		self.assertEqual(worker1.results["loss"], worker2.results["loss"], "Loss should be equal after param copy")

		# self.assertGreaterEqual(worker2.results["accuracy"], worker1.results["accuracy"])
		# self.assertDictAlmostEqual(worker1.results, worker2.results, msg="Evaluation after param copy should be the same")
		



if __name__ == '__main__':	
	# tf.logging.set_verbosity('INFO')
	unittest.main()


