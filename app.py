#!/usr/bin/python3
import threading
import Adafruit_DHT
from time import sleep
import time
from flask import Flask
import sqlite3
import logging
import sys
from flask import render_template, request, redirect
import random, string
import requests
import os
import prometheus_client
import datetime

# https://dev.netatmo.com/apps/createanapp

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', stream=sys.stdout, level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
exitCondition = threading.Condition()
app=Flask(__name__) #instantiating flask object
kpi = prometheus_client.Gauge('app_gauges', 'Netatmo pi controller gauges', ['type'])

sensor = Adafruit_DHT.DHT22
# DHT22 sensor connected to GPIO12.
pin = 12
roomID=os.environ['roomID']
homeID=os.environ['homeID']
humidity = 0.0
roomTemp = 0.0

# read current netatmo temps:
# curl -X GET "https://api.netatmo.com/api/homestatus?home_id={homeID}" -H "accept: application/json" -H "Authorization: Bearer {bearer}"

def getNetatmoTemp(conn, config, refreshToken=False):
	token = config['token']
	if refreshToken:
		token = refreshAuthToken(conn, config)
		if token == None : return None

	r = requests.get(
		'https://api.netatmo.com/api/homestatus?home_id='+homeID,
		headers={'Authorization': 'Bearer {}'.format(token)})
	logging.info("Got homestatus response({}): {} {}".format(r.status_code, r.text, token))

	jsonPayload=r.json()
	if r.status_code==200:
		for roomData in jsonPayload['body']['home']['rooms']:
			if roomData['id']==roomID:
				kpi.labels('setpoint').set(roomData['therm_setpoint_temperature'])
				kpi.labels('netatmo-temp').set(roomData['therm_measured_temperature'])
				return roomData

		logging.error('Room ID {} not found in data returned from server.'.format(roomID))
		return None

	if r.status_code in [403] and refreshToken==False:
		return getNetatmoTemp(conn, config, True)

	# Some other error
	return None


def refreshAuthToken(conn, config):
	r = requests.post(
		'https://api.netatmo.com/oauth2/token', 
		data={
			"grant_type":  "refresh_token",
			"refresh_token": config['refreshtoken'],
			"client_id": config['clientid'],
			"client_secret": config['clientsecret'],
		}, 
		headers={'Content-Type': 'application/x-www-form-urlencoded'})
	logging.info("Got refresh response({}): {}".format(r.status_code, r.text))

	if r.status_code==200:
		codes=r.json()
		cursor = conn.cursor()
		cursor.execute("update netatmo set token=?, refreshtoken=?, expiretime=strftime('%s', 'now') + ?",
			(
				codes['access_token'],
				codes['refresh_token'],
				codes['expires_in']					
			))
		conn.commit()

		logging.info("Tokens refreshed in DB.")
		return codes['access_token']

	return None

def randomword(length):
	letters = string.ascii_lowercase
	return ''.join(random.choice(letters) for i in range(length))

def loadConfig(conn):
	conn.row_factory = sqlite3.Row
	cursor = conn.cursor()
	config=cursor.execute('''SELECT * FROM netatmo''')
	for row in config:
		logging.info(row)
		logging.info("clientid is : {}".format(row['clientid']))
		return row

# http://raspberrypi.local:5000/postauth?state={state}&code={code}
@app.route('/postauth')
def handleNetatmoAuthResponse():

	if 'code' in request.args:
		logging.info("Got code in callback : {}".format(request.args['code']))

		conn = sqlite3.connect('config.db')
		config=loadConfig(conn)
		r = requests.post(
			'https://api.netatmo.com/oauth2/token', 
			data={
				"grant_type":  "authorization_code",
				"client_id": config['clientid'],
				"client_secret": config['clientsecret'],
				"code": request.args['code'],
				"redirect_uri": config['redirect_url'],
				"scope": "read_thermostat write_thermostat"
			}, 
			headers={'Content-Type': 'application/x-www-form-urlencoded'})
		logging.info("Got response({}): {}".format(r.status_code, r.text))

		if r.status_code==200:
			codes=r.json()
			conn = sqlite3.connect('config.db')
			cursor = conn.cursor()
			cursor.execute("update netatmo set token=?, refreshtoken=?, expiretime=strftime('%s', 'now') + ?",
				(
					codes['access_token'],
					codes['refresh_token'],
					codes['expires_in']					
				))
			conn.commit()

			logging.info("Tokens updated in DB.")

	return redirect('/', code=302)

@app.route('/', methods=['GET', 'POST']) #defining a route in the application
def handleAdminPageRequest(): #writing a function to be executed 
	global humidity, roomTemp
	authRequired=False
	conn = sqlite3.connect('config.db')
	config=loadConfig(conn)

	if request.method == 'POST':
		newStatus = 0
		try:
			newStatus = 1 if request.form['status']=='on' else 0
		except KeyError:
			pass

		cursor = conn.cursor()
		config=cursor.execute('''UPDATE netatmo set desiredtemp=?, enabled=? WHERE clientid=? LIMIT 1''', 
			(request.form['desired'], newStatus, config['clientid']))
		conn.commit()
		logging.info("Updated config with desiredtemp={}, enabled={}".format(request.form['desired'], newStatus))

		return redirect('/', code=302)

	return render_template('index.html', context={
		'humidity':humidity,
		'temperature':roomTemp,
		'config': config,
		'state': randomword(8),
		'netatmo': getNetatmoTemp(conn, config),
		'servinghost': request.headers.get('Host').split(':')[0]
	})		

# curl -X POST "https://api.netatmo.com/api/setroomthermpoint?home_id={}&room_id={}&mode=home" -H "accept: application/json" -H "Authorization: Bearer {}"
def setScheduleMode(conn, config, refreshToken=False):

	token = config['token']
	if refreshToken:
		token = refreshAuthToken(conn, config)
		if token == None : return None

	r = requests.post(
		'https://api.netatmo.com/api/setroomthermpoint?home_id={}&room_id={}&mode=home'.format(
			homeID,
			roomID
		),
		headers={'Authorization': 'Bearer {}'.format(token)})
	logging.info("setScheduleMode response({}): {} {}".format(r.status_code, r.text, token))

	if r.status_code==200:
		return r.json()

	if r.status_code in [403] and refreshToken==False:
		return setScheduleMode(conn, config, True)

	# Some other error
	return None	

# curl -X POST "https://api.netatmo.com/api/setroomthermpoint?home_id={homeID}&room_id={roomID}&mode=manual&temp=19&endtime=1679949948" -H "accept: application/json" -H "Authorization: Bearer {bearer}"
def setThermPoint(conn, config, desiredTemp, desiredDuration, refreshToken=False):

	# Temporarily disable turning on boiler
	# return "{}"

	token = config['token']
	if refreshToken:
		token = refreshAuthToken(conn, config)
		if token == None : return None

	r = requests.post(
		'https://api.netatmo.com/api/setroomthermpoint?home_id={}&room_id={}&mode=manual&temp={}&endtime={}'.format(
			homeID,
			roomID,
			desiredTemp,
			int(time.time()+desiredDuration)
		),
		headers={'Authorization': 'Bearer {}'.format(token)})
	logging.info("setroomthermpoint response({}): {} {}".format(r.status_code, r.text, token))

	if r.status_code==200:
		return r.json()

	if r.status_code in [403] and refreshToken==False:
		return setThermPoint(conn, config, desiredTemp, desiredDuration, True)

	# Some other error
	return None


def bgWorker():
	global humidity, roomTemp
	interval = 60
	conn = sqlite3.connect('config.db')
	config=loadConfig(conn)
	zoneMaxSetPoint = 21
	heatingTime=15*60
	lastNetatmoSuccessTime=0

	kpi.labels('boosting').set(0)

	while True:
		humidity, roomTemp = Adafruit_DHT.read_retry(sensor, pin)		
		kpi.labels('pi-temp').set(roomTemp)
		kpi.labels('pi-humidity').set(humidity)

		hourOfDay = datetime.datetime.now().hour
		acceptableTime = hourOfDay >= 21 or hourOfDay <= 6

		# To prevent pulling netatmo data to frequency
		if lastNetatmoSuccessTime < time.time() - 300:
			zoneInfo = getNetatmoTemp(conn, config)
			if zoneInfo != None:
				lastNetatmoSuccessTime=time.time()
		
		if acceptableTime and zoneInfo!=None:
			zoneSetPoint = zoneInfo['therm_setpoint_temperature']
			zoneTemp = zoneInfo['therm_measured_temperature']
			zoneSetEndTime = zoneInfo['therm_setpoint_end_time'] if 'therm_setpoint_end_time' in zoneInfo else None
			thermMode = zoneInfo['therm_setpoint_mode']

			appControllingBoiler = thermMode=='manual' and zoneSetPoint==zoneMaxSetPoint
			if config['enabled']==1 and (thermMode == 'schedule' or appControllingBoiler):
				# Only take actions if we're in schedule mode, or manual mode with our configured setpoint.
				action = None
				weWantBoilerOn = roomTemp < config['desiredtemp']
				issueHeatingRequest=False

				if weWantBoilerOn:
					boostNeeded = zoneSetPoint < zoneTemp 
					currentlyFiringButSoonOff = zoneSetEndTime!=None and (zoneSetEndTime - int(time.time())) < (interval * 2)	

					if boostNeeded:
						issueHeatingRequest=True
						action = "Heat needed, and boiler not on, boosting now for {} min".format(heatingTime/60)

					if currentlyFiringButSoonOff:
						issueHeatingRequest=True
						action = "Boiler on, but ending soon, extending boost now for {} min".format(heatingTime/60)

					if issueHeatingRequest:
						if setThermPoint(conn, config, zoneMaxSetPoint, heatingTime) != None:
							kpi.labels('boosting').set(1)
						else:
							action = "Boosting failed"
							kpi.labels('boosting').set(-1)
					else:
						action = "Heating in progress."
						kpi.labels('boosting').set(1)
				elif appControllingBoiler:
					action = "Clearing existing boost"
					
					if setScheduleMode(conn, config) != None:
						kpi.labels('boosting').set(0)
					else:
						action = "Clearing existing boost failed"
						kpi.labels('boosting').set(-2)
				else:
					action = "No boost or clear needed"
					kpi.labels('boosting').set(0)
				
				logging.info("Action '{}' : roomTemp({}), roomSetPoint({}), zoneTemp({}), zoneSetPoint({}-->{})".format(
					action, roomTemp, config['desiredtemp'], zoneTemp, zoneSetPoint, zoneMaxSetPoint) )

		with exitCondition:
			val=exitCondition.wait(interval)
			if val: return

		config=loadConfig(conn)

if __name__=='__main__':
	try:
		prometheus_client.start_http_server(8000)
		threading.Thread(target=bgWorker).start()
		app.run(host="0.0.0.0", port=3000, threaded=True, debug=False) #launching the flask's integrated development webserver

	finally:
		with exitCondition:
			exitCondition.notify_all()


