
import logging
logger = logging.getLogger(__name__)

class Params(object):
	def __init__(self, fixed, dynamic):
		self.fixed = fixed
		self.dynamic = dynamic

	def __getitem__(self, key):
		if key in self.dynamic:
			return self.dynamic[key].value

		if key in self.fixed:
			return self.fixed[key]

		logger.warn("Available keys:", self.fixed.keys(), self.dynamic.keys())

		raise KeyError(key)