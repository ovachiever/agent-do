// mongosh script for KAN-8
// Assumption: the canonical identity for Green Lantern lives in alterEgo.

const jl = db.getSiblingDB("justice_league");

print("Before:");
printjson(
  jl.heroes.findOne(
    { name: "Green Lantern" },
    { projection: { _id: 0, name: 1, alterEgo: 1, powers: 1, team: 1 } },
  ),
);

jl.heroes.updateOne(
  { name: "Green Lantern" },
  { $set: { alterEgo: "Kyle Rayner" } },
);

print("After:");
printjson(
  jl.heroes.findOne(
    { name: "Green Lantern" },
    { projection: { _id: 0, name: 1, alterEgo: 1, powers: 1, team: 1 } },
  ),
);
