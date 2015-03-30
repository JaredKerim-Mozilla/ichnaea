import collections
import re
import json
import math
import random

import requests

# https://urllib3.readthedocs.org/en/latest/security.html#openssl-pyopenssl
# Combain uses SNI and requires these libraries to make calls
import urllib3.contrib.pyopenssl
urllib3.contrib.pyopenssl.inject_into_urllib3()

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from ichnaea.geocalc import distance
from ichnaea.models.observation import CellObservation, WifiObservation

engine = create_engine('mysql+pymysql://root:mysql@localhost/location', echo=True)
Session = sessionmaker(bind=engine)
session = Session()

combain_url = 'https://cps.combain.com?key=r01gsm14jph63ei8rt0d'
google_url = 'https://www.googleapis.com/geolocation/v1/geolocate?key=AIzaSyAiM8etyRqPu7jG4izJg35HA5xxk1LsyuI'
mozilla_url = 'https://location.services.mozilla.com/v1/geolocate?key=bbe54aa4-8093-4835-9716-49caa05998b4'

def request_location(service_url, cell_observations=[], wifi_observations=[]):
    query_data = {
        'cellTowers': [{
            'cellId': cell_observation.cid,
            'locationAreaCode': cell_observation.lac,
            'mobileCountryCode': cell_observation.mcc,
            'mobileNetworkCode': cell_observation.mnc,
        } for cell_observation in cell_observations],
        'wifiAccessPoints': [{
            'macAddress': re.sub('(..(?!$))', '\g<0>:', wifi_observation.key),
            'signalStrength': wifi_observation.signal,
            'channel': wifi_observation.channel,
            'signalToNoiseRatio': wifi_observation.snr,
        } for wifi_observation in wifi_observations],
    }
    try:
        print 'requesting', query_data
        response = json.loads(requests.post(service_url, json=query_data).content)
        print 'response', response
        return response['location']['lat'], response['location']['lng']
    except Exception, e:
        return 0, 0


def score_observations(service_url, cell_observations=[], wifi_observations=[]):
    #lat, lon = request_combain(observation)
    lat, lon = request_location(service_url, cell_observations=cell_observations, wifi_observations=wifi_observations)

    if lat and lon:
        all_observations = cell_observations + wifi_observations
        avg_obs_lat = sum([obs.lat for obs in all_observations]) / len(all_observations)
        avg_obs_lon = sum([obs.lon for obs in all_observations]) / len(all_observations)
        return distance(lat, lon, avg_obs_lat, avg_obs_lon) * 1000

sorted_reports = collections.defaultdict(list)
for observation in session.query(WifiObservation).limit(100000):
    sorted_reports[('%.4f' % observation.lat, '%.4f' % observation.lon)].append(observation)
wifi_observations = [observations for observations in sorted_reports.values() if len(observations) > 2][:100]
#cell_observations = list(session.query(CellObservation).filter(CellObservation.lac > 0).filter(CellObservation.cid > 0).limit(10000))
#wifi_observations = list(session.query(WifiObservation).limit(10000))
#google_cell_scores = set([score_observations(request_google, observation) for observation in random_observations])
#google_wifi_scores = set([score_observations(google_url, wifi_observations=[observation]) for observation in wifi_observations])
google_wifi_scores = [score_observations(google_url, wifi_observations=observations[:10]) for observations in wifi_observations]
combain_wifi_scores = [score_observations(combain_url, wifi_observations=observations[:10]) for observations in wifi_observations]
mozilla_wifi_scores = [score_observations(mozilla_url, wifi_observations=observations[:10]) for observations in wifi_observations]
