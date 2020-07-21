import sys, os, string, time, datetime
import ldap

import filedb, api

from string import Template
from pathlib import Path

import logging
logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%d.%m.%y %H:%M:%S', level=logging.INFO)

def main():    
    global config 
    config = read_config()

    passdb_conf = read_dovecot_passdb_conf_template()
    plist_ldap = read_sogo_plist_ldap_template()
    extra_conf = read_dovecot_extra_conf()

    passdb_conf_changed = apply_config('conf/dovecot/ldap/passdb.conf', config_data = passdb_conf)
    extra_conf_changed = apply_config('conf/dovecot/extra.conf', config_data = extra_conf)
    plist_ldap_changed = apply_config('conf/sogo/plist_ldap', config_data = plist_ldap)

    if passdb_conf_changed or extra_conf_changed or plist_ldap_changed:
        logging.info ("One or more config files have been changed, please make sure to restart dovecot-mailcow and sogo-mailcow!")

    api.api_host = config['API_HOST']
    api.api_key = config['API_KEY']

    while (True):
        sync()
        interval = int(config['SYNC_INTERVAL'])
        logging.info(f"Sync finished, sleeping {interval} seconds before next cycle")
        time.sleep(interval)

def sync():
    ldap_connector = ldap.initialize(f"{config['LDAP_URI']}")
    ldap_connector.set_option(ldap.OPT_REFERRALS, 0)
    ldap_connector.simple_bind_s(config['LDAP_BIND_DN'], config['LDAP_BIND_DN_PASSWORD'])

    ldap_results = ldap_connector.search_s(config['LDAP_BASE_DN'], ldap.SCOPE_SUBTREE, 
                config['LDAP_FILTER'], 
                ['userPrincipalName', 'cn', 'userAccountControl'])

    ldap_results = map(lambda x: (
        x[1]['userPrincipalName'][0].decode(),
        x[1]['cn'][0].decode(),
        False if int(x[1]['userAccountControl'][0].decode()) & 0b10 else True), ldap_results)

    filedb.session_time = datetime.datetime.now()

    for (email, ldap_name, ldap_active) in ldap_results:
        (db_user_exists, db_user_active) = filedb.check_user(email)
        (api_user_exists, api_user_active, api_name) = api.check_user(email)

        unchanged = True

        if not db_user_exists:
            filedb.add_user(email, ldap_active)
            (db_user_exists, db_user_active) = (True, ldap_active)
            logging.info (f"Added filedb user: {email} (Active: {ldap_active})")
            unchanged = False

        if not api_user_exists:
            api.add_user(email, ldap_name, ldap_active)
            (api_user_exists, api_user_active, api_name) = (True, ldap_active, ldap_name)
            logging.info (f"Added Mailcow user: {email} (Active: {ldap_active})")
            unchanged = False

        if db_user_active != ldap_active:
            filedb.user_set_active_to(email, ldap_active)
            logging.info (f"{'Activated' if ldap_active else 'Deactived'} {email} in filedb")
            unchanged = False

        if api_user_active != ldap_active:
            api.edit_user(email, active=ldap_active)
            logging.info (f"{'Activated' if ldap_active else 'Deactived'} {email} in Mailcow")
            unchanged = False

        if api_name != ldap_name:
            api.edit_user(email, name=ldap_name)
            logging.info (f"Changed name of {email} in Mailcow to {ldap_name}")
            unchanged = False

        if unchanged:
            logging.info (f"Checked user {email}, unchanged")

    for email in filedb.get_unchecked_active_users():
        (api_user_exists, api_user_active, _) = api.check_user(email)

        if (api_user_active and api_user_active):
            api.edit_user(email, active=False)
            logging.info (f"Deactivated user {email} in Mailcow, not found in LDAP")
        
        filedb.user_set_active_to(email, False)
        logging.info (f"Deactivated user {email} in filedb, not found in LDAP")

def apply_config(config_file, config_data):
    if os.path.isfile(config_file):
        with open(config_file) as f:
            old_data = f.read()

        if old_data.strip() == config_data.strip():
            logging.info(f"Config file {config_file} unchanged")
            return False

        backup_index = 1
        backup_file = f"{config_file}.ldap_mailcow_bak"
        while os.path.exists(backup_file):
            backup_file = f"{config_file}.ldap_mailcow_bak.{backup_index}"
            backup_index += 1

        os.rename(config_file, backup_file)
        logging.info(f"Backed up {config_file} to {backup_file}")

    Path(os.path.dirname(config_file)).mkdir(parents=True, exist_ok=True)

    print(config_data, file=open(config_file, 'w'))
    
    logging.info(f"Saved generated config file to {config_file}")
    return True

def read_config():
    required_config_keys = [
        'LDAP-MAILCOW_LDAP_URI', 
        'LDAP-MAILCOW_LDAP_BASE_DN',
        'LDAP-MAILCOW_LDAP_BIND_DN', 
        'LDAP-MAILCOW_LDAP_BIND_DN_PASSWORD',
        'LDAP-MAILCOW_API_HOST', 
        'LDAP-MAILCOW_API_KEY', 
        'LDAP-MAILCOW_SYNC_INTERVAL'
    ]

    config = {}

    for config_key in required_config_keys:
        if config_key not in os.environ:
            sys.exit (f"Required environment value {config_key} is not set")

        config[config_key.replace('LDAP-MAILCOW_', '')] = os.environ[config_key]

    if 'LDAP-MAILCOW_LDAP_FILTER' in os.environ and 'LDAP-MAILCOW_SOGO_LDAP_FILTER' not in os.environ:
        sys.exit('LDAP-MAILCOW_SOGO_LDAP_FILTER is required when you specify LDAP-MAILCOW_LDAP_FILTER')

    if 'LDAP-MAILCOW_SOGO_LDAP_FILTER' in os.environ and 'LDAP-MAILCOW_LDAP_FILTER' not in os.environ:
        sys.exit('LDAP-MAILCOW_LDAP_FILTER is required when you specify LDAP-MAILCOW_SOGO_LDAP_FILTER')

    config['LDAP_FILTER'] = os.environ['LDAP-MAILCOW_LDAP_FILTER'] if 'LDAP-MAILCOW_LDAP_FILTER' in os.environ else '(&(objectClass=user)(objectCategory=person))'
    config['SOGO_LDAP_FILTER'] = os.environ['LDAP-MAILCOW_SOGO_LDAP_FILTER'] if 'LDAP-MAILCOW_SOGO_LDAP_FILTER' in os.environ else "objectClass='user' AND objectCategory='person'"

    return config

def read_dovecot_passdb_conf_template():
    with open('templates/dovecot/ldap/passdb.conf') as f:
        data = Template(f.read())

    return data.substitute(
        ldap_uri=config['LDAP_URI'], 
        ldap_base_dn=config['LDAP_BASE_DN']
        )

def read_sogo_plist_ldap_template():
    with open('templates/sogo/plist_ldap') as f:
        data = Template(f.read())

    return data.substitute(
        ldap_uri=config['LDAP_URI'], 
        ldap_base_dn=config['LDAP_BASE_DN'],
        ldap_bind_dn=config['LDAP_BIND_DN'],
        ldap_bind_dn_password=config['LDAP_BIND_DN_PASSWORD'],
        sogo_ldap_filter=config['SOGO_LDAP_FILTER']
        )

def read_dovecot_extra_conf():
    with open('templates/dovecot/extra.conf') as f:
        data = f.read()

    return data

if __name__ == '__main__':
    main()
