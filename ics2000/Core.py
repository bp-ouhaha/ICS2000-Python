import enum
import requests
import json
import ast

from ics2000.Command import *
from ics2000.Devices import *

base_url = "https://trustsmartcloud2.com/ics2000_api/"


def constraint_int(inp, min_val, max_val) -> int:
    if inp < min_val:
        return min_val
    elif inp > max_val:
        return max_val
    else:
        return inp


class Hub:
    aes = None
    mac = None

    def __init__(self, mac, email, password):
        """Initialize an ICS2000 hub."""
        self.mac = mac
        self._email = email
        self._password = password
        self._connected = False
        self._homeId = -1
        self._devices = []
        self.loginuser()
        self.pulldevices()

    def loginuser(self):
        print("Logging in user")
        url = base_url + "/account.php"
        params = {"action": "login", "email": self._email, "mac": self.mac.replace(":", ""),
                  "password_hash": self._password, "device_unique_id": "android", "platform": "Android"}
        req = requests.get(url, params=params)
        if req.status_code == 200:
            resp = json.loads(req.text)
            self.aes = resp["homes"][0]["aes_key"]
            self._homeId = resp["homes"][0]["home_id"]
            if self.aes is not None:
                print("Succesfully got AES key")
                self._connected = True

    def connected(self):
        return self._connected

    def pulldevices(self):
        url = base_url + "/gateway.php"
        params = {"action": "sync", "email": self._email, "mac": self.mac.replace(":", ""),
                  "password_hash": self._password, "home_id": self._homeId}
        resp = requests.get(url, params=params)
        self._devices = []
        devices = [item.value for item in DeviceType]
        for device in json.loads(resp.text):
            decrypted = json.loads(decrypt(device["data"], self.aes))
            if "module" in decrypted and "info" in decrypted["module"]:
                decrypted = decrypted["module"]
                #print("found device type %s" % decrypted)
                name = decrypted["name"]
                entityid = decrypted["id"]

                if decrypted["device"] not in devices:
                    self._devices.append(Device(name, entityid, self))
                else:
                  dev = DeviceType(decrypted["device"])
                  if   dev == DeviceType.SWITCH:
                      self._devices.append(Device(name, entityid, self))
                  elif dev == DeviceType.DIMMER:
                      self._devices.append(Dimmer(name, entityid, self))
                  elif dev == DeviceType.ACTUATOR:
                      self._devices.append(Device(name, entityid, self))
                  elif dev == DeviceType.ZIGBEE_SOCKET:
                      self._devices.append(Device(name, entityid, self))
                  #else:
                  #    print("unknown type device, setting up as standard Device...")
                  #    self._devices.append(Device(name, entityid, self))
            elif "module" in decrypted and "name" in decrypted["module"]:
                decrypted = decrypted["module"]
                print("found device type %s (without info)" % decrypted)
                name = decrypted["name"]
                entityid = decrypted["id"]
                if decrypted["device"] in devices:
                  dev = DeviceType(decrypted["device"])
                  if dev == DeviceType.ENERGY_MODULE:
                      self._devices.append(Device(name, entityid, self))

    def devices(self):
        return self._devices

    def sendcommand(self, command):
        url = base_url + "/command.php"
        params = {"action": "add", "email": self._email, "mac": self.mac.replace(":", ""),
                  "password_hash": self._password, "device_unique_id": "android", "command": command}
        requests.get(url, params=params)

    def turnoff(self, entity):
        cmd = self.simplecmd(entity, 0, 0)
        self.sendcommand(cmd.getcommand())

    def turnon(self, entity):
        cmd = self.simplecmd(entity, 0, 1)
        self.sendcommand(cmd.getcommand())

    def dim(self, entity, level):
        cmd = self.simplecmd(entity, 1, level)
        self.sendcommand(cmd.getcommand())

    def zigbee_color_temp(self, entity, color_temp):
        color_temp = constraint_int(color_temp, 0, 600)
        cmd = self.simplecmd(entity, 9, color_temp)
        self.sendcommand(cmd.getcommand())

    def zigbee_dim(self, entity, dim_lvl):
        dim_lvl = constraint_int(dim_lvl, 1, 254)
        cmd = self.simplecmd(entity, 4, dim_lvl)
        self.sendcommand(cmd.getcommand())

    def zigbee_switch(self, entity, power):
        cmd = self.simplecmd(entity, 3, (str(1) if power else str(0)))
        self.sendcommand(cmd.getcommand())

    def zigbee_socket(self, entity, power):
        cmd = self.simplecmd(entity, 3, 1 if power else 0)
        self.sendcommand(cmd.getcommand())

    def get_device_status(self, entity) -> []:
        url = base_url + "/entity.php"
        params = {"action": "get-multiple", "email": self._email, "mac": self.mac.replace(":", ""),
                  "password_hash": self._password, "home_id": self._homeId, "entity_id": "[" + str(entity) + "]"}
        resp = requests.get(url, params=params)
        arr = json.loads(resp.text)
        if len(arr) == 1 and "status" in arr[0] and arr[0]["status"] is not None:
            obj = arr[0]
            dcrpt = json.loads(decrypt(obj["status"], self.aes))
            if "module" in dcrpt and "functions" in dcrpt["module"]:
                return dcrpt["module"]["functions"]
        return []

    def get_device_check(self, entity) -> []:
        url = base_url + "/entity.php"
        params = {"action": "check", "email": self._email, "mac": self.mac.replace(":", ""),
                  "password_hash": self._password, "entity_id": str(entity)}
        resp = requests.get(url, params=params)
        arr = json.loads(resp.text)
        if len(arr) == 4:
            # 0: data-version
            # 1: data
            # 2: status-version
            # 3: status
            try:
              dcrpt = json.loads(decrypt(arr[3], self.aes))
              if "module" in dcrpt and "functions" in dcrpt["module"]:
                  return dcrpt["module"]["functions"]
            except TypeError:
              pass
            except json.decoder.JSONDecodeError:
              pass
        return []

    def getlampstatus(self, entity) -> Optional[bool]:
        status = self.get_device_status(entity)
        if len(status) >= 1:
            return True if status[0] == 1 else False
        return False

    def simplecmd(self, entity, function, value):
        cmd = Command()
        cmd.setmac(self.mac)
        cmd.settype(128)
        cmd.setmagic()
        cmd.setentityid(entity)
        cmd.setdata(
            "{\"module\":{\"id\":" + str(entity) + ",\"function\":" + str(function) + ",\"value\":" + str(value) + "}}",
            self.aes)
        return cmd


class DeviceType(enum.Enum):
    SWITCH = 1
    DIMMER = 2
    ACTUATOR = 3
    MOTION_SENSOR = 4
    CONTACT_SENSOR = 5
    DOORBELL_ACDB_7000A = 6
    WALL_CONTROL_1_CHANNEL = 7
    WALL_CONTROL_2_CHANNEL = 8
    REMOTE_CONTROL_1_CHANNEL = 9
    REMOTE_CONTROL_2_CHANNEL = 10
    REMOTE_CONTROL_3_CHANNEL = 11
    REMOTE_CONTROL_16_CHANNEL = 12
    REMOTE_CONTROL_AYCT_202 = 13
    CHIME = 14
    DUSK_SENSOR = 15
    ARC_REMOTE = 16
    ARC_CONTACT_SENSOR = 17
    ARC_MOTION_SENSOR = 18
    ARC_SMOKE_SENSOR = 19
    ARC_SIREN = 20
    DOORBELL_ACDB_7000B = 21
    AWMT = 22
    SOMFY_ACTUATOR = 23
    LIGHT = 24
    WALL_SWITCH_AGST_8800 = 25
    WALL_SWITCH_AGST_8802 = 26
    BREL_ACTUATOR = 27
    CONTACT_SENSOR_2 = 28
    ARC_KEYCHAIN_REMOTE = 29
    ARC_ACTION_BUTTON = 30
    ARC_ROTARY_DIMMER = 31
    ZIGBEE_UNKNOWN_DEVICE = 32
    ZIGBEE_SWITCH = 33
    ZIGBEE_DIMMER = 34
    ZIGBEE_RGB = 35
    ZIGBEE_TUNABLE = 36
    ZIGBEE_MULTI_PURPOSE_SENSOR = 37
    ZIGBEE_LOCK = 38
    ZIGBEE_LIGHT_LINK_REMOTE = 39
    ZIGBEE_LIGHT = 40
    ZIGBEE_SOCKET = 41
    ZIGBEE_LEAKAGE_SENSOR = 42
    ZIGBEE_SMOKE_SENSOR = 43
    ZIGBEE_CARBON_MONOXIDE_SENSOR = 44
    ZIGBEE_TEMPERATURE_AND_HUMIDITY_SENSOR = 45
    ZIGBEE_LIGHT_GROUP = 46
    ZIGBEE_FIREANGEL_SENSOR = 47
    CAMERA_MODULE = 48
    LOCATION_MODULE = 49
    SYSTEM_MODULE = 50
    SECURITY_MODULE = 53
    ENERGY_MODULE = 238
    WEATHER_MODULE = 244


def get_hub(mac, email, password) -> Optional[Hub]:
    url = base_url + "/gateway.php"
    params = {"action": "check", "email": email, "mac": mac.replace(":", ""), "password_hash": password}
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        if ast.literal_eval(resp.text)[1] == "true":
            return Hub(mac, email, password)
    return

