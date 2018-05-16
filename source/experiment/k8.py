
import logging
logging.basicConfig()
logger = logging.getLogger(__name__)

import requests
import json
import platform
import time

from .helpers import *

def i_am_leader(args):

	try:
		res = requests.get("http://localhost:4040")
	except requests.exceptions.ConnectionError:
		logger.warning("Could not contact leadership election sidecar, assuming not leader")
		return False

	if(res.ok):
		data = json.loads(res.content)
		leader_name = data["name"]
		my_name = platform.node()
		return leader_name == my_name

	else:
 		res.raise_for_status()


if __name__ == "__main__":

	args = get_args()

	manager = None
	drone = None

	drone = get_drone(args)

	while True:

		leader = i_am_leader(args)

		if manager is None and leader:
			manager = get_supervisor(args)

		if manager is not None and not leader:
			manager.close()
			manager = None

		drone.ensure_running()
		manager.ensure_running()

		if manager is not None:
			manager.run_epoch()

		time.sleep(args.sleep_per_cycle)

