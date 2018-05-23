
import argparse
import os

def get_args(args=None):
	parser = argparse.ArgumentParser()

	parser.add_argument('--run',					type=str,  default=os.getenv("RUN", "default"), help="Prefix used for file storage and messaging")

	# General storage
	parser.add_argument('--output-dir', 			type=str,  default="./output")
	parser.add_argument('--model-dir',	 			type=str,  default="./output/checkpoint")

	# For storing to Google Cloud
	parser.add_argument('--bucket',					type=str,  default=None)
	parser.add_argument('--gcs-dir',				type=str,  default=None)
	parser.add_argument('--project',				type=str,  default=os.getenv("GOOGLE_CLOUD_PROJECT", "octavian-181621"))

	parser.add_argument('--epochs', 				type=int,  default=1000)
	parser.add_argument('--micro-step', 			type=int,  default=1000)
	parser.add_argument('--macro-step', 			type=int,  default=5)

	parser.add_argument('--batch-size', 			type=int,  default=32)
	parser.add_argument('--n-workers', 				type=int,  default=os.getenv("N_WORKERS", 15))
	parser.add_argument('--job-timeout', 			type=int,  default=60*10)
	parser.add_argument('--message-timeout', 		type=int,  default=60*5)
	parser.add_argument('--sleep-per-cycle', 		type=int,  default=5)
	parser.add_argument('--save-secs', 				type=int,  default=60*5)
	parser.add_argument('--print-secs', 			type=int,  default=60)
	
	parser.add_argument('--lr',						type=float, default=1e-4)
	parser.add_argument('--max-grad-norm',			type=float, default=50)
	parser.add_argument('--optimizer-epsilon',		type=float, default=1e-10)
	parser.add_argument('--heat',					type=float, default=1.0)
	parser.add_argument('--exploit-pct',			type=float, default=0.2)

	parser.add_argument('--profile',				action='store_true')
	parser.add_argument('--single-threaded',		action='store_true')
	parser.add_argument('--log-tf',					action='store_true')
	parser.add_argument('--floyd-metrics',			action='store_true')


	parser.add_argument('--disable-save',			action='store_false',dest="save")
	parser.add_argument('--disable-load',			action='store_false',dest="load")

	parser.add_argument('--n-baselines', 			type=int,  default=None)
	parser.add_argument('--queue-type',				type=str,  default="rabbitmq", choices=["rabbitmq","google"])
	parser.add_argument('--amqp-url',				type=str,  default=os.getenv("AMQP_URL", 'amqp://guest:guest@localhost:5672/%2F'))


	return parser.parse_args(args)
