

import logging
logging.basicConfig()

from .helpers import *

if __name__ == "__main__":

	total_steps = 12 * 1000

	args = get_args()
	args.macro_step = 9999999999999
	args.micro_step = 300
	args.heat = 0.0

	lengths = [pow(2,i) for i in range(1, 6)]
	repeats = [pow(2,i) for i in range(1, 6)]

	# lengths = [1]
	# repetitions = [5]

	datasets = []

	for i in lengths:
		for j in repeats:
			datasets.append(DatasetParam(args.batch_size, {
				"length":  FixedParam([i,i]),
				"repeats": FixedParam([j,j]),
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

	s.run(round(total_steps / args.micro_step))
