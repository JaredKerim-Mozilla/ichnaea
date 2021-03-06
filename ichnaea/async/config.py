import os

from kombu import Queue
from kombu.serialization import register

from ichnaea.async.schedule import CELERYBEAT_SCHEDULE
from ichnaea.cache import (
    configure_redis,
    DataQueue,
    ExportQueue,
)
from ichnaea.config import read_config
from ichnaea import customjson
from ichnaea.db import configure_db
from ichnaea.geoip import configure_geoip
from ichnaea.log import (
    configure_raven,
    configure_stats,
)

CELERY_QUEUES = (
    Queue('celery_default', routing_key='celery_default'),
    Queue('celery_export', routing_key='celery_export'),
    Queue('celery_incoming', routing_key='celery_incoming'),
    Queue('celery_insert', routing_key='celery_insert'),
    Queue('celery_monitor', routing_key='celery_monitor'),
    Queue('celery_reports', routing_key='celery_reports'),
    Queue('celery_upload', routing_key='celery_upload'),
)

register('internal_json', customjson.kombu_dumps, customjson.kombu_loads,
         content_type='application/x-internaljson',
         content_encoding='utf-8')


def configure_celery(celery_app):
    conf = read_config()
    if conf.has_section('celery'):
        section = conf.get_map('celery')
    else:  # pragma: no cover
        # happens while building docs locally and on rtfd.org
        return

    # testing settings
    always_eager = bool(os.environ.get('CELERY_ALWAYS_EAGER', False))
    redis_uri = os.environ.get('REDIS_URI', 'redis://localhost:6379/1')

    if always_eager and redis_uri:
        broker_url = redis_uri
        result_url = redis_uri
    else:  # pragma: no cover
        broker_url = section['broker_url']
        result_url = section['result_url']

    celery_app.config_from_object('ichnaea.async.settings')
    celery_app.conf.update(
        BROKER_URL=broker_url,
        CELERY_RESULT_BACKEND=result_url,
        CELERY_QUEUES=CELERY_QUEUES,
        CELERYBEAT_SCHEDULE=CELERYBEAT_SCHEDULE,
    )


def configure_data(redis_client):
    data_queues = {
        'update_cell': DataQueue('update_cell', redis_client,
                                 queue_key='update_cell'),
        'update_cellarea': DataQueue('update_cellarea', redis_client,
                                     queue_key='update_cell_lac'),
        'update_mapstat': DataQueue('update_mapstat', redis_client,
                                    queue_key='update_mapstat'),
        'update_score': DataQueue('update_score', redis_client,
                                  queue_key='update_score'),
        'update_wifi': DataQueue('update_wifi', redis_client,
                                 queue_key='update_wifi'),
    }
    return data_queues


def configure_export(redis_client, app_config):
    export_queues = {}
    for section_name in app_config.sections():
        if section_name.startswith('export:'):
            section = app_config.get_map(section_name)
            name = section_name.split(':')[1]
            export_queues[name] = ExportQueue(name, redis_client, section)
    return export_queues


def init_worker(celery_app, app_config,
                _db_rw=None, _db_ro=None, _geoip_db=None,
                _raven_client=None, _redis_client=None, _stats_client=None):
    # currently db_ro is not set up

    # make config file settings available
    celery_app.settings = app_config.asdict()

    # configure outside connections
    celery_app.db_rw = configure_db(
        app_config.get('ichnaea', 'db_master'), _db=_db_rw)

    celery_app.raven_client = raven_client = configure_raven(
        app_config.get('ichnaea', 'sentry_dsn'),
        transport='threaded', _client=_raven_client)

    celery_app.redis_client = redis_client = configure_redis(
        app_config.get('ichnaea', 'redis_url'), _client=_redis_client)

    celery_app.stats_client = configure_stats(
        app_config.get('ichnaea', 'statsd_host'), _client=_stats_client)

    celery_app.geoip_db = configure_geoip(
        app_config.get('ichnaea', 'geoip_db_path'), raven_client=raven_client,
        _client=_geoip_db)

    # configure data / export queues
    celery_app.all_queues = all_queues = set([q.name for q in CELERY_QUEUES])

    celery_app.data_queues = data_queues = configure_data(redis_client)
    for queue in data_queues.values():
        if queue.monitor_name:
            all_queues.add(queue.monitor_name)

    celery_app.export_queues = configure_export(redis_client, app_config)
    for queue in celery_app.export_queues.values():
        if queue.monitor_name:
            all_queues.add(queue.monitor_name)


def shutdown_worker(celery_app):
    # close outbound connections / remove custom instance state
    celery_app.db_rw.engine.pool.dispose()
    del celery_app.db_rw

    del celery_app.raven_client

    celery_app.redis_client.connection_pool.disconnect()
    del celery_app.redis_client

    del celery_app.stats_client

    del celery_app.all_queues
    del celery_app.data_queues
    del celery_app.export_queues
    del celery_app.settings
