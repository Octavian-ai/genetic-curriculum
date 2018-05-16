
import logging
logger = logging.getLogger(__name__)

from .param import GeneticParam

class Params(object):
	def __init__(self, fixed, dynamic):
		self.fixed = fixed
		self.dynamic = dynamic

	def __getitem__(self, key):
		if key in self.dynamic:
			return self.dynamic[key].value

		if key in self.fixed:
			return self.fixed[key]

		avail = list(self.fixed.keys()) + list(self.dynamic.keys())
		raise KeyError("{} not found, available keys: {}".format(key, avail))

	def get(self, key, default=None):
		try:
			return self.__getitem__(key)

		except Exception as ex:
			if default is not None:
				return default
			else:
				raise ex

	def __setitem(self, key, value):
		if instanceof(value, GeneticParam):
			self.dynamic[key] = value
		else:
			self.fixed[key] = value

	@property	
	def __dict__(self):
		r = {}

		for key, value in self.fixed.items():
			r[key] = value

		for key, value in self.dynamic.items():
			r[key] = value.value

		return r


class Mutateable(dict):
	def mutate(self, heat):
		return type(self)({
			k: v.mutate(heat) for k, v in self.items()
		})

class ParamSpec(dict):
	def realize(self):
		return Mutateable({
			k: v() for k, v in self.items()
		})



