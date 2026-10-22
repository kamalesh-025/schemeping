#!/bin/sh
# Nightly database backup (Phase 6 Part D).
#
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml \
#          exec -T mysql sh -c 'mysqldump ...' > backup.sql
#
# Put this in cron on the host:
#   15 2 * * * cd /srv/schemeping && ./scripts/backup.sh >> /var/log/schemeping-backup.log 2>&1
set -eu

BACKUP_DIR="${BACKUP_DIR:-/srv/schemeping/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
FILENAME="${BACKUP_DIR}/schemeping-${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T mysql \
    mysqldump --single-transaction --quick --routines --triggers \
    -u"${MYSQL_USER:-schemeping}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE:-schemeping}" \
    | gzip > "${FILENAME}"

# Keep only the recent backups.
find "${BACKUP_DIR}" -name 'schemeping-*.sql.gz' -mtime "+${KEEP_DAYS}" -delete

echo "backup written: ${FILENAME}"
