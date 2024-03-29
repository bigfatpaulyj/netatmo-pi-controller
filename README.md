**Control Netatmo Thermostat from Raspberry PI temperature monitor**

NOTE: this is alpha software. Don't rely on it! There's no guarantee it'll work properly!

This python application can be used in combination with this temperature and humidity sensor:

https://www.amazon.co.uk/dp/B078SVZB1X 
DHT22/AM2302

The idea is that the pi runs a python application that monitors the local room temperature. If
that gets below a certain point it requests the paired Netatmo smarty thermostat to boost its
setpoint for 15 minutes. It keeps extending the boost as necessary.

There is a set of 'acceptable hours' where it runs - the idea being that it doesn't control the
temperature outside of those hours. 

The temperature values and setpoint values are recorded into a Prometheus time-series database so you can keep 
track of how it's performing.

**Instructions** 

This was tested on Raspbian 10. 

Connect the sensor up to the pi by plugging it into the correct GPIO pins as mentioned in the instructions provided with the sensor. The script has a variable that indicates which pin it should use to access the sensor.

You need to create a Netatmo App at https://dev.netatmo.com/apps

Install using the setup.sh script - there are some details in there that you need to modify to get working. These are the items listed as {var}. The clientID and clientSecret are configured at https://dev.netatmo.com/apps.

Once installed you can bring up the app using up.sh script.

Once the python app is running, you need to authenticate your app against Netatmo by accessing the webpage of the app at : http://{my-pi-hostname}:3000/ . You should only need to do this once. Once you login at Netatmo they'll redirect you back to the redirect_url configured in setup.sh. That URL doesn't need to be publically accessible, just accessible from the place the web browser is running.

Note, there is no authentication on the PI webpage - anyone with access to port 3000 can access it. Don't make it publically accessible and make sure you trust anyone that can route to it. They'll be able to control whether your boiler is on or not.

To have the script auto-start after a reboot add the following to the root crontab (replacing {user} with the username which installed the dependencies):
@reboot su {user} -c 'cd /home/{installpath} && ./up.sh |& logger -t netatmo'

Logs can be viewed by running: journalctl -f -t netnatmo
