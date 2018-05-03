
import tensorflow as tf

import logging
logging.basicConfig(level=logging.INFO)

from .train_helpers import *

if __name__ == '__main__':
	args = get_args()

	if args.log_tf:
		tf.logging.set_verbosity('INFO')

	train(args)
