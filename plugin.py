##           Homewizard Plugin
##
##           Author:         Raymond Van de Voorde
##           Version:        2.0.11
##           Last modified:  17-03-2017
##
"""
<plugin key="Homewizard" name="Homewizard" author="Wobbles" version="2.0.11" externallink="https://www.homewizard.nl/">
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="127.0.0.1" />
	<param field="Password" label="Password" width="200px" required="true" default="1234" />
        <param field="Mode1" label="Poll interval" width="100px" required="true" default=20 />
        <param field="Mode2" label="Full update after x polls" width="100px" required="true" default=20 />
        
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
import json
import base64
import http.client
import datetime

class BasePlugin:
    isConnected = False
    LastUnit = 0
    
    #Homewizard vars    
    hw_version = ""
    hw_route = ""
    hw_types = {}
    sendMessage = ""
    FullUpdate = 20
    
    #Const
    Headers = {"Connection": "keep-alive", "Accept": "Content-Type: text/html; charset=UTF-8"}
    hw_port = "80"
    term_id = 111
    en_id= 101
    rain_id= 201
    wind_id= 202
    preset_id = 121
    sensor_id= 61
    el_id= 122    
    UpdateCount = 20

    
    def onStart(self):
        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)

        self.FullUpdate = int(Parameters["Mode2"])
        
        DumpConfigToLog()        
        
        if  10 <= int(Parameters["Mode1"]) <= 60:
            Domoticz.Log("Update interval set to " + Parameters["Mode1"])            
            Domoticz.Heartbeat(int(Parameters["Mode1"]))
        else:
            Domoticz.Heartbeat(20)

        Domoticz.Log("Full update after " + Parameters["Mode2"] + " polls")

        self.hwConnect("get-sensors")
        
        return True
        
    def onConnect(self, Status, Description):
        self.isConnected = True
        
        if (Status == 0):
            if ( len(self.sendMessage) > 0 ):
                Domoticz.Log("Sending onCommand message: " + self.sendMessage)
                Domoticz.Send("", "GET", "/"+Parameters["Password"]+"/"+self.sendMessage, self.Headers)
                self.sendMessage = ""
                return True            

            self.FullUpdate = self.FullUpdate - 1
            if ( self.FullUpdate == 1 ):
                Domoticz.Debug("Sending get-sensors")
                Domoticz.Send("", "GET", "/"+Parameters["Password"]+"/get-sensors", self.Headers)
                return True

            if ( self.FullUpdate == 1 ):
                Domoticz.Debug("Sending /el/get/0/readings")
                Domoticz.Send("", "GET", "/"+Parameters["Password"]+"/el/get/0/readings", self.Headers)
                self.FullUpdate = self.UpdateCount
                return True
            
            
            if ( self.hw_route == "" ):
                Domoticz.Debug("Sending handshake")
                Domoticz.Send("", "GET", "/handshake", self.Headers)
            elif ( self.hw_route == "/handshake" ):
                Domoticz.Debug("Sending get-sensors")
                Domoticz.Send("", "GET", "/"+Parameters["Password"]+"/get-sensors", self.Headers)
            elif ( self.hw_route == "/get-sensors" ):
                Domoticz.Debug("Sending get-status")
                Domoticz.Send("", "GET", "/"+Parameters["Password"]+"/get-status", self.Headers)
            else:
                Domoticz.Debug("Sending get-status")
                Domoticz.Send("", "GET", "/"+Parameters["Password"]+"/get-status", self.Headers)

        return True

    def onMessage(self, Data, Status, Extra):        
        try:
            strData = Data.decode("utf-8", "ignore")
            Response = json.loads(strData)
        except:
            Domoticz.Error("Invalid data received!")
            return
        
        self.hw_status = Response["status"]        
        self.hw_route = Response["request"]["route"]        

        Domoticz.Debug("Received route: " + self.hw_route)
        
        if ( self.hw_status == "ok" ):
            # Did we sent the handshake?
            if ( self.hw_route == "/handshake" ):
                self.hw_version = Response["version"]
                Domoticz.Log("Homewizard version: " + self.hw_version)                
                
            elif ( self.hw_route == "/get-sensors" ):
                Domoticz.Debug("Started handling get-sensors")
                # Add the preset selector switch
                if ( self.preset_id not in Devices ):
                    LevelActions = "LevelActions:"+stringToBase64("||||")+";"
                    LevelNames = "LevelNames:"+stringToBase64("Off|Home|Away|Sleep|Holiday")+";"
                    Other = "LevelOffHidden:dHJ1ZQ==;SelectorStyle:MA==" # true is "dHJ1ZQ==", false is "ZmFsc2U=",0 is "MA==", 1 is "MQ=="
                    Options = LevelActions+LevelNames+Other
                    Domoticz.Device(Name="Preset", Unit=self.preset_id, TypeName="Selector Switch", Options=Options).Create()
        
                self.EnergyMeters(Response)
                self.Switches(Response)            
                self.Thermometers(Response)
                self.Sensors(Response)                

                try:
                    # Update the rain device, create it if not there
                    if ( len(Response["response"]["rainmeters"]) != 0 ):
                        if ( self.wind_id not in Devices ):
                            Domoticz.Device(Name="Wind",  Unit=self.wind_id, TypeName="Wind+Temp+Chill").Create()
                
                        rain_0 = self.GetValue(Response["response"]["rainmeters"][0], "mm", 0)
                        rain_1 = self.GetValue(Response["response"]["rainmeters"][0], "3h", 0)
                        UpdateDevice(self.rain_id, 0, str(rain_1) + ";" + str(rain_0), True)
                except:
                    Domoticz.Error("Error reading rainmeter values")

                try:
                    # Update the wind device, create it if not there
                    if ( len(Response["response"]["windmeters"]) != 0 ):
                        if ( self.rain_id not in Devices ):
                            Domoticz.Device(Name="Regen",  Unit=self.rain_id, TypeName="Rain").Create()

                        wind_0 = round(float(self.GetValue(Response["response"]["windmeters"][0], "ws", 0) / 3.6) * 10, 2)
                        wind_1 = self.GetValue(Response["response"]["windmeters"][0], "dir", "N 0")
                        wind_1 = wind_1.split(" ", 1)
                        wind_2 = round(float(self.GetValue(Response["response"]["windmeters"][0], "gu", 0) / 3.6) * 10, 2)
                        wind_3 = self.GetValue(Response["response"]["windmeters"][0], "wc", 0)
                        wind_4 = self.GetValue(Response["response"]["windmeters"][0], "te", 0)
                        UpdateDevice(self.wind_id, 0, str(wind_1[1])+";"+str(wind_1[0])+";"+str(wind_0)+";"+str(wind_2)+";"+str(wind_4)+";"+str(wind_3))
                except:
                    Domoticz.Error("Error reading wind values")
                    
                Domoticz.Debug("Ended handling get-sensors")
                
            elif ( self.hw_route == "/get-status" ):
                Domoticz.Debug("Starting handle route /get-status")
                
                self.hw_preset = self.GetValue(Response["response"], "preset", 0)
                if self.hw_preset == 0:
                    UpdateDevice(self.preset_id, 2, "10")
                elif self.hw_preset == 1:
                    UpdateDevice(self.preset_id, 2, "20")
                elif self.hw_preset == 2:
                    UpdateDevice(self.preset_id, 2, "30")
                elif self.hw_preset == 3:
                    UpdateDevice(self.preset_id, 2, "40")

                try:
                    # Update the wind device
                    if ( len(Response["response"]["windmeters"]) != 0 ):
                        wind_0 = round(float(self.GetValue(Response["response"]["windmeters"][0], "ws", 0) / 3.6) * 10, 2)
                        wind_1 = self.GetValue(Response["response"]["windmeters"][0], "dir", "N 0")
                        wind_1 = wind_1.split(" ", 1)
                        wind_2 = round(float(self.GetValue(Response["response"]["windmeters"][0], "gu", 0) / 3.6) * 10, 2)
                        wind_3 = self.GetValue(Response["response"]["windmeters"][0], "wc", 0)
                        wind_4 = self.GetValue(Response["response"]["windmeters"][0], "te", 0)
                        UpdateDevice(self.wind_id, 0, str(wind_1[1])+";"+str(wind_1[0])+";"+str(wind_0)+";"+str(wind_2)+";"+str(wind_4)+";"+str(wind_3))
                except:
                    Domoticz.Error("Error reading wind values")

                try:
                    # Update the rain device, create it if not there
                    if ( len(Response["response"]["rainmeters"]) != 0 ):
                        rain_0 = self.GetValue(Response["response"]["rainmeters"][0], "mm", 0)
                        rain_1 = self.GetValue(Response["response"]["rainmeters"][0], "3h", 0)
                        UpdateDevice(self.rain_id, 0, str(rain_1) + ";" + str(rain_0))
                except:
                    Domoticz.Error("Error reading rainmeter values")
                
                try:
                    #Update the thermometes
                    x = 0            
                    for thermometer in self.GetValue(Response["response"], "thermometers", {}):
                        tmp_0 = self.GetValue(thermometer, "te", 0)
                        tmp_1 = self.GetValue(thermometer, "hu", 0)
                        UpdateDevice(self.term_id+x, 0, str(tmp_0) + ";" + str(tmp_1) + ";" + str(self.HumStat(tmp_1)))
                        x = x + 1
                except:
                    Domoticz.Error("Error reading thermometers values")                
                
                try:
                    # Update the switches
                    for Switch in self.GetValue(Response["response"], "switches", {}):
                        sw_id = Switch["id"] + 1
                        sw_status = self.GetValue(Switch, "status", "off").lower()

                        if ( sw_status == "on" ):
                            sw_status = "1"
                        else:
                            sw_status = "0"

                        # Update the switch/dimmer status
                        if ( self.hw_types[str(sw_id)] == "switch" ) or ( self.hw_types[str(sw_id)] == "virtual" ):
                            UpdateDevice(sw_id, int(sw_status), "")
                        elif ( self.hw_types[str(sw_id)] == "dimmer" ):
                            if ( sw_status == "0" ):
                                UpdateDevice(sw_id, 0, str(Switch["dimlevel"]))
                            else:                    
                                UpdateDevice(sw_id, 2, str(Switch["dimlevel"]))
                        elif ( self.hw_types[str(sw_id)] == "somfy" ) or ( self.hw_types[str(sw_id)] == "asun" ):                            
                            UpdateDevice(sw_id, int(Switch["mode"]), "")
                            
                except:
                    Domoticz.Error("Error reading switch values")


                # Update the sensors
                try:
                    for Sensor in self.GetValue(Response["response"], "kakusensors", {}):
                        sens_id = Sensor["id"] + self.sensor_id
                        sens_status = str(self.GetValue(Sensor, "status", "no")).lower()                                

                        if ( sens_status == "yes" ):
                            if ( self.hw_types[str(sens_id)] == "smoke" ) or ( self.hw_types[str(sens_id)] == "smoke868" ):
                                UpdateDevice(sens_id, 6, "")
                            else:
                                UpdateDevice(sens_id, 1, "")
                        else:                    
                            UpdateDevice(sens_id, 0, "")
                                                                                    
                except:
                    Domoticz.Error("Error reading sensor values")

                # Update energymeters (Wattcher)
                en = Devices[self.en_id].sValue.split(";")
                en_0 = self.GetValue(Response["response"]["energymeters"][0], "po", "0")
                UpdateDevice(self.en_id, 0, str(en_0)+";"+str(en[1]))
                
                Domoticz.Debug("Ended handle route /get-status")
                
            elif ( self.hw_route == "/el" ):
                self.Energylinks(Response)

            elif ( self.hw_route == "/sw" ):                
                if ( self.LastCommand == "Set Level" ):
                    UpdateDevice(self.LastUnit, 2, str(self.LastLevel))                
                elif ( self.LastCommand == 'On' and self.hw_types[str(self.LastUnit-1)] == "dimmer"):
                    UpdateDevice(self.LastUnit, 2, "")
                elif ( self.LastCommand == 'On' and self.hw_types[str(self.LastUnit-1)] == "switch"):
                    UpdateDevice(self.LastUnit, 1, "")
                else:
                    UpdateDevice(self.LastUnit, 0, "")                                    
                    
                Domoticz.Debug("Handled the /sw route")
                
            else:
                Domoticz.Debug("Unhandled route received! (" + self.hw_route+")")
                
        return True


                
            
    def onCommand(self, Unit, Command, Level, Hue):
        self.LastUnit = Unit
        self.LastCommand = Command
        self.LastLevel = Level
        Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))
        hw_id = Unit - 1

        # Change the Homewizard preset?
        if ( Unit == self.preset_id ):
            if ( Level == 10 ):
                self.sendMessage = "preset/0"
            elif ( Level == 20 ):
                self.sendMessage = "preset/1"
            elif ( Level == 30 ):
                self.sendMessage = "preset/2"
            elif ( Level == 40 ):
                self.sendMessage = "preset/3"                
            return True
        
        # Is it a dimmer?
        Domoticz.Debug("Detected hardware: "+self.hw_types[str(Unit)])        
        if ( str(Command) == "Set Level" ):
            self.sendMessage = "sw/dim/"+str(hw_id)+"/"+str(Level)            
        else:                
            if (Command == "On"):
                self.sendMessage = "sw/"+str(hw_id)+"/on"
            else:
                self.sendMessage = "sw/"+str(hw_id)+"/off"

        # Start the Homewizard connection and send the command
        self.hwConnect(self.sendMessage)
    
        return True

    def onNotification(self, Data):
        Domoticz.Log("Notification: " + str(Data))
        return

    def onHeartbeat(self):
        self.FullUpdate = self.FullUpdate - 1
        if ( self.FullUpdate == 1 ):
            Domoticz.Debug("Sending get-sensors")
            self.hwConnect("get-sensors")
            return True

        if ( self.FullUpdate < 1 ):
            Domoticz.Debug("Sending /el/get/0/readings")
            self.hwConnect("el/get/0/readingss")
            self.FullUpdate = int(Parameters["Mode2"])
            return True
            
        self.hwConnect("get-status")
        return

    def onDisconnect(self):
        self.isConnected = False
        return

    def onStop(self):
        Domoticz.Log("onStop called")
        return True

    def hwConnect(self, command):
        if ( self.isConnected == False ):
##            Domoticz.Transport(Transport="TCP/IP", Address=Parameters["Address"], Port=self.hw_port)
##            Domoticz.Protocol("HTTP")        
##            Domoticz.Connect()

            conn = http.client.HTTPConnection(Parameters["Address"], timeout=2)
            
            try:
                if ( command == "handshake" ):
                    conn.request("GET", "/" + command)
                else:
                    conn.request("GET", "/" + Parameters["Password"] + "/" + command)
                response = conn.getresponse()
                conn.close()
    
                if response.status == 200:            
                    self.onMessage(response.read(), "200", "")
            except:
                Domoticz.Debug("Failed to communicate to system at ip " + Parameters["Address"] + ". Command" + command )
                return False

            return True
        else:
            Domoticz.Debug("Already connected at hwConnect")
            return False

    def EnergyMeters(self, strData):                
        i = 0
        for Energymeter in self.GetValue(strData["response"], "energymeters", {}):
            if ( self.en_id+i not in Devices ):
                Domoticz.Device(Name="Energymeter",  Unit=self.en_id+i, TypeName="kWh").Create()
            en_0 = self.GetValue(Energymeter, "po", "0")
            en_1 = self.GetValue(Energymeter, "dayTotal", "0")
            UpdateDevice(self.en_id+i, 0, str(en_0)+";"+str(en_1 * 1000))
            i = i + 1
        return


    def Switches(self, strData):    
        Domoticz.Log("No. of switches found: " + str(len(strData["response"]["switches"])))
        for Switch in self.GetValue(strData["response"], "switches", {}):
            sw_id = Switch["id"] + 1
            sw_status = self.GetValue(Switch, "status", "off").lower()            
            sw_type = self.GetValue(Switch, "type", "switch").lower()            
            sw_name = self.GetValue(Switch, "name", "switch").lower()            
            self.hw_types.update({str(sw_id): sw_type})
            
            if ( sw_id not in Devices ):                
                if ( sw_type == "switch" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, TypeName="Switch").Create()
                elif ( sw_type == "virtual" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, TypeName="Switch").Create()
                elif ( sw_type == "dimmer" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, Type=244, Subtype=73, Switchtype=7).Create()
                elif ( sw_type == "somfy" ) or ( sw_type == "asun" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, TypeName="Switch").Create()

            if ( sw_status == "on" ):                
                if ( sw_type == "dimmer" ):
                    sw_status = "2"
                else:
                    sw_status = "1"
            else:
                sw_status = "0"
                
            # Update the switch status
            if ( sw_type == "switch" ):
                UpdateDevice(sw_id, int(sw_status), "")
            elif ( sw_type == "virtual" ):
                UpdateDevice(sw_id, int(sw_status), "")
            elif ( sw_type == "dimmer" ):                
                UpdateDevice(sw_id, int(sw_status), str(Switch["dimlevel"]))
            elif ( sw_type == "somfy" ):
                UpdateDevice(sw_id, int(Switch["mode"]), "")
                
        return

    def Thermometers(self, strData):            
        Domoticz.Log("No. of thermometers found: " + str(len(self.GetValue(strData["response"], "thermometers",{}))))
        i = 0        
        for Thermometer in self.GetValue(strData["response"], "thermometers", {}):
            if ( self.term_id+i not in Devices ):
                Domoticz.Device(Name=Thermometer["name"],  Unit=self.term_id+i, TypeName="Temp+Hum").Create()
            te_0 = self.GetValue(Thermometer, "te", "0")
            hu_0 = self.GetValue(Thermometer, "hu", "0")
            UpdateDevice(self.term_id+i, 0, str(te_0)+";"+str(hu_0)+";"+str(self.HumStat(hu_0)))
            i = i + 1
        return

  
    def Sensors(self, strData):    
        Domoticz.Log("No. of sensors found: " + str(len(self.GetValue(strData["response"], "kakusensors",{}))))

        for Sensor in self.GetValue(strData["response"], "kakusensors",{}):
            sens_id = Sensor["id"] + self.sensor_id            
            sens_type = self.GetValue(Sensor, "type", "Unknown").lower()
            sens_name = self.GetValue(Sensor, "name", "Unknown")
            self.hw_types.update({str(sens_id): str(sens_type)})
            
            if ( sens_id not in Devices ):                
                if ( sens_type == "doorbell" ):                    
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=17, Switchtype=1).Create()
                elif ( sens_type == "motion" ):
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=17, Switchtype=8).Create()
                elif ( sens_type == "contact" ):
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=17, Switchtype=2).Create()
                elif ( sens_type == "smoke" ) or ( sens_type == "smoke868" ):
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=32, Subtype=3).Create()                
                    
        return

    def Energylinks(self, strData):
        el_no = len(self.GetValue(strData, "response",{}))
        
        Domoticz.Log("No. of Energylinks found: " + str(el_no))

        if ( el_no == 0 ):
            return
        
        el_low_in = strData["response"][0]["consumed"]
        el_low_out = strData["response"][0]["produced"]
    
        el_high_in = strData["response"][1]["consumed"]
        el_high_out = strData["response"][1]["produced"]

        gas_in = strData["response"][2]["consumed"]

        # if ( self.el_id not in Devices ):
            #TODO: Create the device

        Data = str(el_low_in)+";"+str(el_high_in)+";"+str(el_low_out)+";"+str(el_high_out)+";"+"0;0"
        UpdateDevice( self.el_id, 0, )
        return 
        
    def is_number(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    def GetValue(self, arr, sKey, defValue):
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

    def HumStat(self, Humidity):
        if 0 <= Humidity < 30:
            return 2
        elif 30 <= Humidity < 50:
            return 0
        elif 50 <= Humidity <= 60:
            return 1
        else:
            return 3
    

    
global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Status, Description):
    global _plugin
    _plugin.onConnect(Status, Description)

def onMessage(Data, Status, Extra):
    global _plugin
    _plugin.onMessage(Data, Status, Extra)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Data):
    global _plugin
    _plugin.onNotification(Data)

def onDisconnect():
    global _plugin
    _plugin.onDisconnect()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# Generic helper functions
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
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

def stringToBase64(s):
    return base64.b64encode(s.encode('utf-8')).decode("utf-8")
  
def UpdateDevice(Unit, nValue, sValue, AlwaysUpdate=False):    
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it 
    if (Unit in Devices):
        if ((Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue) or (AlwaysUpdate == True)):
            Devices[Unit].Update(nValue=nValue, sValue=str(sValue))
            Domoticz.Log("Update "+str(nValue)+":'"+str(sValue)+"' ("+Devices[Unit].Name+")")
    return

