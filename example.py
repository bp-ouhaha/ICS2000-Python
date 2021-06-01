import time
from ics2000.Core import *
hub = Hub("01:23:45:67:89:AB", "xxx@yyy.zzz", "magicalpassword")

ikea_1 = None
p1_module = None
for i in hub.devices():
  print("%s -> %s" % (i.name(), hub.get_device_status(i)))
  if i.name() == "ikea 1":
    ikea_1 = i._id
  if i.name() == "P1 Module":
    p1_module = i._id

ikea_1_status = hub.get_device_status(ikea_1)[3] != 0
print("ikea_1_status is %r" % ikea_1_status)

while(True):
  try:
    current = hub.get_device_check(p1_module)
    if len(current) > 5:
      timestr = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
      consumption = int(current[4])
      production  = int(current[5])
      print("%s : Consumption %d W - Production %d W" % (timestr, consumption, production))

      if ikea_1_status:
        if consumption > 0:
          ikea_1_status = False
          hub.zigbee_switch(ikea_1, ikea_1_status)
          print("ikea 1 disabled")
      else:
        if production > 1000+100: # 1000W plugged into ikea-1 add 100W margin
          ikea_1_status = True
          hub.zigbee_switch(ikea_1, ikea_1_status)
          print("ikea 1 enabled")
    else:
      print("reply too short")
  except Exception as e:
    print("something went really wrong")
    print(e)
    pass
  time.sleep(10)
