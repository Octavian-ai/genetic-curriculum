

import uuid
import time
import collections
import platform

RunSpec = collections.namedtuple('RunSpec', [
	'group', 
	'id', 
	'from_hostname',
	'params',
	'recent_steps',
	'total_steps',
	'micro_step',
	'macro_step',
	'time_sent'])


ResultSpec = collections.namedtuple('ResultSpec', [
	'group', 
	'id', 
	'from_hostname',
	'results', 
	'success', 
	'steps', 
	'recent_steps',
	'total_steps',
	'time_sent'])

HeartbeatSpec = collections.namedtuple('HeartbeatSpec', ['group', 'id', 'time_sent'])



class WorkerHeader(object):

	def __init__(self, params):
		self.id = uuid.uuid1()
		self.results = None
		self.time_last_updated = 0
		self.total_steps = 0
		self.recent_steps = 0

		self.params = params

	def update_from_result_spec(self, result_spec):
		self.total_steps = result_spec.total_steps
		self.recent_steps = result_spec.recent_steps
		self.results = result_spec.results
		self.time_last_updated = time.time()
		self.time_last_dispatched = 0

	def gen_run_spec(self, args):
		return RunSpec(
			args.run, 
			self.id, 
			platform.node(),
			self.params, 
			self.recent_steps,
			self.total_steps,
			args.micro_step, 
			args.macro_step,
			time.time())


