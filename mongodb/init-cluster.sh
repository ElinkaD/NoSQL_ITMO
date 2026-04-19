#!/bin/sh
set -eu

CONFIGSVR01_PORT="${MONGODB_CONFIGSVR01_PORT}"
CONFIGSVR02_PORT="${MONGODB_CONFIGSVR02_PORT}"
CONFIGSVR03_PORT="${MONGODB_CONFIGSVR03_PORT}"
SHARD1_01_PORT="${MONGODB_SHARD1_01_PORT}"
SHARD1_02_PORT="${MONGODB_SHARD1_02_PORT}"
SHARD1_03_PORT="${MONGODB_SHARD1_03_PORT}"
SHARD2_01_PORT="${MONGODB_SHARD2_01_PORT}"
SHARD2_02_PORT="${MONGODB_SHARD2_02_PORT}"
SHARD2_03_PORT="${MONGODB_SHARD2_03_PORT}"
MONGOS_PORT="${MONGODB_PORT}"

wait_for_mongo() {
  host="$1"
  port="$2"

  until mongosh --quiet --host "$host" --port "$port" --eval 'db.adminCommand({ ping: 1 }).ok' >/dev/null 2>&1; do
    sleep 2
  done
}

initiate_replica_set() {
  host="$1"
  port="$2"
  replica_set="$3"
  members="$4"

  mongosh --quiet --host "$host" --port "$port" --eval "
    try {
      rs.status()
    } catch (error) {
      rs.initiate({
        _id: '$replica_set',
        members: [$members]
      })
    }
  " >/dev/null
}

wait_for_primary() {
  host="$1"
  port="$2"

  until mongosh --quiet --host "$host" --port "$port" --eval '
    try {
      rs.status().members.some(member => member.stateStr === "PRIMARY") ? 0 : 1
    } catch (error) {
      1
    }
  ' | grep -qx '0'; do
    sleep 2
  done
}

wait_for_mongo configsvr01 "$CONFIGSVR01_PORT"
wait_for_mongo configsvr02 "$CONFIGSVR02_PORT"
wait_for_mongo configsvr03 "$CONFIGSVR03_PORT"
wait_for_mongo shard1-01 "$SHARD1_01_PORT"
wait_for_mongo shard1-02 "$SHARD1_02_PORT"
wait_for_mongo shard1-03 "$SHARD1_03_PORT"
wait_for_mongo shard2-01 "$SHARD2_01_PORT"
wait_for_mongo shard2-02 "$SHARD2_02_PORT"
wait_for_mongo shard2-03 "$SHARD2_03_PORT"

initiate_replica_set \
  configsvr01 \
  "$CONFIGSVR01_PORT" \
  configReplSet \
  "{ _id: 0, host: 'configsvr01:${CONFIGSVR01_PORT}' }, { _id: 1, host: 'configsvr02:${CONFIGSVR02_PORT}' }, { _id: 2, host: 'configsvr03:${CONFIGSVR03_PORT}' }"

initiate_replica_set \
  shard1-01 \
  "$SHARD1_01_PORT" \
  shard1ReplSet \
  "{ _id: 0, host: 'shard1-01:${SHARD1_01_PORT}' }, { _id: 1, host: 'shard1-02:${SHARD1_02_PORT}' }, { _id: 2, host: 'shard1-03:${SHARD1_03_PORT}' }"

initiate_replica_set \
  shard2-01 \
  "$SHARD2_01_PORT" \
  shard2ReplSet \
  "{ _id: 0, host: 'shard2-01:${SHARD2_01_PORT}' }, { _id: 1, host: 'shard2-02:${SHARD2_02_PORT}' }, { _id: 2, host: 'shard2-03:${SHARD2_03_PORT}' }"

wait_for_primary configsvr01 "$CONFIGSVR01_PORT"
wait_for_primary shard1-01 "$SHARD1_01_PORT"
wait_for_primary shard2-01 "$SHARD2_01_PORT"

wait_for_mongo mongos "$MONGOS_PORT"

mongosh --quiet --host mongos --port "$MONGOS_PORT" <<EOF
const databaseName = "${MONGODB_DATABASE}";
const appUser = "${MONGODB_APP_USER}";
const appPassword = "${MONGODB_APP_PASSWORD}";

const adminDb = db.getSiblingDB("admin");
const configDb = db.getSiblingDB("config");
const appDb = db.getSiblingDB(databaseName);

const shardNames = adminDb.runCommand({ listShards: 1 }).shards.map((shard) => shard._id);
if (!shardNames.includes("shard1ReplSet")) {
  sh.addShard("shard1ReplSet/shard1-01:${SHARD1_01_PORT},shard1-02:${SHARD1_02_PORT},shard1-03:${SHARD1_03_PORT}");
}
if (!shardNames.includes("shard2ReplSet")) {
  sh.addShard("shard2ReplSet/shard2-01:${SHARD2_01_PORT},shard2-02:${SHARD2_02_PORT},shard2-03:${SHARD2_03_PORT}");
}

const databaseEntry = configDb.databases.findOne({ _id: databaseName });
if (!databaseEntry || !databaseEntry.partitioned) {
  sh.enableSharding(databaseName);
}

const collectionEntry = configDb.collections.findOne({ _id: databaseName + ".events" });
if (!collectionEntry) {
  sh.shardCollection(databaseName + ".events", { created_by: "hashed" });
}

if (!appDb.getUser(appUser)) {
  appDb.createUser({
    user: appUser,
    pwd: appPassword,
    roles: [
      { role: "readWrite", db: databaseName },
      { role: "dbOwner", db: databaseName }
    ]
  });
}
EOF
