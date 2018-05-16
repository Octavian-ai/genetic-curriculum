
import collections
import uuid

RunSpec = collections.namedtuple('RunSpec', ['group', 'id', 'params','steps', 'time_sent'])
ResultSpec = collections.namedtuple('ResultSpec', ['group', 'id', 'results', 'success', 'steps', 'time_sent'])

class WorkerHeader(object):

	def __init__(self, params):
		self.id = uuid.uuid1()
		self.results = None
		self.time_dispatched = 0
		self.total_steps = 0
		self.recent_steps = 0

		self.params = params

	def record_result(self, result_spec):
		self.total_steps += result_spec.steps
		self.recent_steps += result_spec.steps
		self.results = result_spec.results