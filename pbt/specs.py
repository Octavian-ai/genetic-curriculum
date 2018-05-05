
import collections

RunSpec = collections.namedtuple('RunSpec', ['id', 'params', 'group'])
ResultSpec = collections.namedtuple('ResultSpec', ['id', 'results', 'success', 'group'])