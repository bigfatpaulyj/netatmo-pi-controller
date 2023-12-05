#!/bin/bash
set -e

# Install python and the python dependencies
sudo apt-get install python3-pip
sudo python3 -m pip install --upgrade pip setuptools wheel
sudo pip3 install -r dependencies.php

# Install and configure prometheus
sudo apt install prometheus
echo '  - job_name: netatmo\
    static_configs:\
      - targets: ['localhost:8000']' >> /etc/prometheus/prometheus.yml
sudo systemctl restart prometheus
sudo systemctl enable prometheus

# Initialise the DB...
sqlite3 test5.db -init schema.sql \
    "insert into netatmo (clientid, clientsecret, redirect_url) \
    values ('{my-clientid}}','{my-client-secret}','http://{my-pi-hostname}:3000/postauth')" ".exit"

# Configure the env variables needed by the app (these should really be in the db)
echo 'export roomID={my-room-id}
      export homeID={my-home-id}' >> app.env