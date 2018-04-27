import tensorflow as tf
import numpy as np

import traceback
from functools import reduce

from pbt import gen_scaffold
from dnc import DNC

def score_to_class(tensor, buckets=2):
	return tf.cast(tf.round(tensor * (buckets-1)), tf.int32)

def model_fn(features, labels, mode, params):

	# --------------------------------------------------------------------------
	# Model
	# --------------------------------------------------------------------------

	access_config = {
		"memory_size": 16,
		"word_size": 16,
		"num_reads": 4,
		"num_writes": 1,
	}
	
	controller_config = {
			"hidden_size": 64,
	}

	clip_value = 20

	dnc_core = DNC(access_config, controller_config, 5, clip_value)
	initial_state = dnc_core.initial_state(params["batch_size"])
	output_logits, _ = tf.nn.dynamic_rnn(
			cell=dnc_core,
			inputs=features,
			time_major=True,
			initial_state=initial_state)

	# --------------------------------------------------------------------------
	# Build EstimatorSpec
	# --------------------------------------------------------------------------

	train_loss = params["dataset"].cost(output_logits, labels["target"], labels["mask"])

	# Set up optimizer with global norm clipping.
	trainable_variables = tf.trainable_variables()
	grads, _ = tf.clip_by_global_norm(
			tf.gradients(train_loss, trainable_variables), params["max_grad_norm"])

	global_step = tf.get_variable(
			name="global_step",
			shape=[],
			dtype=tf.int64,
			initializer=tf.zeros_initializer(),
			trainable=False,
			collections=[tf.GraphKeys.GLOBAL_VARIABLES, tf.GraphKeys.GLOBAL_STEP])

	optimizer = tf.train.RMSPropOptimizer(
			params["lr"], epsilon=params["optimizer_epsilon"])
	
	train_step = optimizer.apply_gradients(
			zip(grads, trainable_variables), global_step=global_step)

	
	# dataset_tensors_np, output_np = sess.run([dataset_tensors, output])
	# dataset_string = dataset.to_human_readable(dataset_tensors_np, output_np)

	eval_metric_ops = {
		"accuracy": tf.metrics.accuracy(
			output_logits * tf.expand_dims(labels["mask"],-1), 
			labels["target"]),
		"loss": tf.metrics.mean(train_loss),
	}


	return tf.estimator.EstimatorSpec(
		mode, 
		loss=train_loss, 
		train_op=train_step, 
		eval_metric_ops=eval_metric_ops,
		scaffold=gen_scaffold(params)
	)

	# --------------------------------------------------------------------------


	


