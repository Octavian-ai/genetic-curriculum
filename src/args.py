
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
	parser.add_argument('--micro-step', 			type=int,  default=20 * 1000)
	parser.add_argument('--macro-step', 			type=int,  default=1)

	parser.add_argument('--batch-size', 			type=int,  default=32)
	parser.add_argument('--n-workers', 				type=int,  default=10)
	
	parser.add_argument('--lr',						type=float, default=1e-4)
	parser.add_argument('--max-grad-norm',			type=float, default=50)
	parser.add_argument('--optimizer-epsilon',		type=float, default=1e-10)
	parser.add_argument('--heat',					type=float, default=1.0)

	parser.add_argument('--profile',				action='store_true')


	return parser.parse_args(args)
