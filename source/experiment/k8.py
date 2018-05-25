
import logging, coloredlogs
logger = logging.getLogger(__name__)
coloredlogs.install(level='DEBUG',logger=logger)
coloredlogs.install(level='DEBUG',logger=logging.getLogger('pbt'))

import requests
import json
import platform
import time
import pika
import threading

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



def do_drone(args):
 	drone = get_drone(args)

 	while True:
 		drone.run_epoch()
 		time.sleep(args.sleep_per_cycle)

def do_supervisor(args):
	sup = get_supervisor(args)

	while True:
		sup.run_epoch()
		time.sleep(args.sleep_per_cycle)


if __name__ == "__main__":

	args = get_args()

	started_drone = False
	started_sup = False

	while True:
		am_sup = i_am_leader(args)
		am_drone = not am_sup or args.master_works

		logger.debug("Main dispatch loop am_sup:{} am_drone:{}".format(am_sup, am_drone))

		if am_sup and not started_sup:
			t = threading.Thread(target=do_supervisor, args=(args,))
			t.setDaemon(True)
			t.start()
			started_sup = True
			
		if am_drone and not started_drone:
			t = threading.Thread(target=do_drone, args=(args,))
			t.setDaemon(True)
			t.start()
			started_drone = True

		time.sleep(args.sleep_per_cycle)
			


def old_main_loop():
	manager = None
	drone = None

	try:
		while True:
			am_leader = i_am_leader(args)
			am_drone = not am_leader or args.master_works

			if am_leader and manager is None:
					logger.info("Start supervisor")
					manager = get_supervisor(args)
			elif not am_leader and manager is not None:
					logger.info("Stop supervisor")
					manager.close()
					manager = None

			if am_drone and drone is None:
				logger.info("Start drone")
				drone = get_drone(args)	
			elif not am_drone and drone is not None:
				logger.info("Stop drone")
				drone.close()
				drone = None

			if drone is not None:
				drone.run_epoch()

			if manager is not None:
				manager.run_epoch()

			time.sleep(args.sleep_per_cycle)



	except KeyboardInterrupt:
		if manager is not None:
			manager.close()

		if drone is not None:
			drone.close()


