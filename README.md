<b>Python plugin for Domoticz with the Homewizard</b>

It currently supports the following hardware:
<ul>
<li>Homewizard preset</li>
<li>Standard switches and dimmers</li>
<li>Doorbell</li>
<li>Motion and door sensors</li>
<li>Smoke detectors</li>
<li>Somfy devices (untested by me)</li>
<li>Thermometers</li>
<li>Windmeter</li>
<li>Rainmeter</li>
<li>Wattcher</li>
<li>Virtual switches</li>
<li>Energylink (untested by me)</li>
</ul>

<b>This plugin should work from Domoticz version 3.8153 (Stable release)</b>

<hr/>

<b>Installation Raspberry PI</b>

Move to the plugin directory
```bash
cd domoticz/plugins
git clone https://github.com/rvdvoorde/domoticz-homewizard.git
```
Restart Domoticz
```bash
sudo systemctl restart domoticz
```
  
You can now add the Homewizard on the Hardware page.

When there is an update do the following to update your plugin
```bash
cd domoticz/plugins/domoticz-homewizard
git pull
sudo systemctl restart domoticz
```
  
<b>For synology users</b>

The plugins directory should be here (thanks to c4coer)
```bash
cd /usr/local/domoticz/var/plugins
```
