##           Homewizard Plugin
##
##           Author:         Raymond Van de Voorde
##           Version:        1.0
##           Last modified:  28-02-2017
##
"""
<plugin key="Homewizard" name="Homewizard" author="Wobbles" version="1.0" externallink="https://www.homewizard.nl/">
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
import re
import time
import base64

# Homewizard status variables
hw_version = ""
hw_status = "Unknown"
hw_route = ""
hw_preset = 0

#constants
term_id = 111
en_id = 101
rain_id = 201
wind_id = 202
preset_id = 121

# Domoticz call back functions
def onStart():
    global rain_id, wind_id, preset_id
    if Parameters["Mode6"] == "Debug":
        Domoticz.Debugging(1)
        DumpConfigToLog()    

    # Test if the first connection is ok
    HWConnect()

    # Get all thermometers
    Thermometers()

    # Get all enerymeters
    EnergyMeters()

    # Get all switches and dimmers
    Switches()

    # Add the preset selector switch
    if ( preset_id not in Devices ):
        LevelActions = "LevelActions:"+stringToBase64("||||")+";"
        LevelNames = "LevelNames:"+stringToBase64("Off|Home|Away|Sleep|Holiday")+";"
        Other = "LevelOffHidden:dHJ1ZQ==;SelectorStyle:MA==" # true is "dHJ1ZQ==", false is "ZmFsc2U=",0 is "MA==", 1 is "MQ=="
        Options = LevelActions+LevelNames+Other
        Domoticz.Device(Name="Preset", Unit=preset_id, TypeName="Selector Switch", Options=Options).Create()

    # Add the rainmeter
    if ( rain_id not in Devices ):
        Domoticz.Device(Name="Regen",  Unit=rain_id, Type=85, Subtype=3).Create()

    # Add the windmeter
    if ( wind_id not in Devices ):
        Domoticz.Device(Name="Wind",  Unit=wind_id, Type=86, Subtype=4).Create()    
    
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
    global hw_status, hw_route, hw_preset, term_id, rain_id, wind_id, preset_id

    if hw_status == "ok":                    
        hw_preset = GetValue(Data["response"], "preset", 0)
        if hw_preset == 0:
            UpdateDevice(preset_id, 0, "10")
        elif hw_preset == 1:
            UpdateDevice(preset_id, 0, "20")
        elif hw_preset == 2:
            UpdateDevice(preset_id, 0, "30")
        elif hw_preset == 3:
            UpdateDevice(preset_id, 0, "40")

        try:
            # Update the wind device
            wind_0 = float(Data["response"]["windmeters"][0]["ws"] / 3.6) * 10
            wind_1 = Data["response"]["windmeters"][0]["dir"]
            wind_1 = wind_1.split(" ", 1)
            wind_2 = float(Data["response"]["windmeters"][0]["gu"] / 3.6) * 10
            wind_3 = Data["response"]["windmeters"][0]["wc"]
            wind_4 = Data["response"]["windmeters"][0]["te"]
            UpdateDevice(wind_id, 0, str(wind_1[1])+";"+str(wind_1[0])+";"+str(wind_0)+";"+str(wind_2)+";"+str(wind_4)+";"+str(wind_3))
        except:
            Domoticz.Debug("Error reading wind values")

        try:
            # Update the rain device            
            rain_0 = Data["response"]["rainmeters"][0]["mm"]
            rain_1 = Data["response"]["rainmeters"][0]["3h"]
            UpdateDevice(rain_id, 0, str(rain_1) + ";" + str(rain_0))
        except:
            Domoticz.Debug("Error reading rainmeter values")

        try:
            # Update the thermometes
            x = 0            
            for thermometer in Data["response"]["thermometers"]:
                tmp_0 = thermometer["te"]
                tmp_1 = thermometer["hu"]
                UpdateDevice(term_id+x, 0, str(tmp_0) + ";" + str(tmp_1) + ";" + str(HumStat(tmp_1)))
                x = x + 1
        except:
            Domoticz.Debug("Error reading thermometers values")
                
        try:
            # Update the switches
            for Switch in Data["response"]["switches"]:
                sw_id = Switch["id"] + 1
                sw_status = GetValue(Switch, "status", "off").lower()
                sw_type = GetValue(Switch, "type", "switch").lower()              

                if ( sw_status == "on" ):
                    sw_status = "1"
                elif ( sw_status == "off" ):
                    sw_status = "0"
                
                # Update the switch/dimmer status
                if ( sw_type == "switch" ):
                    UpdateDevice(sw_id, int(sw_status), "")
                elif ( sw_type == "dimmer" ):
                    if ( sw_status == "0" ):
                        UpdateDevice(sw_id, 0, str(Switch["dimlevel"]))
                    else:                    
                        UpdateDevice(sw_id, 2, str(Switch["dimlevel"]))
        except:
            Domoticz.Debug("Error reading switch values")
        
    return True

def onCommand(Unit, Command, Level, Hue):
    global hw_status, preset_id
    hw_id = Unit - 1

    if Unit == preset_id:
        if Level == 10:
            sendMessage2("preset/0")
        elif Level == 20:
            sendMessage2("preset/1")
        elif Level == 30:
            sendMessage2("preset/2")
        elif Level == 40:
            sendMessage2("preset/3")
        return True
    
    if (Level > 0):        
        sendMessage2("sw/dim/"+str(hw_id)+"/"+str(Level))
    elif (Command == "On"):
        sendMessage2("sw/"+str(hw_id)+"/on")
    else:
        sendMessage2("sw/"+str(hw_id)+"/off")

    if hw_status == "ok":
        time.sleep(150.0 / 1000.0)
        sendMessage("get-status")
        return True
    else:
        return False

def onNotification(name, subject, text, status, priority, sound, image_file):
    Domoticz.Log("Notification: " + str(name) + ", subject: " + str(subject) + ", text: " + str(text) + ", status: " + str(status))
    return

def onHeartbeat():    
    sendMessage("get-status")
    EnergyMeters()
    return True

def onDisconnect():
    ClearDevices()
    return

def onStop():
    Domoticz.Log("onStop called")
    ClearDevices()
    return True

def ClearDevices():
    # Stop everything and make sure things are synced
    return
	
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
    global hw_status, en_id
    
    data = sendMessage2("enlist")
    if hw_status == "ok":
        i = 0
        for Energymeter in data["response"]:
            if ( en_id+i not in Devices ):
                Domoticz.Device(Name="Energymeter",  Unit=en_id+i, Type=243, Subtype=29).Create()
            en_0 = GetValue(Energymeter, "po", "0")
            en_1 = GetValue(Energymeter, "dayTotal", "0")
            UpdateDevice(en_id+i, 0, str(en_0)+";"+str(en_1 * 1000))
            i = i + 1
    return

def Thermometers():
    global hw_status, term_id
    
    data = sendMessage2("telist")
    if hw_status == "ok":
        i = 0        
        for Thermometer in data["response"]:
            if ( term_id+i not in Devices ):
                Domoticz.Device(Name=Thermometer["name"],  Unit=term_id+i, Type=82, Subtype=7).Create()
            te_0 = GetValue(Thermometer, "te", "0")
            hu_0 = GetValue(Thermometer, "hu", "0")
            UpdateDevice(term_id+i, 0, str(te_0)+";"+str(hu_0)+";"+str(HumStat(hu_0)))
            i = i + 1
    return

def Switches():
    global hw_status
    
    data = sendMessage2("swlist")    
    if hw_status == "ok":        
        for Switch in data["response"]:
            sw_id = Switch["id"] + 1
            sw_status = GetValue(Switch, "status", "off").lower()            
            sw_type = GetValue(Switch, "type", "switch").lower()            
            sw_name = GetValue(Switch, "name", "switch").lower()            
            
            if ( sw_id not in Devices ):                
                if ( sw_type == "switch" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, Type=16, Subtype=1).Create()
                elif ( sw_type == "dimmer" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, Type=244, Subtype=73, Switchtype=7).Create()                

            if ( sw_status == "on" ):
                sw_status = "2"
            elif ( sw_status == "off" ):
                sw_status = "0"
                
            # Update the switch status
            if ( sw_type == "switch" ):
                UpdateDevice(sw_id, int(sw_status), "")
            elif ( sw_type == "dimmer" ):                
                UpdateDevice(sw_id, int(sw_status), str(Switch["dimlevel"]))                
    return

def sendMessage(command):      		
    onMessage(sendMessage2(command), "", "")
    return

def sendMessage2(command):
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
            Domoticz.Debug("Homewizard respone: " + str(hw_status))
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

    Domoticz.Debug("Homewizard status: " + str(hw_status))
    Domoticz.Log("Homewizard version: " + str(hw_version))
    return data


def GetValue(arr, sKey, defValue):
    if str(sKey) in arr:
        return arr[str(sKey)]
    else:
        return defValue
    
def UpdateDevice(Unit, nValue, sValue):
    global rain_id
# Make sure that the Domoticz device still exists (they can be deleted) before updating it 
    if (Unit in Devices):
        if (Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue):
            Devices[Unit].Update(nValue, str(sValue))
            Domoticz.Log("Update "+str(nValue)+":'"+str(sValue)+"' ("+Devices[Unit].Name+")")
        # Always update the rainmeter...
        elif (Unit == rain_id):
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

def base64ToString(b):
    return base64.b64decode(b).decode('utf-8')

0
