##           Homewizard Plugin
##
##           Author:         Raymond Van de Voorde
##           Version:        2.0.24
##           Last modified:  14-03-2018
##
"""
<plugin key="Homewizard" name="Homewizard" author="Wobbles" version="2.0.24" externallink="https://www.homewizard.nl/">
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="127.0.0.1" />
        <param field="Port" label="Port" width="200px" required="true" default="80" />
	<param field="Password" label="Password" width="200px" required="true" default="1234" />
        <param field="Mode1" label="Poll interval" width="100px" required="true" default=15 />
        <param field="Mode2" label="Full update after x polls" width="100px" required="true" default=10 />
        
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
import http.client

class BasePlugin:
    enabled = True
    
    isConnected = False
    LastUnit = 0
    
    #Homewizard vars    
    hw_version = ""
    hw_route = ""
    hw_types = {}
    sendMessage = ""
    FullUpdate = 20
    
    #Const
    term_id = 111
    en_id= 101
    rain_id= 201
    wind_id= 202
    preset_id = 121
    sensor_id= 61
    el_id= 122
    gas_id = 123
    hl_pump = 126
    hl_heating = 127
    hl_dhw = 128
    hl_rte = 129
    hl_rsp = 130
    hl_tte = 131
    UpdateCount = 20

    
    def onStart(self):
        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)
            DumpConfigToLog()

        self.FullUpdate = int(Parameters["Mode2"])

        # If poll interval between 10 and 60 sec.
        if  10 <= int(Parameters["Mode1"]) <= 60:
            Domoticz.Log("Update interval set to " + Parameters["Mode1"])            
            Domoticz.Heartbeat(int(Parameters["Mode1"]))
        else:
            # If not, set to 20 sec.
            Domoticz.Heartbeat(20)

        Domoticz.Log("Full update after " + Parameters["Mode2"] + " polls")

        # Start the Homewizard connection
        self.hwConnect("get-sensors")        
        return True
        
    def onConnect(self, Status, Description):
        return True

    def onMessage(self, Data, Status, Extra):        
        try:
            strData = Data.decode("utf-8", "ignore")
            Response = json.loads(strData)
        except:
            Domoticz.Error("Invalid data received!")
            return

        # Response header details
        self.hw_status = self.GetValue(Response, "status", "error")
        self.hw_route = self.GetValue(Response["request"], "route", "error")
        Domoticz.Debug("Received route: " + self.hw_route)

        # Start handling the data if status is ok
        if ( self.hw_status == "ok" ):
            # Did we sent the handshake?
            if ( self.hw_route == "/handshake" ):
                self.hw_version = Response["version"]
                Domoticz.Log("Homewizard version: " + self.hw_version)                

            # Handle get-sensors route, also adds devices when not there...
            elif ( self.hw_route == "/get-sensors" ):
                Domoticz.Debug("Started handling get-sensors")

                # Add the preset selector switch
                if ( self.preset_id not in Devices ):
                    Options = {"LevelActions": "||||",
                                  "LevelNames": "Off|Home|Away|Sleep|Holiday",
                                  "LevelOffHidden": "true",
                                  "SelectorStyle": "0"
                               }
                    Domoticz.Device(Name="Preset", Unit=self.preset_id, TypeName="Selector Switch", Used=1, Options=Options).Create()                    

                # Handle the other devices
                self.EnergyMeters(Response)
                self.Switches(Response)            
                self.Thermometers(Response)
                self.Sensors(Response)
                self.Heatlinks(Response)

                try:
                    # Update the rain device, create it if not there
                    if ( len(Response["response"]["rainmeters"]) != 0 ):
                        if ( self.rain_id not in Devices ):
                             Domoticz.Device(Name="Regen",  Unit=self.rain_id, TypeName="Rain").Create()

                        rain_0 = self.GetValue(Response["response"]["rainmeters"][0], "mm", 0)
                        rain_1 = self.GetValue(Response["response"]["rainmeters"][0], "3h", 0)
                        UpdateDevice(self.rain_id, 0, str(rain_1) + ";" + str(rain_0), True)
                except:
                    Domoticz.Error("Error reading rainmeter values")

                try:
                    # Update the wind device, create it if not there
                    if ( len(Response["response"]["windmeters"]) != 0 ):
                        if ( self.wind_id not in Devices ):
                            Domoticz.Device(Name="Wind",  Unit=self.wind_id, TypeName="Wind+Temp+Chill").Create()


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

            # Handle the status update route
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

                        if ( str(sw_status).lower() == "on" ):
                            sw_status = "1"
                        else:
                            sw_status = "0"

                        # Update the switch/dimmer status
                        if ( self.hw_types[str(sw_id)] == "switch" ):
                            UpdateDevice(sw_id, int(sw_status), "")
                        elif ( self.hw_types[str(sw_id)] == "dimmer" ):
                            if ( sw_status == "0" ):
                                UpdateDevice(sw_id, 0, str(Switch["dimlevel"]))
                            else:
                                UpdateDevice(sw_id, 2, str(Switch["dimlevel"]))
                            
                except:
                    Domoticz.Error("Error reading switch values! Switchtype: "+self.hw_types[str(sw_id)])


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
                if ( len(Response["response"]["energymeters"]) != 0 ):
                    try:                    
                        en = Devices[self.en_id].sValue.split(";")
                        en_0 = self.GetValue(Response["response"]["energymeters"][0], "po", "0")
                        UpdateDevice(self.en_id, 0, str(en_0)+";"+str(en[1]))
                    except:
                        Domoticz.Error("Error on setting the Wattcher values!")
                
                Domoticz.Debug("Ended handle route /get-status")

            # Update the energylink
            elif ( self.hw_route == "/el" ):
                self.Energylinks(Response)

            # Handle a switch command from the Homewizard
            elif ( self.hw_route == "/sw" ):                
                try:
                    if ( self.LastCommand == "Set Level" ):
                        UpdateDevice(self.LastUnit, 2, str(self.LastLevel))                
                    elif ( str(self.LastCommand).lower() == "on" ):
                        if ( self.hw_types[str(self.LastUnit-1)] == "dimmer" ):
                            UpdateDevice(self.LastUnit, 2, "")
                        else:
                            UpdateDevice(self.LastUnit, 1, "")                        
                    else:
                        UpdateDevice(self.LastUnit, 0, "")
                except:
                    Domoticz.Error("Error handling the /sw response!")
                    
                Domoticz.Debug("Handled the /sw route")

            # Handle a Somfy command from the Homewizard
            elif ( self.hw_route == "/sf" ):
                try:
                    if ( str(self.LastCommand).lower() == "on" ):
                        UpdateDevice(self.LastUnit, 1, "")
                    else:
                        UpdateDevice(self.LastUnit, 0, "")
                except:
                    Domoticz.Error("Error handling the /sf response!")


            elif ( self.hw_route == "" ):
                # Seems this is the virtual route... (bug in HW?)
                try:
                    if ( str(self.LastCommand).lower() == "on" ):
                        UpdateDevice(self.LastUnit, 1, "")
                    else:
                        UpdateDevice(self.LastUnit, 0, "")
                except:
                    Domoticz.Error("Error handling the empty ("") response!")

            elif ( self.hw_route == "/preset" ):                                            
                UpdateDevice(self.preset_id, 2, self.LastLevel)                
                
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

            self.hwConnect(self.sendMessage)
            return True
        
        # Is it a dimmer?
        Domoticz.Debug("Detected hardware: "+self.hw_types[str(Unit)])        
        if ( str(Command) == "Set Level" ):
            self.sendMessage = "sw/dim/"+str(hw_id)+"/"+str(Level)
            
        # Is it a Somfy?
        elif  ( self.hw_types[str(Unit)] == "somfy"):
            if ( str(Command).lower() == "on" ):
                self.sendMessage = "sf/"+str(hw_id)+"/down"
            elif ( str(Command).lower() == "stop" ):
                self.sendMessage = "sf/"+str(hw_id)+"/stop"
            else:
                self.sendMessage = "sf/"+str(hw_id)+"/up"

        # Just try the default switch command
        else:                
            if (str(Command).lower() == "on"):
                self.sendMessage = "sw/"+str(hw_id)+"/on"
            else:
                self.sendMessage = "sw/"+str(hw_id)+"/off"

        # Start the Homewizard connection and send the command
        self.hwConnect(self.sendMessage)
    
        return True

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)
        return

    def onHeartbeat(self):
        self.FullUpdate = self.FullUpdate - 1
        if ( self.FullUpdate == 1 ):
            Domoticz.Debug("Sending get-sensors")
            self.hwConnect("get-sensors")
            return True

        if ( self.FullUpdate < 1 ):
            Domoticz.Debug("Sending /el/get/0/readings")
            self.hwConnect("el/get/0/readings")
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
        conn = http.client.HTTPConnection(Parameters["Address"] + ":" + Parameters["Port"], timeout=2)
        Domoticz.Debug("Sending command: "+str(command))
            
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
            Domoticz.Error("Failed to communicate to system at ip " + Parameters["Address"] + " and port " + Parameters["Port"] + ". Command " + command )
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
                if ( sw_type == "switch" ) or ( sw_type == "virtual" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, TypeName="Switch").Create()                
                elif ( sw_type == "dimmer" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, Type=244, Subtype=73, Switchtype=7).Create()
                elif ( sw_type == "somfy" ) or ( sw_type == "asun" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, Type=244, Subtype=73, Switchtype=15).Create()

            if ( str(sw_status).lower() == "on" ):
                if ( sw_type == "dimmer" ):
                    sw_status = "2"
                else:
                    sw_status = "1"
            else:
                sw_status = "0"
                
            # Update the switch status
            try:
                if ( sw_type == "switch" ) or ( sw_type == "virtual" ):
                    UpdateDevice(sw_id, int(sw_status), "")            
                elif ( sw_type == "dimmer" ):                
                    UpdateDevice(sw_id, int(sw_status), str(Switch["dimlevel"]))
                elif ( sw_type == "somfy" ):
                    UpdateDevice(sw_id, int(Switch["mode"]), "")
            except:
                Domoticz.Error("Error at setting device status! Device: "+sw_name)
                
        return

    def Thermometers(self, strData):            
        Domoticz.Log("No. of thermometers found: " + str(len(self.GetValue(strData["response"], "thermometers",{}))))
        i = 0        
        for Thermometer in self.GetValue(strData["response"], "thermometers", {}):
            if ( self.term_id+i not in Devices ):
                Domoticz.Device(Name=Thermometer["name"],  Unit=self.term_id+i, TypeName="Temp+Hum").Create()
            te_0 = self.GetValue(Thermometer, "te", 0)
            hu_0 = self.GetValue(Thermometer, "hu", 0)

            # Skip the update if both values are 0
            if not ( te_0 == 0 ) and not ( hu_0 == 0 ):
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
		elif ( sens_type == "light" ):
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=244, Switchtype=12).Create()      
                    
        return

    # TODO: Verify it works...
    # Update 11-12-2017, fails...
    def Energylinks(self, jsonData):
        try:
            el_no = len(self.GetValue(jsonData, "response",{}))
        
            Domoticz.Log("No. of Energylinks found: " + str(el_no))

            if ( el_no == 0 ):
                return
        
            el_low_in = self.GetValue(jsonData["response"][0], "consumed", 0)
            el_low_out = self.GetValue(jsonData["response"][0], "produced", 0)
    
            el_high_in = self.GetValue(jsonData["response"][1], "consumed", 0)
            el_high_out = self.GetValue(jsonData["response"][1], "produced", 0)

            gas_in = self.GetValue(jsonData["response"][2], "consumed", 0)
        
            if ( self.el_id not in Devices ):
                Domoticz.Device(Name="Electricity",  Unit=self.el_id, Type=250, Subtype=1).Create()

            if ( self.gas_id not in Devices ):
                Domoticz.Device(Name="Gas",  Unit=self.gas_id, Type=251, Subtype=2).Create()

            # Update electric usage
            Data = str(el_low_in)+";"+str(el_high_in)+";"+str(el_low_out)+";"+str(el_high_out)+";"+"0;0"
            UpdateDevice( self.el_id, 0, Data)

            # Update gas usage
            UpdateDevice ( self.gas_id, 0, str(gas_in))
        except:
            Domoticz.Error("Error at setting the energylink values!")
        
        return 


    # TODO: Verify it works...
    # Update 11-12-2017, fails...
    def Heatlinks(self, jsonData):
        try:
            hl_no = len(self.GetValue(jsonData["response"], "heatlinks",{}))
            Domoticz.Log("No. of Heatlinks found: " + str(hl_no))

            # If no heatlinks, return
            if ( hl_no == 0 ):
                return

            # Switch pump exists? If not create it.
            if ( hl_pump not in Devices ):
                Domoticz.Device(Name='HL Pump',  Unit=hl_pump, TypeName="Switch").Create()

            # Switch heating exists? If not create it.
            if ( hl_heating not in Devices ):
                Domoticz.Device(Name='HL Heating',  Unit=hl_heating, TypeName="Switch").Create()

            # Set the pump switch value
            hl_state = self.GetValue(jsonData["response"]["heatlinks"][0], "pump", "off").lower()
            if ( str(hl_state).lower() == "on" ):
                hl_state = "1"
            else:
                hl_state = "0"
                
            UpdateDevice(hl_pump, int(hl_state), "")


            # Set the heating switch value
            hl_state = self.GetValue(jsonData["response"]["heatlinks"][0], "heating", "off").lower()
            if ( str(hl_state).lower() == "on" ):
                hl_state = "1"
            else:
                hl_state = "0"
                
            UpdateDevice(hl_heating, int(hl_state), "")
            
        except:
            Domoticz.Error("Error at setting the heatlink values!")
        
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

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)
    
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
  
def UpdateDevice(Unit, nValue, sValue, AlwaysUpdate=False):    
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it 
    if (Unit in Devices):
        if ((Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue) or (AlwaysUpdate == True)):
            Devices[Unit].Update(nValue=nValue, sValue=str(sValue))
            Domoticz.Log("Update "+str(nValue)+":'"+str(sValue)+"' ("+Devices[Unit].Name+")")
    return
