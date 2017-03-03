##           Homewizard Plugin
##
##           Author:         Raymond Van de Voorde
##           Version:        1.0.2
##           Last modified:  03-03-2017
##
"""
<plugin key="Homewizard" name="Homewizard" author="Wobbles" version="1.0.2" externallink="https://www.homewizard.nl/">
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="127.0.0.1" />
	<param field="Password" label="Password" width="200px" required="true" default="1234" />
        <param field="Mode1" label="Poll interval" width="100px" required="true" default=20 />
        
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal"  default="true" />
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import http.client
import json
import base64

# Homewizard status variables
hw_version = ""
hw_status = "Unknown"
hw_route = ""
hw_preset = 0
hw_types = {"0":"None"}

#constants
hwid_offset = {"term_id": 111, "en_id": 101, "rain_id": 201, "wind_id": 202, "preset_id": 121, "sensor_id": 61}

# Domoticz call back functions
def onStart():
    global hwid_offset, hw_types
    if Parameters["Mode6"] == "Debug":
        Domoticz.Debugging(1)
        DumpConfigToLog()    

    # Test if the first connection is ok
    rData = HWConnect()

    # Get all KAKU sensors
    Sensors(rData)
    
    # Get all thermometers
    Thermometers()

    # Get all enerymeters
    EnergyMeters()

    # Get all switches and dimmers
    Switches()

    # Add the preset selector switch    
    if ( hwid_offset["preset_id"] not in Devices ):
        LevelActions = "LevelActions:"+stringToBase64("||||")+";"
        LevelNames = "LevelNames:"+stringToBase64("Off|Home|Away|Sleep|Holiday")+";"
        Other = "LevelOffHidden:dHJ1ZQ==;SelectorStyle:MA==" # true is "dHJ1ZQ==", false is "ZmFsc2U=",0 is "MA==", 1 is "MQ=="
        Options = LevelActions+LevelNames+Other
        Domoticz.Device(Name="Preset", Unit=hwid_offset["preset_id"], TypeName="Selector Switch", Options=Options).Create()

    # Add the rainmeter
    if ( hwid_offset["rain_id"] not in Devices ):
        Domoticz.Device(Name="Regen",  Unit=hwid_offset["rain_id"], TypeName="Rain").Create()

    # Add the windmeter
    if ( hwid_offset["wind_id"] not in Devices ):
        Domoticz.Device(Name="Wind",  Unit=hwid_offset["wind_id"], TypeName="Wind+Temp+Chill").Create()    
    
    if is_number(Parameters["Mode1"]):
        if  10 <= int(Parameters["Mode1"]) <= 60:
            Domoticz.Log("Update interval set to " + Parameters["Mode1"])
            Domoticz.Heartbeat(int(Parameters["Mode1"]))
        else:
            Domoticz.Heartbeat(20)
    else:
        Domoticz.Heartbeat(20)    
    
    return True

def onConnect(Status, Description):
    return True

def onMessage(Data, Status, Extra):
    global hw_status, hw_route, hwid_offset, hw_types    
    
    if hw_status == "ok":                    
        hw_preset = GetValue(Data["response"], "preset", 0)
        if hw_preset == 0:
            UpdateDevice(hwid_offset["preset_id"], 2, "10")
        elif hw_preset == 1:
            UpdateDevice(hwid_offset["preset_id"], 2, "20")
        elif hw_preset == 2:
            UpdateDevice(hwid_offset["preset_id"], 2, "30")
        elif hw_preset == 3:
            UpdateDevice(hwid_offset["preset_id"], 2, "40")

        try:
            # Update the wind device
            wind_0 = float(GetValue(Data["response"]["windmeters"][0], "ws", 0) / 3.6) * 10
            wind_1 = GetValue(Data["response"]["windmeters"][0], "dir", "N 0")
            wind_1 = wind_1.split(" ", 1)
            wind_2 = float(GetValue(Data["response"]["windmeters"][0], "gu", 0) / 3.6) * 10
            wind_3 = GetValue(Data["response"]["windmeters"][0], "wc", 0)
            wind_4 = GetValue(Data["response"]["windmeters"][0], "te", 0)
            UpdateDevice(hwid_offset["wind_id"], 0, str(wind_1[1])+";"+str(wind_1[0])+";"+str(wind_0)+";"+str(wind_2)+";"+str(wind_4)+";"+str(wind_3))
        except:
            Domoticz.Error("Error reading wind values")

        try:
            # Update the rain device            
            rain_0 = GetValue(Data["response"]["rainmeters"][0], "mm", 0)
            rain_1 = GetValue(Data["response"]["rainmeters"][0], "3h", 0)
            UpdateDevice(hwid_offset["rain_id"], 0, str(rain_1) + ";" + str(rain_0))
        except:
            Domoticz.Error("Error reading rainmeter values")

        try:
            # Update the thermometes
            x = 0            
            for thermometer in GetValue(Data["response"], "thermometers", []):
                tmp_0 = GetValue(thermometer, "te", 0)
                tmp_1 = GetValue(thermometer, "hu", 0)
                UpdateDevice(hwid_offset["term_id"]+x, 0, str(tmp_0) + ";" + str(tmp_1) + ";" + str(HumStat(tmp_1)))
                x = x + 1
        except:
            Domoticz.Error("Error reading thermometers values")
                
        try:
            # Update the switches
            for Switch in GetValue(Data["response"], "switches", []):
                sw_id = Switch["id"] + 1
                sw_status = GetValue(Switch, "status", "off").lower()

                if ( sw_status == "on" ):
                    sw_status = "1"
                elif ( sw_status == "off" ):
                    sw_status = "0"
                
                # Update the switch/dimmer status
                if ( hw_types[str(sw_id)] == "switch" ):
                    UpdateDevice(sw_id, int(sw_status), "")
                elif ( hw_types[str(sw_id)] == "dimmer" ):
                    if ( sw_status == "0" ):
                        UpdateDevice(sw_id, 0, str(Switch["dimlevel"]))
                    else:                    
                        UpdateDevice(sw_id, 2, str(Switch["dimlevel"]))
        except:
            Domoticz.Error("Error reading switch values")


        # Update the sensors
        try:
            for Sensor in GetValue(Data["response"], "kakusensors", []):
                sens_id = Sensor["id"] + hwid_offset["sensor_id"]
                sens_status = str(GetValue(Sensor, "status", "no")).lower()                                

                if ( sens_status == "yes" ):
                    if ( hw_types[str(sens_id)] == "smoke" ):
                        UpdateDevice(sens_id, 6, "")
                    else:
                        UpdateDevice(sens_id, 1, "")
                else:                    
                    UpdateDevice(sens_id, 0, "")
                                                                                    
        except:
            Domoticz.Error("Error reading sensor values at Unit " + str(sens_id))        
                
    return True

def onCommand(Unit, Command, Level, Hue):
    global hw_status, hwid_offset, hw_types
    hw_id = Unit - 1

    if Unit == hwid_offset["preset_id"]:
        if Level == 10:
            sendMessage("preset/0")
        elif Level == 20:
            sendMessage("preset/1")
        elif Level == 30:
            sendMessage("preset/2")
        elif Level == 40:
            sendMessage("preset/3")
        return True
    
    if (Level > 0):        
        sendMessage("sw/dim/"+str(hw_id)+"/"+str(Level))
    elif (Command == "On"):
        sendMessage("sw/"+str(hw_id)+"/on")
    else:
        sendMessage("sw/"+str(hw_id)+"/off")

    if hw_status == "ok":
        return True
    else:
        return False

def onHeartbeat():    
    onMessage(sendMessage("get-status"), "", "")
    EnergyMeters()
    return True

def onDisconnect():
    return

def onStop():
    Domoticz.Log("onStop called")
    return True
	
def HumStat(Humidity):
    if 0 <= Humidity < 30:
        return 2
    elif 30 <= Humidity < 50:
        return 0
    elif 50 <= Humidity <= 60:
        return 1
    else:
        return 3

def EnergyMeters():
    global hw_status, hwid_offset, hw_types
    
    data = sendMessage("enlist")
    if hw_status == "ok":
        i = 0
        for Energymeter in data["response"]:            
            if ( hwid_offset["en_id"]+i not in Devices ):
                Domoticz.Device(Name="Energymeter",  Unit=hwid_offset["en_id"]+i, TypeName="kWh").Create()
            en_0 = GetValue(Energymeter, "po", "0")
            en_1 = GetValue(Energymeter, "dayTotal", "0")
            UpdateDevice(hwid_offset["en_id"]+i, 0, str(en_0)+";"+str(en_1 * 1000))
            i = i + 1
    return

def Thermometers():
    global hw_status, term_id, hw_types
    
    data = sendMessage("telist")
    if hw_status == "ok":
        Domoticz.Log("No. of thermometers found: " + str(len(data["response"])))
        i = 0        
        for Thermometer in data["response"]:
            if ( hwid_offset["term_id"]+i not in Devices ):
                Domoticz.Device(Name=Thermometer["name"],  Unit=hwid_offset["term_id"]+i, TypeName="Temp+Hum").Create()
            te_0 = GetValue(Thermometer, "te", "0")
            hu_0 = GetValue(Thermometer, "hu", "0")
            UpdateDevice(hwid_offset["term_id"]+i, 0, str(te_0)+";"+str(hu_0)+";"+str(HumStat(hu_0)))
            i = i + 1
    return

def Switches():
    global hw_status, hw_types
    
    data = sendMessage("swlist")    
    if hw_status == "ok":
        Domoticz.Log("No. of switches found: " + str(len(data["response"])))
        for Switch in data["response"]:
            sw_id = Switch["id"] + 1
            sw_status = GetValue(Switch, "status", "off").lower()            
            sw_type = GetValue(Switch, "type", "switch").lower()            
            sw_name = GetValue(Switch, "name", "switch").lower()            
            hw_types.update({str(sw_id): sw_type})
            
            if ( sw_id not in Devices ):                
                if ( sw_type == "switch" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, TypeName="Switch").Create()
                elif ( sw_type == "dimmer" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, TypeName="Percentage").Create()                

            if ( sw_status == "on" ):
                if ( sw_type == "switch" ):
                    sw_status = "1"
                elif ( sw_type == "dimmer" ):
                    sw_status = "2"
            elif ( sw_status == "off" ):
                sw_status = "0"
                
            # Update the switch status
            if ( sw_type == "switch" ):
                UpdateDevice(sw_id, int(sw_status), "")
            elif ( sw_type == "dimmer" ):                
                UpdateDevice(sw_id, int(sw_status), str(Switch["dimlevel"]))                
    return

def Sensors(aData):
    global hw_status, hwid_offset, hw_types

    if hw_status == "ok":
        Domoticz.Log("No. of sensors found: " + str(len(aData["response"]["kakusensors"])))

        for Sensor in aData["response"]["kakusensors"]:
            sens_id = Sensor["id"] + hwid_offset["sensor_id"]            
            sens_type = GetValue(Sensor, "type", "Unknown").lower()
            sens_name = GetValue(Sensor, "name", "Unknown")
            hw_types.update({str(sens_id): str(sens_type)})
            
            if ( sens_id not in Devices ):                
                if ( sens_type == "doorbell" ):                    
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=17, Switchtype=1).Create()
                elif ( sens_type == "motion" ):
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=17, Switchtype=8).Create()
                elif ( sens_type == "contact" ):
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=17, Switchtype=2).Create()
                elif ( sens_type == "smoke" ):
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=32, Subtype=3).Create()
                    
    return

def sendMessage(command):
    global hw_status, hw_route
    conn = http.client.HTTPConnection(Parameters["Address"])    

    try:		
        conn.request("GET", "/" + Parameters["Password"] + "/" + command)
        response = conn.getresponse()
        conn.close()
    
        if response.status == 200:            
            data = json.loads(response.read().decode("utf-8"))
            hw_status = data["status"]
            hw_route = data["request"]["route"]
##            Domoticz.Debug("Homewizard respone: " + str(hw_status))
        else:
            hw_status = "Unknown"        
    except:
        Domoticz.Debug("Failed to communicate to system at ip " + Parameters["Address"])
        hw_status = "Unknown"
        return False

    Domoticz.Debug("Homewizard status: " + str(hw_status))
    Domoticz.Debug("Homewizard route: " + str(hw_route))
    return data

def HWConnect():
    global hw_version

    Domoticz.Log("Connecting to " + Parameters["Address"])
    conn = http.client.HTTPConnection(Parameters["Address"])
    
    try:		
        conn.request("GET", "/" + "handshake")
        response = conn.getresponse()
        conn.close()
    
        if response.status == 200:            
            data = json.loads(response.read().decode("utf-8"))
            if data["response"]["homewizard"] == "yes":
                Domoticz.Log("Connected to the Homewizard")
                hw_status = data["status"]
                hw_version = data["response"]["version"]
                hw_route = data["request"]["route"]
                Domoticz.Debug("Homewizard respone: " + str(hw_status))
                Domoticz.Debug("Homewizard status: " + str(hw_status))
                Domoticz.Log("Homewizard version: " + str(hw_version))
                return sendMessage("get-sensors")
            else:
                Domoticz.Log("We are not connected to a Homewizard!")
                return False
        else:
            hw_status = "Unknown"
            return False
    except:
        Domoticz.Debug("Failed to communicate to system at ip " + Parameters["Address"])
        hw_status = "Unknown"
        return False
    
    return data


def GetValue(arr, sKey, defValue):
    try:
        if str(sKey) in arr:
            if ( str(arr[str(sKey)]).lower() == "none" ):
                return defValue
            else:
                return arr[str(sKey)]
        else:
            return defValue
    except:
        return defValue
    
def UpdateDevice(Unit, nValue, sValue):
    global hwid_offset
# Make sure that the Domoticz device still exists (they can be deleted) before updating it 
    if (Unit in Devices):
        if (Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue):
            Devices[Unit].Update(nValue, str(sValue))
            Domoticz.Log("Update "+str(nValue)+":'"+str(sValue)+"' ("+Devices[Unit].Name+")")
        # Always update the rainmeter...
        elif (Unit == hwid_offset["rain_id"]):
            Devices[Unit].Update(nValue, str(sValue))
    return

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")        
    return

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def stringToBase64(s):
    return base64.b64encode(s.encode('utf-8')).decode("utf-8")


0
