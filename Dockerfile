FROM python:3-alpine

RUN apk update && apk --no-cache add build-base openldap-dev python2-dev python3-dev ca-certificates && rm -rf /var/cache/apk/* mkdir /usr/local/share/ca-certificates/extra
RUN pip3 install python-ldap sqlalchemy requests
RUN update-ca-certificates

COPY templates ./templates
COPY api.py filedb.py syncer.py ./

VOLUME [ "/db" ]
VOLUME [ "/conf/dovecot" ]
VOLUME [ "/conf/sogo" ]

COPY ./entrypoint.sh /entrypoint.sh
CMD ["/bin/ash", "/entrypoint.sh"]
