
import logging
logging.basicConfig()

import tensorflow as tf
tf.logging.set_verbosity(tf.logging.INFO)

from .helpers import *

if __name__ == '__main__':

	args = get_args()
	s = get_supervisor(args)
	s.drone()
