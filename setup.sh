#!/bin/bash
set -e
sudo apt-get install python3-pip
sudo python3 -m pip install --upgrade pip setuptools wheel
sudo pip3 install Adafruit_DHT
sudo apt install prometheus
echo "Dont forget to configure prometheus at /etc/prometheus/prometheus.yml"