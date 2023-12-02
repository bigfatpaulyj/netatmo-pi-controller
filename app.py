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

# https://dev.netatmo.com/apps/createanapp

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', stream=sys.stdout, level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')

app=Flask(__name__) #instantiating flask object
kpiPiTemp =      prometheus_client.Gauge('app_pi_temp', 'Current temperature of pi sensor')
kpiPiHumidity =  prometheus_client.Gauge('app_pi_humidity', 'Current humidity of pi sensor')
kpiSetPoint =    prometheus_client.Gauge('app_set_point', 'Netatmo target temp')
kpiNetatmoTemp = prometheus_client.Gauge('app_netatmo_temp', 'Netatmo sensor temp')
kpiBoosting =    prometheus_client.Gauge('app_boosting', 'Whether app think its currently got heating on')

sensor = Adafruit_DHT.DHT22
# DHT22 sensor connected to GPIO12.
pin = 12
roomID=os.environ['roomID']
homeID=os.environ['homeID']

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
def func1():
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

@app.route('/') #defining a route in the application
def func2(): #writing a function to be executed 
	authRequired=False
	conn = sqlite3.connect('config.db')
	config=loadConfig(conn)

	humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
	# if humidity is not None and temperature is not None:
	# 	return("Temp={0:0.1f}*C Humidity={1:0.1f}%".format(temperature, humidity))
	# else:
	# 	return("Failed to get reading. Try again!")

	return render_template('index.html', context={
		'humidity':humidity,
		'temperature':temperature,
		'config': config,
		'state': randomword(8),
		'netatmo': getNetatmoTemp(conn, config)
	})		

# curl -X POST "https://api.netatmo.com/api/setroomthermpoint?home_id={homeID}&room_id={roomID}&mode=manual&temp=19&endtime=1679949948" -H "accept: application/json" -H "Authorization: Bearer {bearer}"
def setThermPoint(conn, config, desiredTemp, desiredDuration, refreshToken=False):

	# Temporarily disable turning on boiler
	return "{}"

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

exitCondition = threading.Condition()
def bgWorker():
	interval = 60
	conn = sqlite3.connect('config.db')
	config=loadConfig(conn)
	desiredTemp = 19
	zoneMaxSetPoint = 21
	heatingTime=15*60
	boosting=False

	kpiBoosting.set(0)

	while True:
		zoneInfo = getNetatmoTemp(conn, config)
		if zoneInfo!=None:

			humidity, roomTemp = Adafruit_DHT.read_retry(sensor, pin)


			# Todo, navigate to roomID...
			zoneSetPoint = zoneInfo['therm_setpoint_temperature']
			zoneTemp = zoneInfo['therm_measured_temperature']

			kpiPiTemp.set(roomTemp)
			kpiPiHumidity.set(humidity)
			kpiSetPoint.set(zoneSetPoint)
			kpiNetatmoTemp.set(zoneTemp)

			action = None
			if roomTemp < desiredTemp:
				if zoneTemp >= zoneSetPoint:
					if setThermPoint(conn, config, zoneMaxSetPoint, heatingTime) != None:
						action = "Boosting now for {} min".format(heatingTime/60)
						boosting=True
						kpiBoosting.set(1)
					else:
						action = "Boosting failed"
						kpiBoosting.set(-1)
				else:
					action = "Heating in progress."
					kpiBoosting.set(1)
				
			else:
				action = "No boost needed"
				kpiBoosting.set(0)

				if boosting and zoneSetPoint==zoneMaxSetPoint:
					# TODO Clear the manual setting we set earlier
					#setThermPoint(conn, config, None, heatingTime)
					boosting=False
					action = "No boost needed, clearing boost request."
				else:
					action = "No boost needed"


			
			# TODO - do we need to turn it off to prevent over heating!?

			logging.info("Action '{}' : roomTemp({}), roomSetPoint({}), zoneTemp({}), zoneSetPoint({}-->{})".format(
				action, roomTemp, desiredTemp, zoneTemp, zoneSetPoint, zoneMaxSetPoint) )

		with exitCondition:
			val=exitCondition.wait(interval)
			if val: return

if __name__=='__main__': #calling  main 
	try:
		prometheus_client.start_http_server(8000)
		threading.Thread(target=bgWorker).start()
		app.run(host="0.0.0.0", port=3000, threaded=True, debug=False) #launching the flask's integrated development webserver

	finally:
		with exitCondition:
			exitCondition.notify_all()


