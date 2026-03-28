#!/bin/sh
set -eu

mongosh --quiet \
  --authenticationDatabase admin \
  -u "${MONGO_INITDB_ROOT_USERNAME}" \
  -p "${MONGO_INITDB_ROOT_PASSWORD}" <<EOF
use ${APP_MONGODB_DATABASE}
db.createUser({
  user: "${APP_MONGODB_USER}",
  pwd: "${APP_MONGODB_PASSWORD}",
  roles: [{ role: "readWrite", db: "${APP_MONGODB_DATABASE}" }]
})
EOF
