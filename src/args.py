
import argparse

def get_args(args=None):
	parser = argparse.ArgumentParser()

	# General storage
	parser.add_argument('--output-dir', 			type=str,  default="./output")
	parser.add_argument('--model-dir',	 			type=str,  default="./output/checkpoint")

	# For storing to Google Cloud
	parser.add_argument('--bucket',					type=str,  default=None)
	parser.add_argument('--gcs-dir',				type=str,  default=None)

	parser.add_argument('--epochs', 				type=int,  default=1000)
	parser.add_argument('--micro-step', 			type=int,  default=5 * 1000)
	parser.add_argument('--macro-step', 			type=int,  default=1)

	parser.add_argument('--batch-size', 			type=int,  default=32)
	parser.add_argument('--n-workers', 				type=int,  default=10)
	
	parser.add_argument('--lr',						type=float, default=1e-4)
	parser.add_argument('--max-grad-norm',			type=float, default=50)
	parser.add_argument('--optimizer-epsilon',		type=float, default=1e-10)
	parser.add_argument('--heat',					type=float, default=1.0)

	parser.add_argument('--profile',				action='store_true')
	parser.add_argument('--single-threaded',		action='store_true')
	parser.add_argument('--log-tf',					action='store_true')

	parser.add_argument('--disable-save',			action='store_false',dest="save")
	parser.add_argument('--disable-load',			action='store_false',dest="load")





	return parser.parse_args(args)
