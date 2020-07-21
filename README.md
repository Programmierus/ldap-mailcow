# ldap-mailcow

Adds LDAP accounts to mailcow-dockerized and enables LDAP (e.g., Active Directory) authentication.

* [How does it work](#how-does-it-work)
* [Usage](#usage)
  * [LDAP Fine-tuning](#ldap-fine-tuning)
* [Limitations](#limitations)
  * [WebUI and EAS authentication](#webui-and-eas-authentication)
  * [Two-way sync](#two-way-sync)
* [Customizations and Integration support](#customizations-and-integration-support)

## How does it work

A python script periodically checks and creates new LDAP accounts and deactivates deleted and disabled ones with mailcow API. It also enables LDAP authentication in SOGo and dovecot.

## Usage

1. Create a `data/ldap` directory. SQLite database for synchronization will be stored there.
2. Extend your `docker-compose.override.yml` with an additional container:

    ```yaml
    ldap-mailcow:
        image: programmierus/ldap-mailcow
        network_mode: host
        container_name: mailcowcustomized_ldap-mailcow
        depends_on:
            - nginx-mailcow
        volumes:
            - ./data/ldap:/db:rw
            - ./data/conf/dovecot:/conf/dovecot:rw
            - ./data/conf/sogo:/conf/sogo:rw
        environment:
            - LDAP-MAILCOW_LDAP_URI=ldap(s)://dc.example.local
            - LDAP-MAILCOW_LDAP_BASE_DN=OU=Mail Users,DC=example,DC=local
            - LDAP-MAILCOW_LDAP_BIND_DN=CN=Bind DN,CN=Users,DC=example,DC=local
            - LDAP-MAILCOW_LDAP_BIND_DN_PASSWORD=BindPassword
            - LDAP-MAILCOW_API_HOST=https://mailcow.example.local
            - LDAP-MAILCOW_API_KEY=XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX
            - LDAP-MAILCOW_SYNC_INTERVAL=300
            - LDAP-MAILCOW_LDAP_FILTER=(&(objectClass=user)(objectCategory=person)(memberOf:1.2.840.113556.1.4.1941:=CN=Group,CN=Users,DC=example DC=local))
            - LDAP-MAILCOW_SOGO_LDAP_FILTER=objectClass='user' AND objectCategory='person' AND memberOf:1.2.840.113556.1.4.1941:='CN=Group,CN=Users,DC=example DC=local'
    ```

3. Configure environmental variables:

    * `LDAP-MAILCOW_LDAP_URI` - LDAP (e.g., Active Directory) URI (must be reachable from within the container). The URIs are in syntax `protocol://host:port`. For example `ldap://localhost` or `ldaps://secure.domain.org`
    * `LDAP-MAILCOW_LDAP_BASE_DN` - base DN where user accounts can be found
    * `LDAP-MAILCOW_LDAP_BIND_DN` - bind DN of a special LDAP account that will be used to browse for users
    * `LDAP-MAILCOW_LDAP_BIND_DN_PASSWORD` - password for bind DN account
    * `LDAP-MAILCOW_API_HOST` - mailcow API url. Make sure it's enabled and accessible from within the container for both reads and writes
    * `LDAP-MAILCOW_API_KEY` - mailcow API key (read/write)
    * `LDAP-MAILCOW_SYNC_INTERVAL` - interval in seconds between LDAP synchronizations
    * **Optional** LDAP filters (see example above). SOGo uses special syntax, so you either have to **specify both or none**:
        * `LDAP-MAILCOW_LDAP_FILTER` - LDAP filter to apply, defaults to `(&(objectClass=user)(objectCategory=person))`
        * `LDAP-MAILCOW_SOGO_LDAP_FILTER` - LDAP filter to apply for SOGo ([special syntax](https://sogo.nu/files/docs/SOGoInstallationGuide.html#_authentication_using_ldap)), defaults to `objectClass='user' AND objectCategory='person'`

4. Start additional container: `docker-compose up -d ldap-mailcow`
5. Check logs `docker-compose logs ldap-mailcow`
6. Restart dovecot and SOGo if necessary `docker-compose restart sogo-mailcow dovecot-mailcow`

### LDAP Fine-tuning

Container internally uses the following configuration templates:

* SOGo: `/templates/sogo/plist_ldap`
* dovecot: `/templates/dovecot/ldap/passdb.conf`

These files have been tested against Active Directory running on Windows Server 2019 domain controller. If necessary, you can edit and remount them through docker volumes. Some documentation on these files can be found here: [dovecot](https://doc.dovecot.org/configuration_manual/authentication/ldap/), [SOGo](https://sogo.nu/files/docs/SOGoInstallationGuide.html#_authentication_using_ldap)

## Limitations

### WebUI and EAS authentication

This tool enables authentication for Dovecot and SOGo, which means you will be able to log into POP3, SMTP, IMAP, and SOGo Web-Interface. **You will not be able to log into mailcow UI or EAS using your LDAP credentials by default.**

As a workaround, you can hook IMAP authentication directly to mailcow by adding the following code above [this line](https://github.com/mailcow/mailcow-dockerized/blob/48b74d77a0c39bcb3399ce6603e1ad424f01fc3e/data/web/inc/functions.inc.php#L608):

```php
    $mbox = imap_open ("{dovecot:993/imap/ssl/novalidate-cert}INBOX", $user, $pass);
    if ($mbox != false) {
        imap_close($mbox);
        return "user";
    }
```

As a side-effect, It will also allow logging into mailcow UI using mailcow app passwords (since they are valid for IMAP). **It is not a supported solution with mailcow and has to be done only at your own risk!**

### Two-way sync

Users from your LDAP directory will be added (and deactivated if disabled/not found) to your mailcow database. Not vice-versa, and this is by design.

## Customizations and Integration support

External authentication (identity federation) is an enterprise feature [for mailcow](https://github.com/mailcow/mailcow-dockerized/issues/2316#issuecomment-491212921). That’s why I developed an external solution, and it is unlikely that it’ll be ever directly integrated into mailcow.

I’ve created this tool because I needed it for my regular work. You are free to use it for commercial needs. Please understand that I can work on issues only if they fall within the scope of my current work interests or if I’ll have some available free time (never happened for many years). I’ll do my best to review submitted PRs ASAP, though.

**You can always [contact me](mailto:programmierus@gmail.com) to help you with the integration or for custom modifications on a paid basis. My current hourly rate (ActivityWatch tracked) is 100,-€ with 3h minimum commitment.**
