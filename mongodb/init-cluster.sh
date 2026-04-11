#!/bin/sh
set -eu

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

wait_for_mongo configsvr01 27019
wait_for_mongo configsvr02 27020
wait_for_mongo configsvr03 27021
wait_for_mongo shard1-01 27118
wait_for_mongo shard1-02 27119
wait_for_mongo shard1-03 27120
wait_for_mongo shard2-01 27218
wait_for_mongo shard2-02 27219
wait_for_mongo shard2-03 27220

initiate_replica_set \
  configsvr01 \
  27019 \
  configReplSet \
  "{ _id: 0, host: 'configsvr01:27019' }, { _id: 1, host: 'configsvr02:27020' }, { _id: 2, host: 'configsvr03:27021' }"

initiate_replica_set \
  shard1-01 \
  27118 \
  shard1ReplSet \
  "{ _id: 0, host: 'shard1-01:27118' }, { _id: 1, host: 'shard1-02:27119' }, { _id: 2, host: 'shard1-03:27120' }"

initiate_replica_set \
  shard2-01 \
  27218 \
  shard2ReplSet \
  "{ _id: 0, host: 'shard2-01:27218' }, { _id: 1, host: 'shard2-02:27219' }, { _id: 2, host: 'shard2-03:27220' }"

wait_for_primary configsvr01 27019
wait_for_primary shard1-01 27118
wait_for_primary shard2-01 27218

wait_for_mongo mongos 27017

mongosh --quiet --host mongos --port 27017 <<EOF
const databaseName = "${MONGODB_DATABASE}";
const appUser = "${MONGODB_APP_USER}";
const appPassword = "${MONGODB_APP_PASSWORD}";

const adminDb = db.getSiblingDB("admin");
const configDb = db.getSiblingDB("config");
const appDb = db.getSiblingDB(databaseName);

const shardNames = adminDb.runCommand({ listShards: 1 }).shards.map((shard) => shard._id);
if (!shardNames.includes("shard1ReplSet")) {
  sh.addShard("shard1ReplSet/shard1-01:27118,shard1-02:27119,shard1-03:27120");
}
if (!shardNames.includes("shard2ReplSet")) {
  sh.addShard("shard2ReplSet/shard2-01:27218,shard2-02:27219,shard2-03:27220");
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
