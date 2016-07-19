

import os
import json
import pika
import logging

from eveimageserver import get_image_server_link


logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# App Settings
RABBITMQ_SERVER = os.environ.get('RABBITMQ_SERVER', 'rabbitmq-alpha')

# RabbitMQ Setup
connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_SERVER))
channel = connection.channel()

channel.exchange_declare(exchange='regner', type='topic')
channel.queue_declare(queue='slack-format-zkillboard', durable=True)
channel.queue_bind(exchange='regner', queue='slack-format-zkillboard', routing_key='slack.format.webhook.zkillboard')
logger.info('Connected to RabbitMQ server...')


def format_killmail_message(zkb_data, kill):
    killmail = zkb_data['killmail']

    if 'character' in killmail['victim']:
        victim_name = killmail['victim']['character']['name']
    else:
        victim_name = killmail['victim']['shipType']['name']

    victim_corp = killmail['victim']['corporation']['name']

    if 'character' in killmail['attackers'][0]:
        killer_name = killmail['attackers'][0]['character']['name']
    elif 'shipType' in killmail['attackers'][0]:
        killer_name = killmail['attackers'][0]['shipType']['name']
    else:
        killer_name = 'Unknown'

    if 'corporation' in killmail['attackers'][0]:
        killer_corp = killmail['attackers'][0]['corporation']['name']
    elif 'faction' in killmail['attackers'][0]:
        killer_corp = killmail['attackers'][0]['faction']['name']
    else:
        killer_corp = 'Unknown'

    if kill:
        title = '{} ({}) killed {} ({})'.format(killer_name, killer_corp, victim_name, victim_corp)
        color = 'good'

    else:
        title = '{} ({}) got killed by {} ({})'.format(victim_name, victim_corp, killer_name, killer_corp)
        color = 'danger'

    damage_taken = {
        'title': 'Damage taken',
        'value': '{:,}'.format(killmail['victim']['damageTaken']),
        'short': True,
    }

    attacker_count = {
        'title': 'Pilots involved',
        'value': killmail['attackerCount'],
        'short': True,
    }

    value = {
        'title': 'Value',
        'value': '{:,.2f} ISK'.format(zkb_data['zkb']['totalValue']),
        'short': True,
    }

    location = {
        'title': 'Location',
        'value': '<https://zkillboard.com/system/{}/|{}>'.format(killmail['solarSystem']['id'], killmail['solarSystem']['name']),
        'short': True,
    }

    ship = {
        'title': 'Ship',
        'value': killmail['victim']['shipType']['name'],
        'short': True,
    }


    return {
        'attachments': [
            {
                'title': title,
                'fallback': title,
                'title_link': 'https://zkillboard.com/kill/{}/'.format(zkb_data['killID']),
                'color': color,
                'thumb_url': get_image_server_link(killmail['victim']['shipType']['id'], 'type', 64),
                'fields': [
                    damage_taken,
                    attacker_count,
                    value,
                    ship,
                    location,
                ],
            }
        ]
    }


def callback(ch, method, properties, body):
    data = json.loads(body.decode())

    formatted_message = format_killmail_message(data['zkb_data'], data['kill'])

    logger.info('Formatted a Slack message for killmail with ID {}.'.format(data['zkb_data']['killID']))

    payload = {
        'webhook': data['webhook'],
        'message': formatted_message,
    }

    channel.basic_publish(
        exchange='regner',
        routing_key='slack.send.webhook',
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            delivery_mode = 2,
        ),
    )
    
    ch.basic_ack(delivery_tag = method.delivery_tag)


channel.basic_qos(prefetch_count=1)
channel.basic_consume(callback, queue='slack-format-zkillboard')
channel.start_consuming()
