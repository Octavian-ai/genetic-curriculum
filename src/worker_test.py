
import unittest
import tensorflow as tf

import pbt

from .args import get_args
from .train import gen_param_spec, gen_worker_init_params

import logging
logger = logging.getLogger(__name__)

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

		logger.info("-------------- NOW TRANSFER PARAMS 1 --------------")

		worker2 = self.vend_worker()
		worker2.params = worker1.explore(1.0)
		worker2.eval()

		self.assertEqual(worker1.results, worker2.results, "Results should be equal after param explore copy")

		logger.info("-------------- NOW TRANSFER PARAMS 2 --------------")

		worker3 = self.vend_worker()
		worker3.params = worker1.params
		worker3.eval()

		self.assertEqual(worker1.results, worker3.results, "Results should be equal after param copy")


		# self.assertGreaterEqual(worker2.results["accuracy"], worker1.results["accuracy"])
		# self.assertDictAlmostEqual(worker1.results, worker2.results, msg="Evaluation after param copy should be the same")
		



if __name__ == '__main__':	
	tf.logging.set_verbosity('INFO')
	logger.setLevel('INFO')
	unittest.main()


