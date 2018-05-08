

import logging
logging.basicConfig()

from .helpers import *

if __name__ == "__main__":

	args = get_args()
	args.macro_step = 9999999999999
	args.heat = 0.0

	lengths     = [pow(2,i) for i in range(1, 10)]
	repetitions = [pow(2,i) for i in range(1, 10)]

	lengths = [2]
	repetitions = [5]

	datasets = []

	for i in lengths:
		for j in repetitions:
			datasets.append(DatasetParam(args.batch_size, {
				"min_length":  i,
				"max_length":  i,
				"min_repeats": j,
				"max_repeats": j,
			}))

	# datasets.reverse()

	if args.n_baselines is not None:
		datasets = datasets[:args.n_baselines]

	s = get_supervisor(args)
	s.n_workers = len(datasets)

	for i in datasets:
		params = gen_param_spec(args).realize()
		params["dataset"] = i
		s.add_worker_from_params(params)

	s.run(args.epochs)
