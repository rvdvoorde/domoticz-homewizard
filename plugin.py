##           Homewizard Plugin
##
##           Author:         Raymond Van de Voorde
##           Version:        2.0.26
##           Last modified:  11-05-2018
##
"""
<plugin key="Homewizard" name="Homewizard" author="Wobbles" version="2.0.26" externallink="https://www.homewizard.nl/">
<description>
Homewizard Plugin.<br/>
<br/>
&quot;Ignore devices&quot; need to have ';' delimited list of devices that the Homewizard knows off and you want to be ignored in Domoticz.<br/>
<br/>
The Preset Selector(s) will pick up the temperature values from the homewizard and will be changed every full update.<br/>
When the temp in the setpoint device is the same as a preset, the corresponding preset will be selected.<br/>
<br/>
Devices will be created in the Devices Tab only and will need to be activated manually. <br/>
<br/>
</description>
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="127.0.0.1" />
        <param field="Port" label="Port" width="200px" required="true" default="80" />
        <param field="Password" label="Password" width="200px" required="true" default="1234" password="true"/>
        <param field="Mode1" label="Poll interval" width="100px" required="true" default=15 />
        <param field="Mode2" label="Full update after x polls" width="100px" required="true" default=10 />
        <param field="Mode4" label="Ignore devices" width="800px" required="false" />
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
    global el_low_in
    global el_low_out
    global el_high_in
    global el_high_out
    global el_tariff
    global hl_pr1
    global hl_pr2
    global hl_pr3
    global hl_pr4
    global ignoreList
    global deleteList

    enabled = True

    isConnected = False
    LastUnit = 0

    #Homewizard vars
    hw_version = ""
    hw_route = ""
    hw_types = {}
    sendMessage = ""
    ignoreList = {}
    deleteList = {}
    FullUpdate = 20
    el_low_in = 0
    el_low_out = 0
    el_high_in = 0
    el_high_out = 0
    el_tariff = 1
    en_dayTotal = 0
    gas_previous = 0
    
    #Const
    term_id = 111
    en_id= 101
    rain_id= 201
    wind_id= 202
    uv_id = 203
    weather_id = 204
    preset_id = 121
    sensor_id= 61
    el_id= 122
    gas_id = 123
    water_id = 124
    hl_pump = 126       # pump active
    hl_heating = 127    # heating active
    hl_shower = 128     # hot water (shower)
    hl_rte = 129        # room Temperature
    hl_rsp = 130        #
    hl_tte = 131        # target Temperature
    hl_wte = 132        # Water temerature
    hl_ofc = 133        # Foutcode
    hl_odc = 134        # Diagnostic code    
    hl_pr1 = 0
    hl_pr2 = 0
    hl_pr3 = 0
    hl_pr4 = 0
    hl_preset_id = 140  # heatlink presets
    hl_setpoint_id = 141 # set temp device
    UpdateCount = 20

    # http://ip/password/kks/testsmoke/id

    def onStart(self):
        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)
            DumpConfigToLog()
        self.FullUpdate = int(Parameters["Mode2"])

        # If poll interval between 10 and 60 sec.
        if 10 <= int(Parameters["Mode1"]) <= 60:
            Domoticz.Log("Update interval set to " + Parameters["Mode1"])
            Domoticz.Heartbeat(int(Parameters["Mode1"]))
        else:
            # If not, set to 20 sec.
            Domoticz.Heartbeat(20)

        Domoticz.Log("Full update after " + Parameters["Mode2"] + " polls")

        if (len(Parameters["Mode4"]) != 0):
            dictValue=1
            delno = 1
            for item in Parameters["Mode4"].split(';'):
                for x in Devices:
                    if item in Devices[x].Name:
                        Domoticz.Debug("Deleting Ignored Device ID: '" + str(x) + "' " +str(Devices[x].Name))
                        deleteList[delno] = x
                        delno += 1
                ignoreList[dictValue] = str(item)
                dictValue += 1
            Domoticz.Debug("Deleting devices : " + str(deleteList))
            DeleteFiltered()

            Domoticz.Debug("ignoring devices : " + str(ignoreList))
        else:
            Domoticz.Log("No Devices will be ignored.")

        # Start the Homewizard connection
        self.hwConnect("el/get/0/readings")
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

                if ( len(Response["response"]["switches"]) != 0 ):
                    self.Switches(Response)

                if ( len(Response["response"]["uvmeters"]) != 0 ):
                    self.UvMeters(Response)

                if ( len(Response["response"]["windmeters"]) != 0 ):
                    self.WindMeters(Response)

                if ( len(Response["response"]["rainmeters"]) != 0 ):
                    self.RainMeters(Response)

                if ( len(Response["response"]["thermometers"]) != 0 ):
                    self.Thermometers(Response)

                if ( len(Response["response"]["weatherdisplays"]) != 0 ):
                    self.WeatherDisplays(Response)

                if ( len(Response["response"]["energymeters"]) != 0 ):
                    self.EnergyMeters(Response)

                if ( len(Response["response"]["energylinks"]) != 0 ):
                    self.Energylinks(Response)

                if ( len(Response["response"]["heatlinks"]) != 0 ):
                    self.Heatlinks(Response)

                if ( len(Response["response"]["kakusensors"]) != 0 ):
                    self.Sensors(Response)

                Domoticz.Debug("Ended handling get-sensors")

            # Handle the status update route
            elif ( self.hw_route == "/get-status" ):
                Domoticz.Debug("Starting handle route /get-status")

                # update preset
                self.hw_preset = self.GetValue(Response["response"], "preset", 0)
                if self.hw_preset == 0:
                    UpdateDevice(self.preset_id, 2, "10")
                elif self.hw_preset == 1:
                    UpdateDevice(self.preset_id, 2, "20")
                elif self.hw_preset == 2:
                    UpdateDevice(self.preset_id, 2, "30")
                elif self.hw_preset == 3:
                    UpdateDevice(self.preset_id, 2, "40")

                if ( len(Response["response"]["switches"]) != 0 ):
                    self.Switches(Response)

                if ( len(Response["response"]["uvmeters"]) != 0 ):
                    self.UvMeters(Response)

                if ( len(Response["response"]["windmeters"]) != 0 ):
                    self.WindMeters(Response)

                if ( len(Response["response"]["rainmeters"]) != 0 ):
                    self.RainMeters(Response)

                if ( len(Response["response"]["thermometers"]) != 0 ):
                    self.Thermometers(Response)

                if ( len(Response["response"]["weatherdisplays"]) != 0 ):
                    self.WeatherDisplays(Response)

                if ( len(Response["response"]["energymeters"]) != 0 ):
                    self.EnergyMeters(Response)

                if ( len(Response["response"]["energylinks"]) != 0 ):
                    self.Energylinks(Response)

                if ( len(Response["response"]["heatlinks"]) != 0 ):
                    self.Heatlinks(Response)

                if ( len(Response["response"]["kakusensors"]) != 0 ):
                    self.Sensors(Response)

                Domoticz.Debug("Ended handle route /get-status")

            # Handle the energylinks update route
            elif ( self.hw_route == "/el" ):

                Domoticz.Debug("Start handle route /el")
                self.Energylinks_Totals(Response)

            elif ( self.hw_route == "/hl" ):
                #set heatlink TODO
                Domoticz.Debug("Start handle route /hl")
                #http://homewizard/secret/hl/0/settarget/26

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
        if ( Unit == self.preset_id ) or ( Unit == self.hl_preset_id ) or ( Unit == self.hl_setpoint_id):
            if ( Level == 10 ):
                preset = 0
                target = hl_pr1
            elif ( Level == 20 ):
                preset = 1
                target = hl_pr2
            elif ( Level == 30 ):
                preset = 2
                target = hl_pr3
            elif ( Level == 40 ):
                preset = 3
                target = hl_pr4

            if ( Unit == self.preset_id ):
                self.sendMessage = "preset/"+str(preset)

            elif ( Unit == self.hl_preset_id ):
                self.sendMessage = "hl/0/settarget/"+str(target)

            # send command to change heating to be tested
            elif  ( Unit == self.hl_setpoint_id):
                self.sendMessage = "hl/0/settarget/"+str(Level)

            self.hwConnect(self.sendMessage)
            return True

        # Is it a dimmer?
        Domoticz.Debug("Detected hardware: "+self.hw_types[str(Unit)])
        if ( str(Command) == "Set Level" ):
            self.sendMessage = "sw/dim/"+str(hw_id)+"/"+str(Level)

        # Is it a Somfy or brel ?
        elif  ( self.hw_types[str(Unit)] == "somfy") or ( self.hw_types[str(Unit)] == "brel"):
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
        self.FullUpdate -=  1
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
            Domoticz.Debug("Failed to communicate to system at ip " + Parameters["Address"] + " and port " + Parameters["Port"] + ". Command " + command )
            return False

    def WindMeters(self, strData):

        Domoticz.Debug("Retrieve WindMeter Data: ")
        try:
            # Update the wind device, create it if not there
            if ( self.wind_id not in Devices ) and ("Wind" not in ignoreList):
                Domoticz.Device(Name="Wind",  Unit=self.wind_id, TypeName="Wind+Temp+Chill").Create()

            wind_0 = round(float(self.GetValue(strData["response"]["windmeters"][0], "ws", 0) / 3.6) * 10, 2)
            wind_1 = self.GetValue(strData["response"]["windmeters"][0], "dir", "N 0")
            wind_1 = wind_1.split(" ", 1)
            wind_2 = round(float(self.GetValue(strData["response"]["windmeters"][0], "gu", 0) / 3.6) * 10, 2)
            wind_3 = self.GetValue(strData["response"]["windmeters"][0], "wc", 0)
            wind_4 = self.GetValue(strData["response"]["windmeters"][0], "te", 0)
            wind_5 = self.GetValue(strData["response"]["windmeters"][0], "lowBattery", "")
            Domoticz.Debug("Battery low :" + str(wind_5))
            UpdateDevice(self.wind_id, 0, str(wind_1[1])+";"+str(wind_1[0])+";"+str(wind_0)+";"+str(wind_2)+";"+str(wind_4)+";"+str(wind_3))
        except:
            Domoticz.Error("Error reading wind values")
        return

    def UvMeters(self, strData):
        # skeleton to be finish soon
        Domoticz.Debug("Retrieve UvMeter Data: ")
        #try:
        #    # Update the UV device, create it if not there
        #    if ( self.uv_id not in Devices ):
        #        # Domoticz.Device(Name="?????",  Unit=self.uv_id, TypeName="????").Create()
        #    #UpdateDevice(self.rain_id, 0, str(rain_1) + ";" + str(rain_0))
        #except:
        #    Domoticz.Error("Error reading UvMeter values")
        return

    def WeatherDisplays(self, strData):
        # skeleton to be finish soon
        Domoticz.Debug("Retrieve Weather Displays Data: ")
        #try:
        #    # Update the Weather Displays, create it if not there
        #    if ( self.weather_id not in Devices ):
        #        # Domoticz.Device(Name="Weerstation",  Unit=self.weather_id, TypeName="weather").Create()

        #    #UpdateDevice(self.weather_id, 0, str(rain_1) + ";" + str(rain_0))
        #except:
        #    Domoticz.Error("Error Weather Displays values")
        return

    def RainMeters(self, strData):

        Domoticz.Debug("Retrieve RainMeter Data: ")
        try:
            # Update the rain device, create it if not there
            if ( self.rain_id not in Devices ) and ("Regen" not in ignoreList):
                Domoticz.Device(Name="Regen",  Unit=self.rain_id, TypeName="Rain").Create()

            rain_0 = self.GetValue(strData["response"]["rainmeters"][0], "mm", 0)
            rain_1 = self.GetValue(strData["response"]["rainmeters"][0], "3h", 0)
            UpdateDevice(self.rain_id, 0, str(rain_1) + ";" + str(rain_0))
        except:
            Domoticz.Error("Error reading rainmeter values")
        return

    def EnergyMeters(self, strData):
        Domoticz.Debug("No. of Energymeters found: " + str(len(strData["response"]["energymeters"])))
        i = 0
        for Energymeter in self.GetValue(strData["response"], "energymeters", {}):
            if ( self.en_id+i not in Devices ) and ("Energymeter" not in ignoreList):
                Domoticz.Device(Name="Energymeter",  Unit=self.en_id+i, TypeName="kWh").Create()
            en_0 = self.GetValue(Energymeter, "po", "0")
            en_1 = self.GetValue(Energymeter, "dayTotal", "0")
            UpdateDevice(self.en_id+i, 0, str(en_0)+";"+str(en_1 * 1000))
            i += 1

            if en_1 == "0":
                UpdateDevice(self.en_id+i, 0, str(en_0)+";"+str(self.en_dayTotal * 1000))
            else:
                self.en_dayTotal = en_1
                UpdateDevice(self.en_id+i, 0, str(en_0)+";"+str(en_1 * 1000))
            i = i + 1
        return


    def Switches(self, strData):
        Domoticz.Debug("No. of switches found: " + str(len(strData["response"]["switches"])))
        for Switch in self.GetValue(strData["response"], "switches", {}):
            sw_id = Switch["id"] + 1
            sw_status = self.GetValue(Switch, "status", "off").lower()
            sw_type = self.GetValue(Switch, "type", "switch").lower()
            sw_name = self.GetValue(Switch, "name", "switch").lower()
            self.hw_types.update({str(sw_id): sw_type})

            if ( sw_id not in Devices ) and ( sw_name not in ignoreList ):
                if ( sw_type == "switch" ) or ( sw_type == "virtual" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, TypeName="Switch").Create()
                elif ( sw_type == "dimmer" ):
                    Domoticz.Device(Name=sw_name,  Unit=sw_id, Type=244, Subtype=73, Switchtype=7).Create()
                elif ( sw_type == "somfy" ) or ( sw_type == "asun" ) or ( sw_type == "brel" ):
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
                if ( sw_type == "switch" ) or ( sw_type == "virtual" ) or ( sw_type == "asun" ):
                    UpdateDevice(sw_id, int(sw_status), "")
                elif ( sw_type == "dimmer" ):
                    UpdateDevice(sw_id, int(sw_status), str(Switch["dimlevel"]))
                elif ( sw_type == "somfy" ) or ( sw_type == "brel" ):
                    UpdateDevice(sw_id, int(Switch["mode"]), "")
            except:
                Domoticz.Error("Error at setting device status! Switches: "+sw_name)

        return

    def Thermometers(self, strData):
        Domoticz.Debug("No. of thermometers found: " + str(len(self.GetValue(strData["response"], "thermometers",{}))))
        i = 0
        for Thermometer in self.GetValue(strData["response"], "thermometers", {}):
            if ( self.term_id+i not in Devices ) and ( Thermometer["name"] not in ignoreList ):
                Domoticz.Device(Name=Thermometer["name"],  Unit=self.term_id+i, TypeName="Temp+Hum").Create()
            te_0 = self.GetValue(Thermometer, "te", 0)
            hu_0 = self.GetValue(Thermometer, "hu", 0)

            # Skip the update if both values are 0
            if not ( te_0 == 0 ) and not ( hu_0 == 0 ):
                UpdateDevice(self.term_id+i, 0, str(te_0)+";"+str(hu_0)+";"+str(self.HumStat(hu_0)))

            i += 1
        return


    def Sensors(self, strData):
        Domoticz.Debug("No. of sensors found: " + str(len(self.GetValue(strData["response"], "kakusensors",{}))))

        for Sensor in self.GetValue(strData["response"], "kakusensors",{}):
            sens_id = Sensor["id"] + self.sensor_id
            sens_type = self.GetValue(Sensor, "type", "Unknown").lower()
            sens_name = self.GetValue(Sensor, "name", "Unknown")
            self.hw_types.update({str(sens_id): str(sens_type)})
            if ( sens_id not in Devices ) and ( sens_name not in ignoreList ):
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
                elif ( sens_type == "leakage" ):
                    Domoticz.Device(Name=sens_name,  Unit=sens_id, Type=32 , Switchtype=8).Create()

            # Update the sensors
            sens_status = str(self.GetValue(Sensor, "status", "no")).lower()

            if ( sens_status == "yes" ):
                if ( self.hw_types[str(sens_id)] == "smoke" ) or ( self.hw_types[str(sens_id)] == "smoke868" ):
                    UpdateDevice(sens_id, 6, "")
                else:
                    UpdateDevice(sens_id, 1, "")
            else:
                UpdateDevice(sens_id, 0, "")

        return

    def Energylinks(self, strData):

        global el_tariff
        water = 0
        solar = 0

        el_no = len(self.GetValue(strData["response"], "energylinks",{}))
        Domoticz.Debug("Nr. of Energylinks found: " + str(el_no))

        if ( el_no == 0 ):
            return

        try:
            el_tariff = self.GetValue(strData["response"]["energylinks"][0], "tariff", 0)
            Domoticz.Debug("Current Meter has " +str(el_tariff)+" counter")

            el_t1 = self.GetValue(strData["response"]["energylinks"][0], "t1", "")
            Domoticz.Debug("Current T1 value: " +str(el_t1))

            el_t2 = self.GetValue(strData["response"]["energylinks"][0], "t2", "")
            Domoticz.Debug("Current T2 value: " +str(el_t2))

            if (el_t1 == "") and (el_t2 == ""):
                Domoticz.Debug("No special meters found")
            else:
                Domoticz.Log("Special Meter found t1 : "+str(el_t1)+" t2 : "+str(el_t2))

                # if Solar panels connected
                if (el_t1 == "solar"):
                    solar_po   = self.GetValue(Energylinks["s1"][0], "po"      , 0)
                    solar_used = self.GetValue(Energylinks["s1"][0], "dayTotal", 0)

                if (el_t2 == "solar"):
                    solar_po   = self.GetValue(Energylinks["s2"][0], "po"      , 0)
                    solar_used = self.GetValue(Energylinks["s2"][0], "dayTotal", 0)

                # if water meter connected
                if (el_t1 == "water"):
                    water_po   = self.GetValue(Energylinks["s1"][0], "po"      , 0)
                    water_used = self.GetValue(Energylinks["s1"][0], "dayTotal", 0) / 1000

                if (el_t2 == "water"):
                    water_po   = self.GetValue(Energylinks["s2"][0], "po"      , 0)
                    water_used = self.GetValue(Energylinks["s2"][0], "dayTotal", 0) / 1000

                if (el_t1 == "water") or (el_t2 == "water"):
                    if ( self.water_id not in Devices ) and ( "Water" not in ignoreList):
                        Domoticz.Device(Name="Water", Unit=self.water_id, Type=113).Create()
                    UpdateDevice( self.el_id, 0, str(water_po)+";"+str(water_used))
        except:
            Domoticz.Error("Error at setting the special meter values!")


        try:
            for Energylinks in self.GetValue(strData["response"], "energylinks", {}):
                power_current = self.GetValue(Energylinks["used"],"po", 0)
                Domoticz.Debug("Current Energy usage: " + str(power_current))

        except:
            Domoticz.Error("Error at getting the energylink values!")

        # add solar power to meter reading
        if (el_t1 == "solar") or (el_t2 == "solar"):
            power_current = power_current + solar_po
            # el_total = el_total + solar_used

        try:
            if ( self.el_id not in Devices ) and ( "Electricity" not in ignoreList ):
                Domoticz.Device(Name="Electricity", Unit=self.el_id, Type=250, Subtype=1).Create()

            # update power usage
            Data = str(el_low_in)+";"+str(el_high_in)+";"+str(el_low_out)+";"+str(el_high_out)+";"+str(power_current)+";0"
            UpdateDevice( self.el_id, 0, Data)

        except:
            Domoticz.Error("Error at setting the Gas values!")

        return

    def Energylinks_Totals(self, strData):

        global el_low_in
        global el_low_out
        global el_high_in
        global el_high_out

        try:
            el_no = len(strData["response"])
            Domoticz.Debug("No. of Energylinks found: " + str(el_no))

            # If no energylinks, return
            if ( el_no == 0 ):
                return

            el_low_in = self.GetValue(strData["response"][0], "consumed", 0) * 1000
            el_low_out = self.GetValue(strData["response"][0], "produced", 0) * 1000

            el_high_in = self.GetValue(strData["response"][1], "consumed", 0) * 1000
            el_high_out = self.GetValue(strData["response"][1], "produced", 0) * 1000

            Domoticz.Debug("Data Found low in : "+str(el_low_in)+" high in: "+str(el_high_in)+" low out: "+str(el_low_out)+" high out: "+str(el_high_out))

            gas_in = self.GetValue(strData["response"][2], "consumed", 0) * 1000

            if ( gas_in == 0 ):
                return

            if ( self.gas_id not in Devices )  and ( "Gas" not in ignoreList ):
                Domoticz.Device(Name="Gas",  Unit=self.gas_id, Type=251, Subtype=2).Create()
            UpdateDevice ( self.gas_id, 0, str(gas_in))

        except:
            Domoticz.Error("Error at setting the energylink values!")

        return

    def Heatlinks(self, strData):

        sourceOptions = {}          #dict with options for control
        global hl_pr1
        global hl_pr2
        global hl_pr3
        global hl_pr4

        hl_no = len(self.GetValue(strData["response"], "heatlinks",{}))
        Domoticz.Debug("No. of Heatlinks found: " + str(hl_no))

        # If no heatlinks, return
        if ( hl_no == 0 ):
            return

        try:
            self.hw_route = self.GetValue(strData["request"], "route", "error")
            # get heatlink preset values

            if ( self.hw_route == "/get-sensors" ):
                for preset in self.GetValue(strData["response"]["heatlinks"][0],"presets", {}):
                    pr_id    = self.GetValue(preset, "id", 0)
                    pr_value = self.GetValue(preset, "te", 0)
                    Domoticz.Debug("Preset "+str(pr_id)+ " "+ str(pr_value))
                    if (int(pr_id) == 0):
                        hl_pr1 = int(pr_value)
                    elif (int(pr_id) == 1):
                        hl_pr2 = int(pr_value)
                    elif (int(pr_id) == 2):
                        hl_pr3 = int(pr_value)
                    elif (int(pr_id) == 3):
                        hl_pr4 = int(pr_value)

            # room Temp exist? If not create it.
            if ( self.hl_rte not in Devices ) and ( "HL Thermostaat" not in ignoreList ):
                Domoticz.Device(Name="HL Thermostaat", Unit=self.hl_rte, TypeName="Temperature").Create()

            if ( self.hl_setpoint_id not in Devices) and ( "Heatlink Temp" not in ignoreList ):
                Domoticz.Device(Name="Heatlink Temp", Unit=self.hl_setpoint_id, Type=242, Subtype=1, Used=1).Create()

            if ( self.hl_preset_id not in Devices ) and ( "HeatLink Preset" not in ignoreList ):
                self.SourceOptions =    { "LevelActions"  : "||||",
                                        "LevelNames"    : "Off|Home|Away|Comfort|Sleep",
                                        "LevelOffHidden": "true",
                                        "SelectorStyle" : "0"
                                        }
                Domoticz.Device(Name="HeatLink Preset", Unit=self.hl_preset_id, TypeName="Selector Switch", Switchtype=18, Image=8, Options=self.SourceOptions, Used=1).Create()

            # Switch pump exists? If not create it.
            if ( self.hl_pump not in Devices ) and ( "HL Pump" not in ignoreList ):
                Domoticz.Device(Name="HL Pump",  Unit=self.hl_pump, TypeName="Switch").Create()

            # Switch heating exists? If not create it.
            if ( self.hl_heating not in Devices ) and ( "HL Heating" not in ignoreList ):
                Domoticz.Device(Name="HL Heating",  Unit=self.hl_heating, TypeName="Switch").Create()

            # Switch shower exists? If not create it.
            if ( self.hl_shower not in Devices ) and ( "HL Shower" not in ignoreList ):
                Domoticz.Device(Name="HL Shower",  Unit=self.hl_shower, TypeName="Switch").Create()

            # Display Error
            if ( self.hl_ofc not in Devices) and ( "HL Error" not in ignoreList ):
                Domoticz.Device(Name="HL Error", Unit=self.hl_ofc, TypeName="Custom", Options={"Custom": "0;Foutcode"}, Used=1).Create()

            # Display Error
            if ( self.hl_odc not in Devices) and ( "HL Diagnose" not in ignoreList ):
                Domoticz.Device(Name="HL Diagnose", Unit=self.hl_odc, TypeName="Custom", Options={"Custom": "0;Diagnose"}, Used=1).Create()

            # WaterTemp exist? If not create it.
            if ( self.hl_wte not in Devices ) and ( "HL WaterTemp" not in ignoreList ):
                Domoticz.Device(Name="HL WaterTemp", Unit=self.hl_wte, TypeName="Temperature").Create()


        except:
            Domoticz.Error("Error at creating the heatlink devices!")

        # Set watertemp value
        hl_state = self.GetValue(strData["response"]["heatlinks"][0], "wte", 0)
        UpdateDevice(self.hl_wte, 0, int(hl_state))

        # Set the roomtemp value
        hl_state = self.GetValue(strData["response"]["heatlinks"][0], "rte", 0)
        UpdateDevice(self.hl_rte, 0, int(hl_state))

        target = self.GetValue(strData["response"]["heatlinks"][0], "tte", 0)
        Domoticz.Debug("tte state : "+str(target))
        if (target == 0):
            target = hl_state

        if (int(hl_pr1) == int(target)):
            UpdateDevice(self.hl_preset_id, 2, "10")
        elif (int(hl_pr2) == int(target)):
            UpdateDevice(self.hl_preset_id, 2, "20")
        elif (int(hl_pr3) == int(target)):
            UpdateDevice(self.hl_preset_id, 2, "30")
        elif (int(hl_pr4) == int(target)):
            UpdateDevice(self.hl_preset_id, 2, "40")
        else:
            UpdateDevice(self.hl_preset_id, 2, "00")
        UpdateDevice (self.hl_setpoint_id, 0, str(target) )

        try:
            # Set Error
            hl_state = self.GetValue(strData["response"]["heatlinks"][0], "ofc", 0)
            Domoticz.Debug("ofc state : "+str(hl_state))
            UpdateDevice(self.hl_ofc, 0, int(hl_state))

            # Set diagnostic error
            hl_state = self.GetValue(strData["response"]["heatlinks"][0], "odc", 0)
            Domoticz.Debug("odc state : "+str(hl_state))
            UpdateDevice(self.hl_odc, 0, int(hl_state))

            # Set the pump switch value
            hl_state = self.GetValue(strData["response"]["heatlinks"][0], "pump", "off").lower()
            if ( str(hl_state).lower() == "on" ):
                hl_state = "1"
            else:
                hl_state = "0"
            UpdateDevice(self.hl_pump, int(hl_state), "")

            # Set the shower switch value
            hl_state = self.GetValue(strData["response"]["heatlinks"][0], "dhw", "off").lower()
            if ( str(hl_state).lower() == "on" ):
                hl_state = "1"
            else:
                hl_state = "0"
            UpdateDevice(self.hl_shower, int(hl_state), "")

            # Set the heating switch value
            hl_state = self.GetValue(strData["response"]["heatlinks"][0], "heating", "off").lower()
            if ( str(hl_state).lower() == "on" ):
                hl_state = "1"
            else:
                hl_state = "0"
            UpdateDevice(self.hl_heating, int(hl_state), "")

        except:
            Domoticz.Error("Error at getting the heatlink values!")

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
def DeleteFiltered():
    for x in deleteList:
        y = deleteList[x]
        Domoticz.Debug("Delete Ignored Device : '" + str(Devices[y].ID) + "' "+str(Devices[y].Name))
        Devices[y].Delete()
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
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

def UpdateDevice(Unit, nValue, sValue, AlwaysUpdate=False):
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it
    if (Unit in Devices):
        if ((Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue) or (AlwaysUpdate == True)):
            Devices[Unit].Update(nValue=nValue, sValue=str(sValue))
            Domoticz.Log("Update "+str(nValue)+":'"+str(sValue)+"' ("+Devices[Unit].Name+")")
    return
